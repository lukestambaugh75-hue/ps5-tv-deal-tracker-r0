#!/usr/bin/env python3
"""Build the Gmail self-send payload for the PS5/TV tracker."""
import argparse
import html
import json
import os
from datetime import datetime, timezone

try:
    from .tracker_core import best_rows_by_target, money
    from .audience_guard import validate_email_payload
except ImportError:
    from tracker_core import best_rows_by_target, money
    from audience_guard import validate_email_payload


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
OUT_DIR = os.path.join(ROOT, "out")
DEFAULT_DASHBOARD_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
RECIPIENTS = ["lukestambaugh75@gmail.com", "devin.mullen89@gmail.com"]


def item_label(row):
    if not row:
        return "No current buy path passed fresh-evidence checks."
    return f"{row['retailer']} - {row.get('product_name') or row.get('model')} - {money(row.get('price'))}"


def warning_text(row):
    if not row or not row.get("warnings"):
        return "No warning chips on the current best row."
    return ", ".join(row["warnings"])


def build_payload(data, dashboard_url=DEFAULT_DASHBOARD_URL):
    best = best_rows_by_target(data)
    ps5 = best.get("ps5")
    tv = best.get("tv")
    generated = data.get("meta", {}).get("generated_at_utc") or datetime.now(timezone.utc).isoformat()
    status = data.get("daily_brief", {}).get("fresh_evidence_status") or "unknown"
    subject = f"PS5 + 65-inch TV deal tracker - {status}"

    lines = [
        "PS5 and TV deal tracker",
        "",
        f"Fresh evidence status: {status}",
        f"PS5 best row: {item_label(ps5)}",
        f"TV best row: {item_label(tv)}",
        f"PS5 warnings: {warning_text(ps5)}",
        f"TV warnings: {warning_text(tv)}",
        "",
        f"Dashboard: {dashboard_url}",
        f"Generated: {generated}",
        "",
        "Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.",
    ]
    html_body = [
        "<h2>PS5 and TV deal tracker</h2>",
        f"<p><strong>Fresh evidence status:</strong> {html.escape(status)}</p>",
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-family:Arial;font-size:13px'>",
        "<tr style='background:#152238;color:#fff'><th>Target</th><th>Best row</th><th>Warnings</th></tr>",
        f"<tr><td>PS5</td><td>{html.escape(item_label(ps5))}</td><td>{html.escape(warning_text(ps5))}</td></tr>",
        f"<tr><td>65-inch TV</td><td>{html.escape(item_label(tv))}</td><td>{html.escape(warning_text(tv))}</td></tr>",
        "</table>",
        f"<p>Dashboard: <a href='{html.escape(dashboard_url)}'>{html.escape(dashboard_url)}</a></p>",
        f"<p style='color:#666;font-size:12px'>Generated: {html.escape(generated)}. Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.</p>",
    ]
    payload = {
        "to": RECIPIENTS[:],
        "cc": [],
        "bcc": [],
        "subject": subject,
        "body_text": "\n".join(lines),
        "body_html": "\n".join(html_body),
        "dashboard_url": dashboard_url,
        "generated_at": generated,
    }
    validate_email_payload(payload, data)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=OUT_DIR)
    parser.add_argument("--dashboard-url", default=DEFAULT_DASHBOARD_URL)
    args = parser.parse_args()
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    payload = build_payload(data, args.dashboard_url)
    os.makedirs(args.output_dir, exist_ok=True)
    with open(os.path.join(args.output_dir, "latest-email.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"email payload: recipients={len(payload['to'])} subject={payload['subject']!r}")


if __name__ == "__main__":
    main()
