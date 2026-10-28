"""驗證外部HTTPS入口，輸出不包含私人位址或回傳的個人資料。"""
from pathlib import Path
import json
import ssl

import httpx
import truststore

ROOT = Path(__file__).resolve().parents[1]


def main():
    state = json.loads((ROOT / "run/remote-access.json").read_text(encoding="utf-8"))
    base = state.get("url", "")
    if not base.startswith("https://"):
        raise ValueError("外出網址尚未產生")
    origin = base.rsplit("/", 1)[0]
    with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=25, trust_env=False) as client:
        health = client.get(base + "/api/health")
        assert health.status_code == 200 and health.json() == {"status": "ok", "database": {"ok": True}}, "health"
        near = client.get(base + "/api/hotspots/near", params={"lat": 25.0363, "lon": 121.4318, "radius": 500})
        assert near.status_code == 200 and near.json()["count"] > 0, "nearby"
        models = client.get(base + "/api/ai/models")
        assert models.status_code == 200 and len(models.json()) > 0, "models"
        for path in ["/api/health", "/.env", "/api/reports"]:
            assert client.get(origin + path).status_code == 404, "unauthorized"
        assert client.get(base + "/api/admin/stats").status_code == 404, "admin"
        for method in ["GET", "POST"]:
            assert client.request(method, base + "/api/reports").status_code == 404, "removed-reports"
        preflight = client.options(base + "/api/routes", headers={"Origin": "http://localhost",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        assert preflight.status_code == 204, "android-cors"
        iphone = client.options(base + "/api/routes", headers={"Origin": "capacitor://localhost",
            "Access-Control-Request-Method": "POST"})
        assert iphone.status_code == 204, "iphone-cors"
    report = {"httpsVerified": True, "databaseHealthy": True, "nearbyCount": near.json()["count"],
              "modelsAvailable": True, "unauthorizedDenied": True, "adminDenied": True, "androidPreflight": True,
              "iphonePreflight": True, "reportingRemoved": True}
    (ROOT / "logs/remote-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    try:
        main()
    except (httpx.HTTPError, AssertionError, ValueError, OSError) as error:
        # HTTP例外可能帶完整URL，不能直接印出而洩漏路徑通行碼。
        print("外網驗證失敗：" + type(error).__name__)
        raise SystemExit(1)
