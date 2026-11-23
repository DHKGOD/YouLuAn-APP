"""雙平台入口要實際驗證網站，也不能重複啟動或誤連原資料庫。"""
import json
from pathlib import Path

import httpx
import pytest

from backend.app import remote_gateway
from scripts import dual_platform as launcher

ADDRESS = "https://example.invalid/" + "x" * 43


def website_response(request):
    if request.url.path.endswith("/api/health"):
        return httpx.Response(200, json={"status": "ok", "database": {"ok": True}})
    if request.url.path.endswith("/api/hotspots/near"):
        return httpx.Response(200, json={"count": 4})
    if request.url.path.endswith("/"):
        return httpx.Response(200, text='<meta name="youluan-api-path" content="/' + "x" * 43
                              + '"><script type="module" src="./assets/main.js"></script>')
    return httpx.Response(200, text="console.log('ready')", headers={"content-type": "text/javascript"})


def test_checks_real_data_and_website_script():
    paths = []
    def handle(request):
        paths.append(request.url.path)
        return website_response(request)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        launcher.check_versions(ADDRESS, client)
    assert len(paths) == 4
    assert paths[-1].endswith("/assets/main.js")


@pytest.mark.parametrize("broken", ["health", "near", "script", "website"])
def test_rejects_a_partially_working_deployment(broken):
    def handle(request):
        path = request.url.path
        if (broken == "health" and path.endswith("/health")
                or broken == "near" and path.endswith("/near")
                or broken == "script" and path.endswith(".js")
                or broken == "website" and path.endswith("/")):
            return httpx.Response(200, json={"status": "error"})
        return website_response(request)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(launcher.LaunchError):
            launcher.check_versions(ADDRESS, client)


def test_existing_services_are_not_started_again(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "LOG", tmp_path / "logs/events.jsonl")
    monkeypatch.setattr(launcher, "STATE", tmp_path / "run/status.json")
    monkeypatch.setattr(launcher, "ensure_database", lambda: None)
    monkeypatch.setattr(launcher, "ensure_website", lambda: None)
    monkeypatch.setattr(launcher.remote_access, "gateway_healthy", lambda: True)
    monkeypatch.setattr(launcher.remote_access, "wait_ready", lambda: True)
    monkeypatch.setattr(launcher, "verify", lambda: ADDRESS)
    def unexpected(*args):
        raise AssertionError("不能重啟既有服務")
    monkeypatch.setattr(launcher, "run_script", unexpected)
    launcher.start_versions(tmp_path / "平台")
    assert ADDRESS in (tmp_path / "平台/run/Android連線位址.txt").read_text(encoding="utf-8")
    assert ADDRESS not in launcher.LOG.read_text(encoding="utf-8")
    assert ADDRESS + "/" in (tmp_path / "平台/run/網頁版網址.txt").read_text(encoding="utf-8")
    assert json.loads(launcher.STATE.read_text())["websiteReady"] is True


def test_missing_database_is_not_initialized(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "database_ready", lambda: False)
    monkeypatch.setattr(launcher, "project_path", lambda value: tmp_path)
    monkeypatch.setattr(launcher, "env", lambda key, default=None: default)
    monkeypatch.setattr(launcher, "run_script", lambda *args: pytest.fail("不能建立或覆寫資料庫"))
    with pytest.raises(launcher.LaunchError, match="首次部署"):
        launcher.ensure_database()


def test_starts_only_existing_local_database(monkeypatch, tmp_path):
    (tmp_path / "PG_VERSION").write_text("18")
    ready = iter([False, True])
    monkeypatch.setattr(launcher, "database_ready", lambda: next(ready))
    monkeypatch.setattr(launcher, "project_path", lambda value: tmp_path)
    monkeypatch.setattr(launcher, "env", lambda key, default=None: default)
    calls = []
    monkeypatch.setattr(launcher, "run_script", lambda *args: calls.append(args))
    launcher.ensure_database()
    assert calls == [("localdb.py", "start")]


def test_failure_does_not_print_private_url(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(launcher, "LOG", tmp_path / "events.jsonl")
    monkeypatch.setattr(launcher, "STATE", tmp_path / "status.json")
    def failed(*args):
        raise httpx.ConnectError("Cannot connect to " + ADDRESS)
    monkeypatch.setattr(launcher, "execute", failed)
    assert launcher.safe_execute("status", tmp_path) is False
    assert ADDRESS not in capsys.readouterr().out
    assert ADDRESS not in launcher.LOG.read_text(encoding="utf-8")
    assert json.loads(launcher.STATE.read_text())["androidReady"] is False


def test_stop_does_not_stop_database(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(launcher, "run_script", lambda *args: calls.append(args))
    monkeypatch.setattr(launcher.remote_access, "gateway_healthy", lambda: False)
    monkeypatch.setattr(launcher, "STATE", tmp_path / "status.json")
    monkeypatch.setattr(launcher, "LOG", tmp_path / "events.jsonl")
    launcher.execute("stop", tmp_path)
    assert calls == [("remote_access.py", "stop")]


def test_gateway_uses_the_copied_website_and_api_port(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_gateway, "dotenv_values", lambda path: {
        "REMOTE_ACCESS_KEY": "x" * 43, "REMOTE_API_PORT": "8094", "FRONTEND_DIR": str(tmp_path)})
    captured = {}
    def create(secret, upstream, **kwargs):
        captured.update(upstream=upstream, **kwargs)
    monkeypatch.setattr(remote_gateway, "create_gateway", create)
    remote_gateway.gateway_app()
    assert captured == {"upstream": "http://127.0.0.1:8094", "web_root": tmp_path}


def test_gateway_default_paths_are_unchanged(monkeypatch):
    monkeypatch.setattr(remote_gateway, "dotenv_values", lambda path: {})
    captured = {}
    monkeypatch.setattr(remote_gateway, "create_gateway", lambda secret, upstream, **kwargs:
                        captured.update(upstream=upstream, **kwargs))
    remote_gateway.gateway_app()
    assert captured["upstream"] == "http://127.0.0.1:8092"
    assert captured["web_root"] == Path(remote_gateway.__file__).resolve().parents[2] / "web/dist"


def test_new_tunnel_retries_a_temporary_connection_error(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "LOG", tmp_path / "events.jsonl")
    attempts = []
    def verify():
        attempts.append(True)
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary")
        return ADDRESS
    monkeypatch.setattr(launcher, "verify", verify)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    assert launcher.verify_after_start() == ADDRESS
    assert len(attempts) == 2


def test_permanent_connection_failure_has_a_retry_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "LOG", tmp_path / "events.jsonl")
    attempts = []
    def failed():
        attempts.append(True)
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(launcher, "verify", failed)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    with pytest.raises(httpx.ConnectError):
        launcher.verify_after_start()
    assert len(attempts) == 12
