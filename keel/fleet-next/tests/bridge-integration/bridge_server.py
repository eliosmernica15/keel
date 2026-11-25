"""REAL Python fleet bridge launcher for bridge-integration tests.

This starts the authoritative bridge from THIS worktree's src/keel (never the
globally installed copy) with a throwaway token and a disposable state root.
It is a test harness only: no backend source is modified. The only addition is
a token-free /__bridge_ready probe used by Playwright's webServer readiness
check; every other request is handled by the unmodified keel.webapp handler.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# tests/bridge-integration/bridge_server.py -> <worktree>/keel/src/keel
SRC = Path(__file__).resolve().parents[3] / "src"
sys.path.insert(0, str(SRC))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    # webapp._TOKEN and settings.default_state_root() read these at import /
    # call time, so set them before importing keel.webapp.
    import os

    os.environ["KEEL_TOKEN"] = args.token
    os.environ["KEEL_STATE_DIR"] = args.state

    state = Path(args.state)
    if state.exists():
        shutil.rmtree(state, ignore_errors=True)
    state.mkdir(parents=True, exist_ok=True)

    from keel import webapp  # noqa: E402  (path/bootstrap set above)

    server = webapp.make_server(args.port)
    base_handler = server.RequestHandlerClass

    class ReadyHandler(base_handler):  # type: ignore[misc,valid-type]
        """Add only a readiness probe; delegate everything else to the bridge."""

        def do_GET(self):  # noqa: N802
            if self.path.split("?", 1)[0] == "/__bridge_ready":
                body = b'{"ok":true,"source":"real-python-fleet-bridge"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

    server.RequestHandlerClass = ReadyHandler
    webapp.prepare_runtime()
    print(
        f"bridge ready on 127.0.0.1:{args.port} "
        f"(state={state}, token={args.token[:6]}...)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        webapp.shutdown_runtime(server)
        server.server_close()


if __name__ == "__main__":
    main()
