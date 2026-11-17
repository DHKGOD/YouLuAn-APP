"""iPhone網站需通行碼，並且不再提供原生App／更新下載。"""
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.remote_gateway import create_gateway

KEY = 'website-test-' + 'x' * 40


@pytest.fixture
def site(tmp_path):
    (tmp_path/'index.html').write_text('<html><head></head><body>有路安</body></html>', encoding='utf8')
    (tmp_path/'assets').mkdir()
    (tmp_path/'assets/main.js').write_text('console.log("website")')
    (tmp_path/'private.env').write_text('private=not-public')
    (tmp_path/'YouLuAn.ipa').write_bytes(b'old-app')
    return tmp_path


def test_website_has_protected_entry_and_relative_api_configuration(site):
    with TestClient(create_gateway(KEY, web_root=site)) as client:
        assert client.get('/').status_code == 404
        assert client.get('/wrong/').status_code == 404
        redirect = client.get('/'+KEY, follow_redirects=False)
        assert redirect.status_code == 307 and redirect.headers['location'] == '/'+KEY+'/'
        home = client.get('/'+KEY+'/')
        assert home.status_code == 200
        assert 'text/html' in home.headers['content-type']
        assert f'name="youluan-api-path" content="/{KEY}"' in home.text
        assert home.headers['referrer-policy'] == 'no-referrer'
        assert client.get('/'+KEY+'/assets/main.js').text == 'console.log("website")'


@pytest.mark.parametrize('path', [
    '/private.env', '/YouLuAn.ipa', '/updates/revisions/4/index.html',
    '/assets/source.pem', '/assets/%2e%2e/private.env', '/api/admin/stats',
])
def test_website_never_becomes_a_private_file_or_ipa_server(site, path):
    with TestClient(create_gateway(KEY, web_root=site)) as client:
        response = client.get('/'+KEY+path, follow_redirects=False)
        assert response.status_code == 404
        assert 'not-public' not in response.text and 'old-app' not in response.text


def test_native_updates_are_retired_and_same_origin_browser_api_still_works(site):
    requests = []
    def backend(request):
        requests.append(request)
        return httpx.Response(200, json={'code': 'ABCDEF'})
    with TestClient(create_gateway(KEY, web_root=site, transport=httpx.MockTransport(backend)),
                    base_url='https://website.example') as client:
        assert client.get('/updates/stable.json').status_code == 410
        assert client.get('/updates/revisions/4/index.html').status_code == 404
        response = client.post('/'+KEY+'/api/routes', json={}, headers={'Origin': 'https://website.example'})
        assert response.status_code == 200
        assert len(requests) == 1
        assert client.post('/'+KEY+'/api/routes', json={}, headers={'Origin': 'https://other.example'}).status_code == 403
        assert client.get('/'+KEY+'/api/reports').status_code == 404
        assert client.post('/'+KEY+'/api/reports', json={}).status_code == 404
