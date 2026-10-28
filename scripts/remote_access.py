"""Android外出連線：私密API入口＋Cloudflare臨時通道，不改路由器。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid

from dotenv import dotenv_values
import httpx

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run"
LOGS = ROOT / "logs"
STATE = RUN / "remote-access.json"
STOP = RUN / "remote-stop.json"
BINARY = ROOT / "tools/cloudflared.exe"
BINARY_SHA256 = "db4e4c413612a0916f3e1679d3caaf376f94911952d163028fb726fb2e0516a9"
GATEWAY_PORT = 8091
REMOTE_API_PORT = 8092


def values():
    return dotenv_values(ROOT / ".env")


def get_key():
    key = values().get("REMOTE_ACCESS_KEY", "") or ""
    if not key:
        key = secrets.token_urlsafe(32)
        with (ROOT / ".env").open("a", encoding="utf-8") as file:
            file.write("\n# 手機外出連線的私人通行碼，不要公開\nREMOTE_ACCESS_KEY=" + key + "\n")
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", key):
        raise SystemExit("REMOTE_ACCESS_KEY格式不正確")
    return key


def flags(detach=False):
    if os.name != "nt":
        return {}
    value = subprocess.CREATE_NO_WINDOW
    if detach:
        value |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    return {"creationflags": value}


def healthy(url):
    try:
        response = httpx.get(url, timeout=3, trust_env=False)
        return response.status_code == 200 and response.json().get("status") == "ok"
    except (httpx.HTTPError, ValueError):
        return False


def save(state):
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STATE)


def run():
    if not BINARY.is_file() or hashlib.sha256(BINARY.read_bytes()).hexdigest() != BINARY_SHA256:
        raise SystemExit("找不到已驗證的cloudflared；請依docs/remote-access.md準備工具")
    key = get_key()
    for port in [GATEWAY_PORT, REMOTE_API_PORT]:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(f"外出連線連接埠{port}已被使用，沒有覆蓋或終止其他程序")

    instance = uuid.uuid4().hex
    state = {"instance": instance, "pid": os.getpid(), "status": "starting", "url": ""}
    save(state)
    gateway = tunnel = api = None
    try:
        with (LOGS / "remote-gateway.log").open("ab") as gateway_log, \
                (LOGS / "remote-api.log").open("ab") as api_log, \
                (LOGS / "remote-tunnel.log").open("w", encoding="utf-8") as tunnel_log:
            # 外出模式用自己建立的 API，載入最新程式；既有區網服務與資料庫不停止。
            api = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "backend.app.main:app",
                "--host", "127.0.0.1", "--port", str(REMOTE_API_PORT), "--no-access-log",
                "--loop", "backend.app.runtime:windows_selector_loop" if os.name == "nt" else "auto"
            ], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=api_log, stderr=subprocess.STDOUT, **flags())
            for _ in range(60):
                if healthy(f"http://127.0.0.1:{REMOTE_API_PORT}/api/health"):
                    break
                if api.poll() is not None:
                    raise RuntimeError("外出API啟動失敗，請查看remote-api.log")
                time.sleep(.5)
            else:
                raise RuntimeError("資料庫尚未就緒，請先啟動start_server.bat")
            gateway = subprocess.Popen([
                sys.executable, "-m", "uvicorn", "backend.app.remote_gateway:gateway_app", "--factory",
                "--host", "127.0.0.1", "--port", str(GATEWAY_PORT), "--no-access-log",
                "--loop", "backend.app.runtime:windows_selector_loop" if os.name == "nt" else "auto"
            ], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=gateway_log, stderr=subprocess.STDOUT, **flags())
            for _ in range(60):
                if healthy(f"http://127.0.0.1:{GATEWAY_PORT}/{key}/api/health"):
                    break
                if gateway.poll() is not None:
                    raise RuntimeError("私密入口啟動失敗，請查看remote-gateway.log")
                time.sleep(.5)
            else:
                raise RuntimeError("私密入口尚未就緒")

            tunnel = subprocess.Popen([
                str(BINARY), "tunnel", "--no-autoupdate", "--protocol", "quic", "--url",
                f"http://127.0.0.1:{GATEWAY_PORT}"
            ], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=tunnel_log, stderr=subprocess.STDOUT, **flags())
            announced = False
            started_at = time.monotonic()
            connected = False
            while True:
                if STOP.exists():
                    try:
                        if json.loads(STOP.read_text()) == {"instance": instance}:
                            state["status"] = "stopped"
                            break
                    except (ValueError, OSError):
                        pass
                if gateway.poll() is not None or tunnel.poll() is not None or api.poll() is not None:
                    raise RuntimeError("外出通道已停止，請查看remote-gateway.log／remote-tunnel.log")
                if not connected:
                    text = (LOGS / "remote-tunnel.log").read_text(encoding="utf-8", errors="replace")
                    if "Registered tunnel connection" in text:
                        connected = True
                        state["status"] = "tunnel_connected"
                        save(state)
                    elif time.monotonic() - started_at > 120:
                        raise RuntimeError("兩分鐘內無法建立外網連線，請查看remote-tunnel.log")
                if not announced:
                    match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
                    if match:
                        state.update(status="tunnel_connected" if connected else "connecting",
                                     url=match.group() + "/" + key)
                        save(state)
                        (RUN / "手機外出連線.txt").write_text(
                            "App設定的伺服器位址（含私人通行碼，不要公開）：\n" + state["url"] +
                            "\n\n電腦與外出通道要保持運作；重啟通道後網址會改變。\n", encoding="utf-8")
                        announced = True
                        print("外出網址已產生；連通測試尚未完成。", flush=True)
                time.sleep(1)
    except Exception as error:
        state.update(status="failed", error=str(error))
        print(str(error), flush=True)
    finally:
        # 只管理這一輪自己啟動的子程序，不停止原本的區網API或資料庫。
        for child in [tunnel, gateway, api]:
            if child and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
        state["url"] = "" if state["status"] == "failed" else state["url"]
        save(state)


def main():
    RUN.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "run":
        run()
    elif command == "start":
        key = get_key()
        if healthy(f"http://127.0.0.1:{GATEWAY_PORT}/{key}/api/health"):
            print("外出入口已在執行，請用status查看通道狀態")
            return
        with (LOGS / "remote-supervisor.log").open("ab") as log:
            subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "run"], cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **flags(True))
        print("已啟動外出連線準備，請稍候再查看status")
    elif command == "stop":
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        if state.get("instance"):
            STOP.write_text(json.dumps({"instance": state["instance"]}), encoding="utf-8")
            print("已要求停止本專案的外出通道；API與資料庫保留")
    elif command == "status":
        if not STATE.exists():
            print("尚未啟動外出連線")
            return
        state = json.loads(STATE.read_text(encoding="utf-8"))
        print("狀態：" + state["status"])
        if state.get("url"):
            print("私人連線位址存放在run/手機外出連線.txt；不要上傳GitHub")
    else:
        raise SystemExit("使用方式：remote_access.py start／status／stop")


if __name__ == "__main__":
    main()
