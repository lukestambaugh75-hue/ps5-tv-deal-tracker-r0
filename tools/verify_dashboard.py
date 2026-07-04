#!/usr/bin/env python3
"""Verify required dashboard text locally or from the public URL."""
import argparse
import os
import sys
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_INDEX = os.path.join(ROOT, "index.html")
PUBLIC_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
REQUIRED = [
    "PS5 and 65-inch TV Deal Tracker",
    "Best Buy Today",
    "Current Retailer Rows",
    "Price History",
    "Evidence Guardrails",
    "Main Dashboard",
    "https://lukestambaugh75-hue.github.io/daily-dashboards-public-safe-r0/",
]
FORBIDDEN = ["Andante", "8826"]


def read_target(public=False):
    if public:
        with urllib.request.urlopen(PUBLIC_URL, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    with open(LOCAL_INDEX, encoding="utf-8") as f:
        return f.read()


def verify(html):
    missing = [text for text in REQUIRED if text not in html]
    forbidden = [text for text in FORBIDDEN if text in html]
    if missing or forbidden:
        raise AssertionError(f"dashboard verification failed; missing={missing}; forbidden={forbidden}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    try:
        verify(read_target(public=args.public))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("dashboard verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
