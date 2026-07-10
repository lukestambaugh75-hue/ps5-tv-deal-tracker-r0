#!/usr/bin/env python3
"""Check the public GitHub Pages dashboard."""
import argparse
import json
import os
import sys
import urllib.request

try:
    from .audience_guard import validate_dashboard_html
except ImportError:
    from audience_guard import validate_dashboard_html


PUBLIC_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_INDEX = os.path.join(ROOT, "index.html")
DATA_PATH = os.path.join(ROOT, "data", "deals.json")


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_body(local=False, input_path=LOCAL_INDEX):
    if local:
        with open(input_path, encoding="utf-8") as f:
            return f.read(), "local"
    with urllib.request.urlopen(PUBLIC_URL, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status: {response.status}")
        return body, response.status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--input", default=LOCAL_INDEX)
    parser.add_argument("--data", default=DATA_PATH)
    args = parser.parse_args()
    result = {
        "url": os.path.abspath(args.input) if args.local else PUBLIC_URL,
        "source": "local" if args.local else "public",
        "ok": False,
        "status": None,
    }
    try:
        body, status = _read_body(local=args.local, input_path=args.input)
        result["status"] = status
        if "PS5 and 65-inch TV Deal Tracker" not in body:
            raise AssertionError("required dashboard title is missing")
        validate_dashboard_html(body, _read_json(args.data))
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
