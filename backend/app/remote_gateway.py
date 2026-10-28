"""外出連線入口：只有持有私密路徑的 App 能呼叫指定 API。"""
from __future__ import annotations

from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hmac
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import httpx
from .signed_updates import update_asset

MAX_BODY = 256 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
ORIGINS = {"http://localhost", "https://localhost", "capacitor://localhost"}
GET_PATHS = re.compile(
    r"api/(?:health|meta|hotspots/(?:near|top|areas|\d+/report)|"
    r"ai/(?:models|hotspots/\d+/causes|predictions/\d+)|geo/(?:search|route)|"
    r"weather/now|routes/[A-Za-z0-9]{6})"
)
POST_PATHS = {"api/routes", "api/hotspots/route"}


def create_gateway(secret: str, upstream: str = "http://127.0.0.1:8000", *,
                   transport=None, rate_limit: int = 120, updates_root: Path | None = None) -> FastAPI:
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", secret):
        raise ValueError("外出連線通行碼尚未設定")
    target = urlsplit(upstream)
    if (target.scheme != "http" or target.hostname != "127.0.0.1" or
            target.username or target.password or target.path or target.query or target.fragment):
        raise ValueError("外出入口只能連到本機 API")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(transport=transport, trust_env=False,
                                     follow_redirects=False, timeout=45) as client:
            app.state.client = client
            yield

    gateway = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    gateway.router.redirect_slashes = False
    recent = defaultdict(deque)

    @gateway.get("/updates/{asset_path:path}")
    async def signed_update(asset_path: str):
        if updates_root is None:
            return Response(status_code=404)
        try:
            data = update_asset(updates_root, asset_path)
            return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})
        except (OSError, ValueError, KeyError, StopIteration, TypeError):
            return Response(status_code=404)

    @gateway.api_route("/{access_code}/{path:path}", methods=["GET", "POST", "OPTIONS"])
    async def forward(access_code: str, path: str, request: Request):
        if not hmac.compare_digest(access_code.encode(), secret.encode()):
            return Response(status_code=404)
        allowed = bool(GET_PATHS.fullmatch(path)) or path in POST_PATHS
        if not allowed:
            return Response(status_code=404)

        # 不轉送瀏覽器 Cookie、Authorization 或任意自訂標頭。
        origin = request.headers.get("origin", "")
        headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
        if origin:
            if origin not in ORIGINS:
                return Response(status_code=403)
            headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
        if request.method == "OPTIONS":
            headers.update({"Access-Control-Allow-Methods": "GET, POST",
                            "Access-Control-Allow-Headers": "Content-Type"})
            return Response(status_code=204, headers=headers)
        if (request.method == "GET" and not GET_PATHS.fullmatch(path) or
                request.method == "POST" and path not in POST_PATHS):
            return Response(status_code=405, headers=headers)

        # 入口只綁本機，這個IP標頭由外面的Cloudflare通道提供。
        visitor = request.headers.get("cf-connecting-ip", "shared")[:64]
        now = time.monotonic()
        for old_visitor in list(recent):
            while recent[old_visitor] and now - recent[old_visitor][0] >= 60:
                recent[old_visitor].popleft()
            if not recent[old_visitor]:
                del recent[old_visitor]
        if visitor not in recent and len(recent) >= 256:
            return Response(status_code=429, headers=headers)
        calls = recent[visitor]
        if len(calls) >= rate_limit:
            return Response(status_code=429, headers={**headers, "Retry-After": "60"})
        calls.append(now)

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return Response(status_code=413, headers=headers)
        if request.method == "POST" and request.headers.get("content-type", "").split(";")[0] != "application/json":
            return Response(status_code=415, headers=headers)

        # 用固定的本機來源建立URL，不接受使用者指定轉送主機。
        url = httpx.URL(upstream).copy_with(path="/" + path, query=request.url.query.encode())
        try:
            async with request.app.state.client.stream(
                request.method, url, content=bytes(body),
                headers={"Content-Type": "application/json"} if request.method == "POST" else {}
            ) as result:
                if result.status_code >= 500 or 300 <= result.status_code < 400:
                    return JSONResponse({"detail": "伺服器暫時無法處理，請稍後重試"},
                                        status_code=503, headers=headers)
                data = bytearray()
                async for chunk in result.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE:
                        return Response(status_code=502, headers=headers)
                if path == "api/health" and result.status_code == 200:
                    health = httpx.Response(200, content=bytes(data)).json()
                    if not isinstance(health, dict):
                        raise ValueError("Invalid health response")
                    database = health.get("database")
                    database = database if isinstance(database, dict) else {}
                    return JSONResponse({"status": health.get("status", "error"),
                                         "database": {"ok": bool(database.get("ok"))}},
                                        headers=headers)
                if "application/json" not in result.headers.get("content-type", ""):
                    return Response(status_code=502, headers=headers)
                return Response(bytes(data), status_code=result.status_code,
                                media_type="application/json", headers=headers)
        except (httpx.HTTPError, ValueError):
            return JSONResponse({"detail": "電腦上的服務暫時無法連線"}, status_code=503, headers=headers)

    return gateway


def gateway_app():
    root = Path(__file__).resolve().parents[2]
    values = dotenv_values(root / ".env")
    updates_root = values.get("IOS_UPDATES_DIR", "")
    return create_gateway(values.get("REMOTE_ACCESS_KEY", ""),
                          "http://127.0.0.1:8092",
                          updates_root=Path(updates_root) if updates_root else None)
