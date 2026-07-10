#!/usr/bin/env python3
"""Verify required dashboard text locally or from the public URL."""
import argparse
import json
import os
import sys
import urllib.request

try:
    from .audience_guard import validate_outputs
except ImportError:
    from audience_guard import validate_outputs


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_INDEX = os.path.join(ROOT, "index.html")
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
EMAIL_PATH = os.path.join(ROOT, "out", "latest-email.json")
PUBLIC_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
REQUIRED = [
    "PS5 and 65-inch TV Deal Tracker",
    "Best Buy Today",
    "Current Retailer Rows",
    "Price History",
    "Evidence Guardrails",
]
FORBIDDEN = [
    "Andante",
    "8826",
    "Main Dashboard",
    "Deal Trackers",
    "daily-dashboards-public-safe-r0",
    "kegerator-tracker-r0",
    "ford-raptor-tracker-r0",
]


def read_target(public=False, input_path=LOCAL_INDEX):
    if public:
        with urllib.request.urlopen(PUBLIC_URL, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    with open(input_path, encoding="utf-8") as f:
        return f.read()


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def verify(html_text, data=None, payload=None):
    missing = [text for text in REQUIRED if text not in html_text]
    forbidden = [text for text in FORBIDDEN if text in html_text]
    if missing or forbidden:
        raise AssertionError(f"dashboard verification failed; missing={missing}; forbidden={forbidden}")
    data = data if data is not None else _read_json(DATA_PATH)
    payload = payload if payload is not None else _read_json(EMAIL_PATH)
    validate_outputs(html_text, payload, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--input", default=LOCAL_INDEX)
    parser.add_argument("--data", default=DATA_PATH)
    parser.add_argument("--email", default=EMAIL_PATH)
    args = parser.parse_args()
    try:
        if args.public and args.input != LOCAL_INDEX:
            raise ValueError("--input cannot be combined with --public")
        verify(
            read_target(public=args.public, input_path=args.input),
            data=_read_json(args.data),
            payload=_read_json(args.email),
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("dashboard verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
