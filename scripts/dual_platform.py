"""Android App 與通用網頁版的共用啟動工具。"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit
import webbrowser

import httpx
import psycopg
import truststore
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("YOULUAN_BUNDLE") == "1":
    load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))
from scripts import remote_access  # noqa: E402
from scripts.common import database_url, env, project_path  # noqa: E402

LOG = ROOT / "logs/dual-platform.jsonl"
STATE = ROOT / "run/dual-platform-status.json"


class LaunchError(Exception):
    pass


def record(event: str) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                               "event": event}, ensure_ascii=False) + "\n")


def run_script(name: str, *args: str) -> None:
    # 子程序輸出留在本機，主畫面只顯示啟動步驟。
    output = ROOT / "logs/dual-platform-services.log"
    output.parent.mkdir(exist_ok=True)
    with output.open("a", encoding="utf-8") as file:
        file.write(f"\n{datetime.now().isoformat()} {name} {' '.join(args)}\n")
        file.flush()
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / name), *args],
                                cwd=ROOT, stdout=file, stderr=subprocess.STDOUT,
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                **remote_access.flags())
    if result.returncode:
        raise LaunchError(f"{name} 執行失敗，請查看共用服務裡的logs/dual-platform-services.log。")


@contextmanager
def startup_lock():
    path = ROOT / "run/dual-platform.lock"
    path.parent.mkdir(exist_ok=True)
    with path.open("a+b") as file:
        if file.tell() == 0:
            file.write(b"0")
            file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise LaunchError("另一個視窗正在啟動，請稍後再檢查狀態。") from None
        else:
            import fcntl
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise LaunchError("另一個視窗正在啟動，請稍後再檢查狀態。") from None
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file, fcntl.LOCK_UN)


def database_ready() -> bool:
    try:
        with psycopg.connect(database_url(), connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def ensure_database() -> None:
    if database_ready():
        return
    if env("DB_MODE", "local") != "local":
        raise LaunchError("無法連到設定的資料庫，請先確認資料庫主機。")
    data = project_path(env("PGDATA", "db/pgdata"))
    if not (data / "PG_VERSION").is_file():
        raise LaunchError("尚未完成首次部署，請先依README建立資料庫；這個工具不會重建資料。")
    run_script("localdb.py", "start")
    if not database_ready():
        raise LaunchError("資料庫啟動後仍無法連線，請查看啟動紀錄。")


def ensure_website() -> None:
    website = project_path(env("FRONTEND_DIR", "web/dist"))
    frontend = website.parent
    if (website / "index.html").is_file():
        return
    npm = shutil.which("npm")
    if not npm or not (frontend / "node_modules").is_dir():
        raise LaunchError("尚未準備網站，請先依README安裝前端套件並建置。")
    with (ROOT / "logs/dual-platform-services.log").open("a", encoding="utf-8") as file:
        result = subprocess.run([npm, "run", "build"], cwd=frontend,
                                stdout=file, stderr=subprocess.STDOUT, **remote_access.flags())
    if result.returncode or not (website / "index.html").is_file():
        raise LaunchError("網站建置失敗，請查看啟動紀錄。")


def current_address() -> str:
    address = remote_access.read_state().get("url", "")
    if not isinstance(address, str):
        raise LaunchError("尚未取得可用的外出位址。")
    parsed = urlsplit(address)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_-]{40,128}", parsed.path)):
        raise LaunchError("尚未取得可用的外出位址。")
    return address


def check_versions(address: str, client: httpx.Client) -> None:
    health = client.get(address + "/api/health")
    health_data = health.json() if health.status_code == 200 else None
    database = health_data.get("database") if isinstance(health_data, dict) else None
    if (not isinstance(database, dict) or health_data.get("status") != "ok"
            or database.get("ok") is not True):
        raise LaunchError("Android資料連線未通過，請稍後再檢查。")
    nearby = client.get(address + "/api/hotspots/near",
                        params={"lat": 25.0363, "lon": 121.4318, "radius": 500})
    nearby_data = nearby.json() if nearby.status_code == 200 else None
    count = nearby_data.get("count") if isinstance(nearby_data, dict) else None
    if not isinstance(count, int) or count < 1:
        raise LaunchError("Android路口資料讀取失敗，請查看啟動紀錄。")
    page = client.get(address + "/")
    api_path = urlsplit(address).path
    if page.status_code != 200 or f'name="youluan-api-path" content="{api_path}"' not in page.text:
        raise LaunchError("網頁版入口未通過，請查看啟動紀錄。")
    script = re.search(r'<script\b[^>]*\bsrc="([^"]+)"', page.text)
    asset = urljoin(address + "/", script.group(1)) if script else ""
    if not asset.startswith(address + "/assets/"):
        raise LaunchError("網頁版缺少正確的程式檔，請重新建置網站。")
    response = client.get(asset)
    if response.status_code != 200 or "javascript" not in response.headers.get("content-type", ""):
        raise LaunchError("網頁版程式載入失敗，請查看啟動紀錄。")


def verify() -> str:
    if not remote_access.gateway_healthy():
        raise LaunchError("共用服務目前沒有正常回應，請選擇重新啟動。")
    address = current_address()
    with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=20,
                      trust_env=False) as client:
        check_versions(address, client)
    return address


def verify_after_start() -> str:
    for attempt in range(12):
        try:
            return verify()
        except (LaunchError, httpx.HTTPError, ValueError) as error:
            record("waiting_public_connection_" + type(error).__name__)
            if attempt == 11:
                raise
            print("外出位址剛建立，稍候重新確認…", flush=True)
            time.sleep(5)
    raise LaunchError("外出連線仍未就緒。")


def save_status(ready: bool) -> None:
    STATE.parent.mkdir(exist_ok=True)
    data = {"checkedAt": datetime.now().isoformat(timespec="seconds"),
            "androidReady": ready, "websiteReady": ready}
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def save_addresses(workspace: Path, address: str) -> None:
    # 位址含私人通行碼，只寫入本機整合資料夾，不放進來源範本。
    web_text = "手機、平板或電腦直接用瀏覽器開啟：\n" + address + "/"
    for folder, filename, text in [
        ("run", "Android連線位址.txt", "貼到 Android App 的伺服器設定，再按測試並儲存：\n" + address),
        ("run", "網頁版網址.txt", web_text),
    ]:
        target = workspace / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / filename).write_text(text + "\n\n請勿公開；重啟外出通道可能換網址。\n", encoding="utf-8")


def show_addresses(address: str) -> None:
    print("\nAndroid伺服器位址：\n" + address)
    print("\n網頁版網址（手機、平板與電腦）\n" + address + "/")
    print("\n以上是私人位址，請勿公開。電腦要保持開機、連網且不要睡眠。")


def start_versions(workspace: Path) -> str:
    record("start_requested")
    with startup_lock():
        print("[1/3] 檢查共用資料庫與網站…", flush=True)
        ensure_database()
        ensure_website()
        print("[2/3] 啟用 Android App 與網頁版的共用連線…", flush=True)
        if not remote_access.gateway_healthy():
            run_script("remote_access.py", "start")
        # 現有入口正常時直接沿用，不重啟通道或改變手機的位址。
        if not remote_access.wait_ready():
            raise LaunchError("外出通道尚未就緒，請查看共用服務的logs/remote-supervisor.log。")
        print("[3/3] 從外網檢查資料讀取與網站程式…", flush=True)
        address = verify_after_start()
        save_addresses(workspace, address)
        save_status(True)
        record("both_versions_verified")
    print("\nAndroid 資料服務與網頁版均已就緒。")
    show_addresses(address)
    return address


def execute(command: str, workspace: Path) -> None:
    if command == "start":
        start_versions(workspace)
    elif command in {"status", "open", "links"}:
        address = verify()
        save_addresses(workspace, address)
        save_status(True)
        record("status_verified")
        if command == "open":
            if not webbrowser.open(address + "/"):
                raise LaunchError("無法自動開瀏覽器，請用最上層「網頁版網址.txt」的網址開啟。")
        else:
            print("Android 資料連線與網頁版檢查正常。")
            show_addresses(address)
    elif command == "stop":
        run_script("remote_access.py", "stop")
        for _ in range(20):
            if not remote_access.gateway_healthy():
                save_status(False)
                record("external_connection_stopped")
                print("兩個版本的外出連線已停止；資料庫及原有區網服務保留。")
                return
            time.sleep(0.5)
        raise LaunchError("已送出停止要求，服務仍在結束中，請稍後檢查狀態。")
    elif command == "logs":
        if LOG.is_file():
            print("\n".join(LOG.read_text(encoding="utf-8").splitlines()[-12:]))
        print("詳細服務紀錄：" + str(ROOT / "logs/dual-platform-services.log"))


def safe_execute(command: str, workspace: Path) -> bool:
    try:
        execute(command, workspace)
        return True
    except (LaunchError, httpx.HTTPError, ValueError, OSError) as error:
        save_status(False)
        record("operation_failed_" + command)
        # HTTP例外會附上完整私人位址，所以不能直接輸出例外內容。
        message = str(error) if isinstance(error, LaunchError) else "連線或檔案操作失敗，請檢查網路與啟動紀錄。"
        print("\n尚未完成：" + message)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="menu",
                        choices=["menu", "start", "status", "open", "links", "logs", "stop"])
    parser.add_argument("--workspace", type=Path, default=ROOT)
    args = parser.parse_args()
    LOG.parent.mkdir(exist_ok=True)
    if args.command != "menu":
        return 0 if safe_execute(args.command, args.workspace) else 1
    print("有路安｜Android App＋網頁版\n")
    safe_execute("start", args.workspace)
    choices = {"1": "start", "2": "status", "3": "open", "4": "links", "5": "logs", "6": "stop"}
    while True:
        print("\n1 重新啟動／確認   2 檢查狀態   3 電腦預覽網站")
        print("4 顯示連線網址    5 查看紀錄   6 停止兩邊的外出連線")
        print("0 關閉工具（服務繼續執行）")
        try:
            choice = input("請選擇：").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if choice == "0":
            return 0
        if choice in choices:
            safe_execute(choices[choice], args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
