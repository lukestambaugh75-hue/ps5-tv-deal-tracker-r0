#!/usr/bin/env python3
"""Check the public GitHub Pages dashboard."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

try:
    from .audience_guard import validate_dashboard_html
except ImportError:
    from audience_guard import validate_dashboard_html


PUBLIC_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
EXPECTED_ORIGIN = "https://github.com/lukestambaugh75-hue/ps5-tv-deal-tracker-r0.git"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_INDEX = os.path.join(ROOT, "index.html")
DATA_PATH = os.path.join(ROOT, "data", "deals.json")


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _git(args):
    result = subprocess.run(
        ["git", "-C", ROOT, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git identity check failed")
    return result.stdout.strip()


def _require_clean_pushed_main():
    if _git(["branch", "--show-current"]) != "main":
        raise RuntimeError("public verification requires branch main")
    if _git(["status", "--porcelain"]):
        raise RuntimeError("public verification requires a clean checkout")
    if _git(["remote", "get-url", "origin"]) != EXPECTED_ORIGIN:
        raise RuntimeError("public verification found the wrong origin")
    head = _git(["rev-parse", "HEAD"])
    if _git(["rev-parse", "refs/remotes/origin/main"]) != head:
        raise RuntimeError("local HEAD does not match origin/main")
    remote_line = _git(["ls-remote", "--exit-code", "origin", "refs/heads/main"])
    if not remote_line.startswith(head + "\t"):
        raise RuntimeError("live origin/main does not match local HEAD")
    return head


def _read_body(local=False, input_path=LOCAL_INDEX):
    if local:
        with open(input_path, encoding="utf-8") as f:
            return f.read(), "local"
    head = _require_clean_pushed_main()
    request = urllib.request.Request(
        f"{PUBLIC_URL}?verify={int(time.time() * 1000)}",
        headers={"Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status: {response.status}")
    expected = open(LOCAL_INDEX, "rb").read()
    if raw != expected:
        raise RuntimeError(
            "live dashboard bytes do not match the clean pushed local HEAD"
        )
    return raw.decode("utf-8", errors="strict"), f"{response.status}; head={head}"


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
