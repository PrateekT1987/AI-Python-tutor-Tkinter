#!/usr/bin/env python3
"""Production server for the browser console.

Serves the built Vite bundle from ``dist/`` and proxies
``/api/openrouter/*`` to OpenRouter with the server-side key, so no secret is
ever shipped to the browser.

Usage::

    npm run build
    python3 server.py                 # http://127.0.0.1:8000
    PORT=8080 python3 server.py

For a real deployment put this behind a TLS-terminating reverse proxy
(nginx, Caddy, a container platform). The stdlib server is intentionally
small: one process, one OpenRouter key, no sessions.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from config import (
    CHAT_COMPLETIONS_URL,
    MODEL,
    OPENROUTER_BASE_URL,
    provider_headers,
    validate_config,
)

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
PROXY_PREFIX = "/api/openrouter"
MAX_REQUEST_BYTES = 2 * 1024 * 1024  # 2 MiB is plenty for a chat history

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json",
}

log = logging.getLogger("python_tutor.server")


class TutorHandler(BaseHTTPRequestHandler):
    server_version = "PythonTutor/1.0"
    protocol_version = "HTTP/1.1"

    # ── routing ────────────────────────────────────────────────────────
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/api/config":
            self._send_json(200, {"model": MODEL})
            return
        self._serve_static(path)

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if not path.startswith(PROXY_PREFIX):
            self._send_json(404, {"error": "not found"})
            return
        self._proxy(path[len(PROXY_PREFIX):] or "/")

    # ── OpenRouter proxy ───────────────────────────────────────────────
    def _proxy(self, suffix: str) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return
        if length > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "request body too large"})
            return

        body = self.rfile.read(length) if length else b""
        target = OPENROUTER_BASE_URL + suffix
        request = urllib.request.Request(
            target,
            data=body,
            headers=provider_headers(),
            method="POST",
        )

        try:
            upstream = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self._send_bytes(exc.code, payload, "application/json")
            return
        except urllib.error.URLError as exc:
            log.warning("OpenRouter unreachable: %s", exc.reason)
            self._send_json(502, {"error": f"OpenRouter unreachable: {exc.reason}"})
            return

        with upstream:
            self.send_response(upstream.status)
            for key, value in upstream.headers.items():
                if key.lower() in ("transfer-encoding", "connection", "content-length"):
                    continue
                self.send_header(key, value)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            # Pass tokens through as they arrive instead of buffering.
            while True:
                chunk = upstream.read(4096)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

    # ── static files ───────────────────────────────────────────────────
    def _serve_static(self, path: str) -> None:
        if not os.path.isfile(os.path.join(DIST_DIR, "index.html")):
            self._send_json(
                503,
                {"error": "frontend not built - run 'npm run build' first"},
            )
            return

        if path in ("", "/"):
            path = "/index.html"

        safe = os.path.normpath(path.lstrip("/"))
        if safe.startswith("..") or os.path.isabs(safe):
            self._send_json(403, {"error": "forbidden"})
            return

        full = os.path.join(DIST_DIR, safe)
        if not os.path.isfile(full):
            # SPA fallback only for extension-less routes.
            if os.path.splitext(safe)[1]:
                self._send_json(404, {"error": "not found"})
                return
            full = os.path.join(DIST_DIR, "index.html")

        if not os.path.isfile(full):
            self._send_json(
                503,
                {"error": "frontend not built - run 'npm run build' first"},
            )
            return

        with open(full, "rb") as handle:
            data = handle.read()
        ext = os.path.splitext(full)[1].lower()
        self._send_bytes(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))

    # ── helpers ────────────────────────────────────────────────────────
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(status, body, "application/json")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    validate_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.isfile(os.path.join(DIST_DIR, "index.html")):
        print(
            "warning: dist/index.html not found; run 'npm run build' first.",
            file=sys.stderr,
        )

    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        raise SystemExit("PORT must be an integer")

    server = ThreadingHTTPServer((host, port), TutorHandler)
    print(f"Python Tutor browser console on http://{host}:{port} (model: {MODEL})")
    print(f"proxying /api/openrouter -> {CHAT_COMPLETIONS_URL.rsplit('/chat/', 1)[0]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
