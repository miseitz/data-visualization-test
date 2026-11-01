"""
Rebuild the dashboard data and open it in your browser.

Handy for running from an IDE such as Spyder: open this file and press F5.
It
  1. runs build_data.py (CSV -> site/data/*.json)
  2. starts a local web server for the site/ folder
  3. opens http://localhost:8000 in your default browser

The server keeps running until you stop it:
  - Spyder: click the red square ("Interrupt kernel") or press Ctrl+C in the console
  - terminal: Ctrl+C
"""

import functools
import http.server
import socketserver
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE.parent / "site"
PORT = 8000

sys.path.insert(0, str(HERE))
import build_data  # noqa: E402  (imported after the path tweak on purpose)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep the console readable
        pass


class Server(socketserver.TCPServer):
    allow_reuse_address = True  # lets you re-run the script right after stopping it


def main() -> None:
    build_data.main()

    handler = functools.partial(QuietHandler, directory=str(SITE))
    try:
        httpd = Server(("127.0.0.1", PORT), handler)
    except OSError:
        url = f"http://localhost:{PORT}"
        print(f"Port {PORT} is already in use; the dashboard is probably still running at {url}")
        webbrowser.open(url)
        return

    url = f"http://localhost:{PORT}"
    print(f"Dashboard running at {url}  (interrupt the kernel / press Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("Server stopped.")


if __name__ == "__main__":
    main()
