"""啟動提示不能把舊狀態檔視為目前已可連線。"""
import importlib.util
import json
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "remote_startup", Path(__file__).resolve().parents[1] / "scripts/remote_access.py")
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


def test_old_connected_record_cannot_hide_a_stopped_gateway(monkeypatch, tmp_path, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"status": "tunnel_connected", "url": "https://old.invalid/private"}))
    monkeypatch.setattr(remote, "STATE", state)
    monkeypatch.setattr(remote, "gateway_healthy", lambda: False)
    remote.show_status()
    output = capsys.readouterr().out
    assert "沒有正常回應" in output
    assert "啟動外出連線.bat" in output
    assert "old.invalid" not in output


def test_wait_does_not_accept_old_record_when_gateway_is_down(monkeypatch):
    monkeypatch.setattr(remote, "read_state", lambda: {"status": "tunnel_connected", "url": "https://old.invalid"})
    monkeypatch.setattr(remote, "gateway_healthy", lambda: False)
    times = iter([0, 0, 2])
    monkeypatch.setattr(remote.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(remote.time, "sleep", lambda seconds: None)
    assert remote.wait_ready(timeout=1) is False


def test_wait_accepts_ready_gateway_without_starting_or_stopping_processes(monkeypatch):
    monkeypatch.setattr(remote, "read_state", lambda: {"status": "tunnel_connected", "url": "https://test.invalid"})
    monkeypatch.setattr(remote, "gateway_healthy", lambda: True)
    assert remote.wait_ready(timeout=1) is True
