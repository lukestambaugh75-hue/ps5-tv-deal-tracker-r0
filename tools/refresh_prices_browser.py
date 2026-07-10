#!/usr/bin/env python3
"""Apply fresh browser/web price evidence to data/deals.json."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    from .tracker_core import process_evidence_attempt, record_unsuccessful_attempt
except ImportError:
    from tracker_core import process_evidence_attempt, record_unsuccessful_attempt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
DEFAULT_EVIDENCE_PATH = os.path.join(ROOT, "out", "browser-price-evidence.json")


def mark_blocker(data, message, attempted_at=None, status="failed"):
    """Backward-compatible wrapper that preserves the prior successful snapshot."""
    return record_unsuccessful_attempt(data, status, message, attempted_at)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA_PATH)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE_PATH)
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    attempted_at = datetime.now(timezone.utc)
    try:
        with open(args.evidence, encoding="utf-8") as f:
            evidence = json.load(f)
        updated, succeeded = process_evidence_attempt(data, evidence, now=attempted_at)
    except Exception as exc:
        updated = mark_blocker(data, str(exc), attempted_at=attempted_at, status="failed")
        succeeded = False

    with open(args.data, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
        f.write("\n")
    if not succeeded:
        refresh = updated.get("refresh", {})
        print(
            f"blocked: {refresh.get('last_attempt_status')}: {refresh.get('last_attempt_reason')}",
            file=sys.stderr,
        )
        return 2
    print(f"applied {len(updated.get('items', []))} fresh evidence rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
