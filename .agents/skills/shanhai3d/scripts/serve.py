#!/usr/bin/env python3
"""Serve Shanhaiworld locally without exposing secrets or production records."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


BLOCKED_PARTS = {".agents", ".env", ".git", "production"}


class SafeStaticHandler(SimpleHTTPRequestHandler):
    def _is_blocked(self) -> bool:
        path = PurePosixPath(unquote(urlsplit(self.path).path))
        return any(part.startswith(".") or part in BLOCKED_PARTS for part in path.parts)

    def _reject_or_serve(self, method: str) -> None:
        if self._is_blocked():
            self.send_error(404, "File not found")
            return
        getattr(super(), method)()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._reject_or_serve("do_GET")

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        self._reject_or_serve("do_HEAD")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely serve the Shanhaiworld project.")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).expanduser().resolve()

    def handler(*handler_args, **handler_kwargs):
        return SafeStaticHandler(*handler_args, directory=str(root), **handler_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Shanhaiworld: http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
