#!/usr/bin/env python3
"""Append one dated best-price row per target to history.csv."""
import argparse
import csv
import json
import os
from datetime import datetime, timezone

try:
    from .tracker_core import TARGET_IDS, best_rows_by_target
    from .refresh_state import CENTRAL_ZONE, evaluate_refresh, utc_iso
except ImportError:
    from tracker_core import TARGET_IDS, best_rows_by_target
    from refresh_state import CENTRAL_ZONE, evaluate_refresh, utc_iso


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
HISTORY_PATH = os.path.join(ROOT, "history.csv")
FIELDS = ["date", "target_id", "retailer", "product_name", "price", "evidence_class", "url"]


def _snapshot_is_represented(data, best):
    refresh = data.get("refresh") or {}
    success_at = utc_iso(refresh.get("data_refreshed_at_utc"))
    items = data.get("items") or []
    if not success_at or set(best) != TARGET_IDS:
        return False
    if refresh.get("last_attempt_status") != "success":
        return False
    if int(refresh.get("row_count") or 0) != len(items):
        return False
    return bool(items) and all(
        utc_iso(row.get("captured_at")) == success_at for row in items
    )


def build_history_rows(data, today=None, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = today or now.astimezone(CENTRAL_ZONE).strftime("%Y-%m-%d")
    state = evaluate_refresh(data.get("refresh"), now=now)
    if state["state"] not in {"Fresh", "Due"}:
        return []
    best = best_rows_by_target(data)
    if not _snapshot_is_represented(data, best):
        return []
    rows = []
    for target_id in sorted(best):
        row = best[target_id]
        rows.append(
            {
                "date": today,
                "target_id": target_id,
                "retailer": row.get("retailer", ""),
                "product_name": row.get("product_name") or row.get("model") or "",
                "price": row.get("price", ""),
                "evidence_class": row.get("evidence_class", ""),
                "url": row.get("url", ""),
            }
        )
    return rows


def write_history(path, new_rows, today=None):
    today = today or (new_rows[0]["date"] if new_rows else datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    if not new_rows:
        return rows
    rows = [row for row in rows if row.get("date") != today]
    rows.extend(new_rows)
    rows.sort(key=lambda row: (row["date"], row["target_id"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DATA_PATH)
    parser.add_argument("--history", default=HISTORY_PATH)
    args = parser.parse_args()
    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    now = datetime.now(timezone.utc)
    today = now.astimezone(CENTRAL_ZONE).strftime("%Y-%m-%d")
    rows = build_history_rows(data, today=today, now=now)
    all_rows = write_history(args.history, rows, today=today)
    print(f"history.csv: {len(all_rows)} rows; updated {today} with {len(rows)} target rows")


if __name__ == "__main__":
    main()
