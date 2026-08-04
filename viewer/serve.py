#!/usr/bin/env python3
"""Serve this repository read-only on localhost so the viewer can fetch the
frozen artifacts.

Browsers refuse cross-origin ``file://`` fetches and do not expose
``crypto.subtle`` outside a secure context, so opening ``index.html`` off
the disk would show an empty viewer with hash verification disabled.  This
server exists only to remove that obstacle.

It is deliberately minimal and read-only:

* only ``GET`` and ``HEAD`` are answered; every other method gets 405,
* nothing is ever written, deleted, or executed,
* paths are resolved inside the repository root and nowhere else,
* ``.jsonl`` and ``.mjs`` get sensible content types.

Usage::

    python3 viewer/serve.py                # serve and open the viewer
    python3 viewer/serve.py --port 9000    # different port
    python3 viewer/serve.py --no-open      # do not launch a browser
"""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8765


class ViewerServer(http.server.ThreadingHTTPServer):
    """Threaded on purpose.

    A browser opens several keep-alive connections and the viewer fetches
    dozens of artifact files per run; a single-threaded server deadlocks on
    the first idle connection and the page never finishes loading.
    """

    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        """A browser that navigates away mid-download drops the socket.
        That is normal, not a server fault; anything else still surfaces."""
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class ReadOnlyHandler(http.server.SimpleHTTPRequestHandler):
    """``SimpleHTTPRequestHandler`` with writes and unknown methods off."""

    protocol_version = 'HTTP/1.1'

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript',
        '.mjs': 'text/javascript',
        '.json': 'application/json',
        '.jsonl': 'application/x-ndjson',
        '.md': 'text/markdown; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8',
        '.css': 'text/css',
    }

    def do_POST(self):  # noqa: N802 - stdlib naming
        self.send_error(405, 'this server is read-only')

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    def end_headers(self):
        # The artifacts are frozen; a stale cache would be a lie.
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, fmt, *args):
        if os.environ.get('VIEWER_SERVE_QUIET'):
            return
        sys.stderr.write(f'{self.address_string()} {fmt % args}\n')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--no-open', action='store_true',
                        help='do not launch a browser')
    args = parser.parse_args(argv)

    handler = functools.partial(ReadOnlyHandler, directory=str(REPO_ROOT))
    url = f'http://{args.host}:{args.port}/viewer/index.html'
    with ViewerServer((args.host, args.port), handler) as httpd:
        print(f'serving {REPO_ROOT} read-only')
        print(f'viewer: {url}')
        print('press Ctrl-C to stop')
        if not args.no_open:
            try:
                webbrowser.open(url)
            except Exception:  # pragma: no cover - headless machines
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nstopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
