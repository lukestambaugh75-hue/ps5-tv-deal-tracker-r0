#!/usr/bin/env python3
"""Check the public GitHub Pages dashboard."""
import json
import sys
import urllib.request


PUBLIC_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"


def main():
    result = {"url": PUBLIC_URL, "ok": False, "status": None}
    try:
        with urllib.request.urlopen(PUBLIC_URL, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            result["status"] = response.status
            result["ok"] = response.status == 200 and "PS5 and 65-inch TV Deal Tracker" in body
    except Exception as exc:
        result["error"] = str(exc)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

