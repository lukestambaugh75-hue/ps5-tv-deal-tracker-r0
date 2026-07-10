#!/usr/bin/env python3
"""Build the Gmail self-send payload for the PS5/TV tracker."""
import argparse
import html
import json
import os
import re
from datetime import datetime, timezone

try:
    from .tracker_core import best_rows_by_target, money, snapshot_is_represented
    from .audience_guard import validate_email_payload
    from .refresh_state import evaluate_refresh, format_central, utc_iso
except ImportError:
    from tracker_core import best_rows_by_target, money, snapshot_is_represented
    from audience_guard import validate_email_payload
    from refresh_state import evaluate_refresh, format_central, utc_iso


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


def _non_actionable_reason(value):
    return re.sub(
        r"\$\s?\d[\d,]*(?:\.\d{1,2})?",
        "[price withheld]",
        str(value or "Not recorded"),
    )


def build_payload(data, dashboard_url=DEFAULT_DASHBOARD_URL, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    state = evaluate_refresh(data.get("refresh"), now=now)
    best = best_rows_by_target(data)
    ps5 = best.get("ps5")
    tv = best.get("tv")
    generated = utc_iso(now)
    status = state["state"]
    actionable = status in {"Fresh", "Due"} and snapshot_is_represented(data)
    subject = f"PS5 + 65-inch TV deal tracker - {status}"

    success_text = state["data_refreshed_at_central"]
    attempt_text = state["last_attempt_at_central"]
    if state["last_attempt_status"] != "unknown":
        attempt_text = f"{attempt_text} ({state['last_attempt_status']})"
    reason = state["reason"]

    lines = [
        "PS5 and TV deal tracker",
        "",
        f"Refresh state: {status}",
        f"Last successful data refresh: {success_text}",
        f"Latest attempt: {attempt_text}",
        f"State reason: {_non_actionable_reason(reason)}",
        f"Dashboard: {dashboard_url}",
    ]
    html_body = [
        "<h2>PS5 and TV deal tracker</h2>",
        f"<p><strong>Refresh state:</strong> {html.escape(status)}</p>",
        f"<p><strong>Last successful data refresh:</strong> {html.escape(success_text)}</p>",
        f"<p><strong>Latest attempt:</strong> {html.escape(attempt_text)}</p>",
        f"<p><strong>State reason:</strong> {html.escape(_non_actionable_reason(reason))}</p>",
        f"<p>Dashboard: <a href='{html.escape(dashboard_url)}'>{html.escape(dashboard_url)}</a></p>",
    ]
    if actionable:
        lines[5:5] = [
            f"PS5 best row: {item_label(ps5)}",
            f"TV best row: {item_label(tv)}",
            f"PS5 warnings: {warning_text(ps5)}",
            f"TV warnings: {warning_text(tv)}",
        ]
        html_body[5:5] = [
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-family:Arial;font-size:13px'>",
            "<tr style='background:#152238;color:#fff'><th>Target</th><th>Best row</th><th>Warnings</th></tr>",
            f"<tr><td>PS5</td><td>{html.escape(item_label(ps5))}</td><td>{html.escape(warning_text(ps5))}</td></tr>",
            f"<tr><td>65-inch TV</td><td>{html.escape(item_label(tv))}</td><td>{html.escape(warning_text(tv))}</td></tr>",
            "</table>",
        ]
    else:
        lines.extend(
            [
                "",
                "Recommendations are withheld until a complete represented snapshot is Fresh or Due.",
            ]
        )
        html_body.append(
            "<p><strong>Recommendations withheld:</strong> a complete represented snapshot must be Fresh or Due.</p>"
        )
    lines.extend(
        [
            "",
            f"Email built: {format_central(now)}",
            "Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.",
        ]
    )
    html_body.append(
        f"<p style='color:#666;font-size:12px'>Email built: {html.escape(format_central(now))}. Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.</p>"
    )
    payload = {
        "to": RECIPIENTS[:],
        "cc": [],
        "bcc": [],
        "subject": subject,
        "body_text": "\n".join(lines),
        "body_html": "\n".join(html_body),
        "dashboard_url": dashboard_url,
        "generated_at": generated,
        "refresh_state": status,
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
