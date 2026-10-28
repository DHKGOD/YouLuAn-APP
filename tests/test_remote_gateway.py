"""外出入口的存取限制；使用假後端，不連資料庫或外部通道。"""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.remote_gateway import MAX_BODY, create_gateway

KEY = "gateway-test-" + "x" * 40


@pytest.fixture
def gateway():
    requests = []

    def backend(request):
        requests.append(request)
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "database": {
                "ok": True, "error": "private-database-connection", "version": "private-version"}})
        return httpx.Response(200, json={"path": request.url.path})

    app = create_gateway(KEY, transport=httpx.MockTransport(backend))
    with TestClient(app) as client:
        yield client, requests


@pytest.mark.parametrize("path", [
    "/api/reports", "/docs", "/.env", "/wrong/api/reports", "/錯誤/api/reports",
    f"/{KEY}/api/admin/stats", f"/{KEY}/api/reports", f"/{KEY}/openapi.json", f"/{KEY}/../docs",
])
def test_private_or_unauthenticated_paths_never_reach_backend(gateway, path):
    client, requests = gateway
    assert client.get(path, follow_redirects=False).status_code == 404
    assert requests == []


def test_api_query_is_forwarded_without_access_code_or_credentials(gateway):
    client, requests = gateway
    result = client.get(f"/{KEY}/api/hotspots/near?lat=25&lon=121&complete=true",
                        headers={"Cookie": "private=cookie", "Authorization": "Bearer private"})
    assert result.status_code == 200
    request = requests[0]
    assert str(request.url).startswith("http://127.0.0.1:8000/api/hotspots/near?")
    assert request.url.params["complete"] == "true"
    assert KEY not in str(request.url)
    assert "cookie" not in request.headers and "authorization" not in request.headers
    assert result.headers["cache-control"] == "no-store"


def test_phone_preflight_and_health_hide_private_backend_details(gateway):
    client, requests = gateway
    result = client.options(f"/{KEY}/api/routes", headers={"Origin": "http://localhost"})
    assert result.status_code == 204
    assert result.headers["access-control-allow-origin"] == "http://localhost"
    assert requests == []
    health = client.get(f"/{KEY}/api/health")
    assert health.json() == {"status": "ok", "database": {"ok": True}}
    assert "private" not in health.text


def test_unknown_browser_origin_is_rejected(gateway):
    client, requests = gateway
    assert client.get(f"/{KEY}/api/routes", headers={"Origin": "https://untrusted.invalid"}).status_code == 403
    assert requests == []


def test_route_json_and_request_limits(gateway):
    client, requests = gateway
    result = client.post(f"/{KEY}/api/routes", json={"lat": 25, "lon": 121})
    assert result.status_code == 200
    assert requests[0].content == b'{"lat":25,"lon":121}'
    requests.clear()
    assert client.post(f"/{KEY}/api/routes", content=b"x").status_code == 415
    assert client.post(f"/{KEY}/api/routes", content=b"x" * (MAX_BODY + 1),
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post(f"/{KEY}/api/health", json={}).status_code == 405
    assert requests == []


@pytest.mark.parametrize("failure", ["redirect", "exception", "server-error", "invalid-health"])
def test_backend_failure_never_leaks_details_or_follows_redirect(failure):
    requests = []

    def backend(request):
        requests.append(request)
        if failure == "exception":
            raise httpx.ConnectError("private-password-and-host")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://private.invalid"})
        if failure == "invalid-health":
            return httpx.Response(200, json=["private"])
        return httpx.Response(500, text="private-password-and-host")

    with TestClient(create_gateway(KEY, transport=httpx.MockTransport(backend))) as client:
        result = client.get(f"/{KEY}/api/health")
        assert result.status_code == 503
        assert "private" not in result.text
        assert len(requests) == 1


def test_rate_limit_does_not_forward_excess_requests():
    requests = []

    def backend(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    with TestClient(create_gateway(KEY, transport=httpx.MockTransport(backend), rate_limit=2)) as client:
        for _ in range(2):
            assert client.get(f"/{KEY}/api/meta").status_code == 200
        assert client.get(f"/{KEY}/api/meta").status_code == 429
        assert len(requests) == 2


def test_gateway_cannot_become_an_arbitrary_remote_proxy():
    for target in ["https://example.com", "http://127.0.0.1:8000/path", "http://user:password@127.0.0.1:8000"]:
        with pytest.raises(ValueError):
            create_gateway(KEY, target)
    with pytest.raises(ValueError):
        create_gateway("short")
