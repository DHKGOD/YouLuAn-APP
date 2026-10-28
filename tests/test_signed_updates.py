"""外網只提供最新清單列出的更新檔，拒絕私人檔與損毀內容。"""
import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from backend.app.remote_gateway import create_gateway

KEY = 'update-test-' + 'x' * 40


@pytest.fixture
def release(tmp_path):
    asset = tmp_path / 'revisions/3/index.html'
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'<html>three tabs</html>')
    manifest = {'schema': 1, 'revision': 3, 'files': [
        {'path': 'index.html', 'size': asset.stat().st_size,
         'sha256': hashlib.sha256(asset.read_bytes()).hexdigest()}]}
    envelope = {'payload': base64.b64encode(json.dumps(manifest).encode()).decode(), 'signature': 'fixture'}
    (tmp_path/'stable.json').write_text(json.dumps(envelope))
    (tmp_path/'signing-key.pem').write_text('private fixture')
    return tmp_path, asset


def test_only_current_manifest_assets_are_downloadable(release):
    root, asset = release
    with TestClient(create_gateway(KEY, updates_root=root)) as client:
        assert client.get('/updates/stable.json').status_code == 200
        assert client.get('/updates/revisions/3/index.html').content == asset.read_bytes()
        for path in ['signing-key.pem', 'revisions/2/index.html', 'revisions/3/unknown.js',
                     'revisions/3/.env', 'revisions/3/%2e%2e/signing-key.pem']:
            assert client.get('/updates/' + path, follow_redirects=False).status_code == 404
        asset.write_bytes(b'changed')
        assert client.get('/updates/revisions/3/index.html').status_code == 404


def test_updates_are_disabled_unless_explicitly_configured():
    with TestClient(create_gateway(KEY)) as client:
        assert client.get('/updates/stable.json').status_code == 404


def test_cancelled_report_api_is_rejected_for_all_phone_origins():
    with TestClient(create_gateway(KEY)) as client:
        for origin in ['http://localhost', 'capacitor://localhost']:
            for method in ['GET', 'POST', 'OPTIONS']:
                assert client.request(method, f'/{KEY}/api/reports', headers={'Origin': origin}).status_code == 404
            response = client.options(f'/{KEY}/api/routes', headers={'Origin': origin})
            assert response.status_code == 204
            assert response.headers['access-control-allow-origin'] == origin
