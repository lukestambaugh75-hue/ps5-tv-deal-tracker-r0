#!/usr/bin/env python3
"""Build and deliver the private PS5 and TV encrypted dashboard."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT.parent / "Tools" / "encrypted-dashboard-publisher"
PUBLISHER_ROOT = ROOT.parent / "Encrypted Tracker Link Publisher r0"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from encrypted_dashboard_publisher.tracker_cli import run_tracker_cli  # noqa: E402


TRACKER_ID = "ps5-tv"
BINDING_ID = "binding_gjuVFrUKDKfvZGGaw9Ic1n3c"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot_id(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return "snapshot_" + hashlib.sha256(raw).hexdigest()


def _history_by_target() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    with (ROOT / "history.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            result.setdefault(row.get("target_id") or "", []).append(
                {
                    "at": row.get("date") or "",
                    "value": row.get("price") or "",
                    "note": f"{row.get('retailer') or 'Unknown'} - {row.get('evidence_class') or 'unknown'}",
                }
            )
    return {key: value[-30:] for key, value in result.items()}


def build_bundle() -> tuple[dict, dict]:
    data = _load(ROOT / "data" / "deals.json")
    email = _load(ROOT / "out" / "latest-email.json")
    histories = _history_by_target()
    rows = []
    for item in data.get("items", []):
        warnings = item.get("warnings") or []
        rows.append(
            {
                "id": item.get("id") or f"{item.get('target_id')}-{len(rows) + 1}",
                "name": item.get("product_name") or item.get("model") or "Tracked offer",
                "model": item.get("model") or "",
                "price": item.get("price"),
                "change": None,
                "availability": item.get("stock_status") or "Unknown",
                "freshness": f"Captured {item.get('captured_at') or data.get('refresh', {}).get('data_refreshed_at_utc')}",
                "status": "Review warning" if warnings else "Top pick",
                "confidence": (item.get("evidence_class") or "not stated").replace("_", " ").title(),
                "validation": item.get("evidence_text") or "Confirm checkout before buying.",
                "direct_url": item.get("url"),
                "history": histories.get(item.get("target_id") or "", []),
                "details": {
                    "Target": item.get("target_id") or "Not stated",
                    "Retailer": item.get("retailer") or "Not stated",
                    "Brand": item.get("brand") or "Not stated",
                    "Condition": item.get("condition") or "Not stated",
                    "Pickup or delivery": item.get("pickup_delivery") or "Not stated",
                    "Evidence class": (item.get("evidence_class") or "Not stated").replace("_", " "),
                    "Warnings": "; ".join(warnings) if warnings else "None",
                    "Evidence": item.get("evidence_text") or "Not stated",
                },
            }
        )
    refresh = data.get("refresh") or {}
    daily = data.get("daily_brief") or {}
    dashboard = {
        "schema_version": 1,
        "product_id": TRACKER_ID,
        "title": "PS5 and TV Deal Tracker",
        "snapshot_id": _snapshot_id(data),
        "generated_at": refresh.get("last_attempt_at_utc") or refresh.get("data_refreshed_at_utc"),
        "source_freshness": f"{refresh.get('last_attempt_status', 'unknown')} - refreshed {refresh.get('data_refreshed_at_utc', 'unknown')}",
        "overall_status": "FRESH" if refresh.get("last_attempt_status") == "success" else "CHECK",
        "summary": {
            "decision": daily.get("summary") or f"Compare {len(rows)} current PS5 and TV offers",
            "recommendation": "Confirm final cart total, tax, pickup or delivery timing, and seller identity before buying.",
            "verified_changes": len(rows),
            "blocked": int((refresh.get("quality_counts") or {}).get("blocked_or_stale") or 0),
            "stale": 0,
            "retry": 0,
            "overdue": 0,
        },
        "rows": rows,
    }
    brief = {
        "to": email.get("to"),
        "cc": email.get("cc") or [],
        "bcc": email.get("bcc") or [],
        "subject": email.get("subject") or "PS5 and TV Deal Tracker",
        "decision": dashboard["summary"]["decision"],
        "recommendation": dashboard["summary"]["recommendation"],
        "freshness": dashboard["source_freshness"],
    }
    return dashboard, brief


def main(argv=None) -> int:
    return run_tracker_cli(
        build_bundle,
        tracker_id=TRACKER_ID,
        binding_id=BINDING_ID,
        default_publisher_root=PUBLISHER_ROOT,
        default_tools_root=TOOLS_ROOT,
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
