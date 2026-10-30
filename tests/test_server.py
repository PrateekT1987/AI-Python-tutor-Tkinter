"""Tests for the static/proxy server used by the browser console."""

from __future__ import annotations

import http.client
import io
import json
import threading
import urllib.error
from http.server import ThreadingHTTPServer

import pytest

import server as srv


@pytest.fixture
def web(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>tutor</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "styles.css").write_text("body{}", encoding="utf-8")

    monkeypatch.setattr(srv, "DIST_DIR", str(dist))
    monkeypatch.setattr(srv, "MODEL", "test/model")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.TutorHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], dist
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def request(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_config_reports_model(web):
    port, _dist = web

    status, headers, body = request(port, "GET", "/api/config")

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"model": "test/model"}


def test_index_is_served(web):
    port, _dist = web

    status, headers, body = request(port, "GET", "/")

    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert body == b"<html>tutor</html>"


def test_assets_get_correct_content_type(web):
    port, _dist = web

    status, headers, body = request(port, "GET", "/assets/app.js")

    assert status == 200
    assert headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert body == b"console.log(1)"

    status, headers, _body = request(port, "GET", "/styles.css")

    assert status == 200
    assert headers["Content-Type"] == "text/css; charset=utf-8"


def test_missing_asset_is_404(web):
    port, _dist = web

    status, _headers, body = request(port, "GET", "/assets/missing.js")

    assert status == 404
    assert json.loads(body) == {"error": "not found"}


def test_extensionless_route_falls_back_to_index(web):
    port, _dist = web

    status, _headers, body = request(port, "GET", "/deep/route")

    assert status == 200
    assert body == b"<html>tutor</html>"


def test_path_traversal_is_forbidden(web):
    port, _dist = web

    status, _headers, _body = request(port, "GET", "/../etc/passwd")

    assert status == 403


def test_missing_dist_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "DIST_DIR", str(tmp_path / "empty"))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.TutorHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _headers, body = request(httpd.server_address[1], "GET", "/")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert status == 503
    assert "npm run build" in json.loads(body)["error"]


def test_unknown_post_path_is_404(web):
    port, _dist = web

    status, _headers, body = request(port, "POST", "/nope", body=b"{}")

    assert status == 404
    assert json.loads(body) == {"error": "not found"}


class FakeUpstream:
    def __init__(self, status=200, payload=b'{"ok":true}', headers=None):
        self.status = status
        self._payload = payload
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, size=-1):
        if size == -1:
            payload, self._payload = self._payload, b""
            return payload
        chunk, self._payload = self._payload[:size], self._payload[size:]
        return chunk


def test_proxy_forwards_body_and_headers(web, monkeypatch):
    port, _dist = web
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["auth"] = request.get_header("Authorization")
        captured["referer"] = request.get_header("Http-referer")
        return FakeUpstream(payload=b'{"choices":[]}')

    monkeypatch.setattr(srv.urllib.request, "urlopen", fake_urlopen)

    status, _headers, body = request(
        port,
        "POST",
        "/api/openrouter/chat/completions",
        body=b'{"model":"x"}',
        headers={"Content-Type": "application/json"},
    )

    assert status == 200
    assert body == b'{"choices":[]}'
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"] == b'{"model":"x"}'
    assert captured["auth"].startswith("Bearer ")


def test_proxy_passes_upstream_errors_through(web, monkeypatch):
    port, _dist = web

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error":"bad key"}'),
        )

    monkeypatch.setattr(srv.urllib.request, "urlopen", fake_urlopen)

    status, _headers, body = request(
        port, "POST", "/api/openrouter/chat/completions", body=b"{}"
    )

    assert status == 401
    assert body == b'{"error":"bad key"}'


def test_proxy_reports_unreachable_upstream(web, monkeypatch):
    port, _dist = web

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("dns failure")

    monkeypatch.setattr(srv.urllib.request, "urlopen", fake_urlopen)

    status, _headers, body = request(
        port, "POST", "/api/openrouter/chat/completions", body=b"{}"
    )

    assert status == 502
    assert "unreachable" in json.loads(body)["error"]


def test_proxy_rejects_oversized_body(web):
    port, _dist = web

    status, _headers, body = request(
        port,
        "POST",
        "/api/openrouter/chat/completions",
        body=b"",
        headers={"Content-Length": str(srv.MAX_REQUEST_BYTES + 1)},
    )

    assert status == 413
    assert json.loads(body) == {"error": "request body too large"}
