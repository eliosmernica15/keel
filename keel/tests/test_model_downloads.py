"""B1.6 — resumable, integrity-verified model downloads."""

from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from keel import model_downloads
from keel.cli.main import main

PAYLOAD = bytes(range(256)) * 40


class RangeHandler(BaseHTTPRequestHandler):
    payload = PAYLOAD

    def do_GET(self):
        header = self.headers.get("Range")
        if header:
            start = int(header.split("=", 1)[1].split("-", 1)[0])
            body = self.payload[start:]
            self.send_response(206)
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(self.payload) - 1}/{len(self.payload)}")
        else:
            body = self.payload
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    handler = RangeHandler
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/model.bin"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_fresh_download_verifies_sha256(tmp_path, server):
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    dest = tmp_path / "model.bin"
    result = model_downloads.download(server, dest, sha256=digest,
                                      allow_http=True)
    assert result.read_bytes() == PAYLOAD
    assert not model_downloads.part_path(dest).exists()


def test_download_resumes_partial_file(tmp_path, server):
    dest = tmp_path / "model.bin"
    part = model_downloads.part_path(dest)
    part.write_bytes(PAYLOAD[:1000])
    model_downloads.download(server, dest,
                             sha256=hashlib.sha256(PAYLOAD).hexdigest(),
                             allow_http=True)
    assert dest.read_bytes() == PAYLOAD


def test_bad_checksum_removes_staging(tmp_path, server):
    dest = tmp_path / "model.bin"
    with pytest.raises(model_downloads.DownloadError, match="integrity"):
        model_downloads.download(server, dest, sha256="0" * 64,
                                 allow_http=True)
    assert not dest.exists()
    assert not model_downloads.part_path(dest).exists()


def test_http_requires_opt_in(tmp_path, server):
    with pytest.raises(model_downloads.DownloadError, match="allow_http"):
        model_downloads.download(server, tmp_path / "model.bin")


def test_cli_model_download(tmp_path, server):
    dest = tmp_path / "model.bin"
    digest = hashlib.sha256(PAYLOAD).hexdigest()
    assert main(["model", "download", server, "--dest", str(dest),
                 "--sha256", digest, "--allow-http"]) == 0
    assert dest.read_bytes() == PAYLOAD
