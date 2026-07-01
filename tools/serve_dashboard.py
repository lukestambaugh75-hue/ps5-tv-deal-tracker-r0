#!/usr/bin/env python3
"""Serve the dashboard locally and open it in the browser."""
import argparse
import http.server
import os
import socketserver
import subprocess


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    url = f"http://127.0.0.1:{args.port}/index.html"
    if not args.no_browser:
        subprocess.run(["open", url], check=False)
    with socketserver.TCPServer(("127.0.0.1", args.port), http.server.SimpleHTTPRequestHandler) as httpd:
        print(url)
        httpd.serve_forever()


if __name__ == "__main__":
    main()

