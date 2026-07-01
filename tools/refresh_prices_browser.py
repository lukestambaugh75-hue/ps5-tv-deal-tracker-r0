#!/usr/bin/env python3
"""Apply fresh browser/web price evidence to data/deals.json."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    from .tracker_core import apply_evidence
except ImportError:
    from tracker_core import apply_evidence


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
DEFAULT_EVIDENCE_PATH = os.path.join(ROOT, "out", "browser-price-evidence.json")


def mark_blocker(data, message):
    updated = dict(data)
    updated["meta"] = dict(data.get("meta", {}))
    updated["daily_brief"] = dict(data.get("daily_brief", {}))
    updated["meta"]["blocker"] = f"fresh_price_refresh: {message}"
    updated["daily_brief"]["fresh_evidence_status"] = "blocked"
    updated["daily_brief"]["summary"] = "Fresh price evidence failed. Do not treat old prices as current."
    gaps = list(updated["daily_brief"].get("data_quality_gaps", []))
    gaps.insert(0, message)
    updated["daily_brief"]["data_quality_gaps"] = gaps
    updated["meta"]["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA_PATH)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE_PATH)
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    try:
        with open(args.evidence, encoding="utf-8") as f:
            evidence = json.load(f)
        updated = apply_evidence(data, evidence)
    except Exception as exc:
        updated = mark_blocker(data, str(exc))
        with open(args.data, "w", encoding="utf-8") as f:
            json.dump(updated, f, indent=2)
        print(f"blocked: {exc}", file=sys.stderr)
        return 2

    with open(args.data, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
    print(f"applied {len(updated.get('items', []))} fresh evidence rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

