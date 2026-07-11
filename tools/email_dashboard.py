#!/usr/bin/env python3
"""Render the PS5/TV tracker as an HTML email body.

Returns (body_html, inline_images). Charts are written as PNGs next to the payload
and referenced by Content-ID, because Gmail will not render inline SVG or <canvas>.

The standalone audience boundary (tools/audience_guard.py) still applies to whatever
this produces: every navigation link must be either the exact dashboard URL or an
exact `url` from `data["items"]`, and every image must ride as a `cid:` inline
attachment that audience_guard can match against `inline_images`.

When the snapshot is not actionable (refresh state is not Fresh/Due, or the two
targets are not both represented by one successful refresh), this intentionally
renders NO prices, product names, or best-row claims -- only the refresh state and
the honest reason recommendations are withheld. See tests/test_tracker.py for the
non-actionable invariants this must keep satisfying.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAILER = Path.home() / "Documents" / "Files for GitHub" / "Tools" / "dashboard-mailer"
if str(MAILER) not in sys.path:
    sys.path.insert(0, str(MAILER))

import charts  # noqa: E402
import email_render as er  # noqa: E402

try:
    from .refresh_state import evaluate_refresh
    from .tracker_core import BAD_CURRENT_CLASSES, best_rows_by_target, snapshot_is_represented
except ImportError:
    from refresh_state import evaluate_refresh
    from tracker_core import BAD_CURRENT_CLASSES, best_rows_by_target, snapshot_is_represented

HISTORY_DAYS = 21
TOP_N_PER_TARGET = 5

TARGET_LABELS = {"ps5": "PS5", "tv": "65-inch TV"}

WARNING_TONES = {
    "out of stock": "bad",
    "blocked or stale evidence": "bad",
    "marketplace seller": "warn",
    "open-box/refurbished": "warn",
    "member-only price": "note",
    "cart-only price": "note",
    "manufacturer-direct reference": "note",
    "entry-tier TV": "note",
    "PS5 Pro, not the standard target": "note",
}


def _history(path=None):
    path = path or (ROOT / "history.csv")
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows[-HISTORY_DAYS:]


def _price_series(hist, target_id):
    """One price per date for a target, keeping only dates both targets reported."""
    by_date = {}
    for row in hist:
        if row.get("target_id") != target_id:
            continue
        try:
            by_date[row["date"]] = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue
    return by_date


def _row_tone(item, best_ids):
    if item.get("id") in best_ids:
        return "good"
    if item.get("evidence_class") in BAD_CURRENT_CLASSES:
        return "bad"
    if item.get("warnings"):
        return "warn"
    return None


def _warning_pills(item):
    pills = [er.pill(w, WARNING_TONES.get(w, "note")) for w in item.get("warnings", [])]
    return " ".join(pills) if pills else "--"


def _non_actionable_body(data, state, dashboard_url):
    status = state["state"]
    blocks = [
        er.kpis([
            ("Refresh state", status, "good" if status == "Fresh" else "warn"),
            ("Last successful refresh", state["data_refreshed_at_central"], "flat"),
            ("Latest attempt", state["last_attempt_at_central"], "flat"),
        ]),
        er.callout(
            er.esc(state["reason"]),
            tone="bad" if status in {"Blocked", "Stale"} else "warn",
            title="Recommendations withheld",
        ),
        er.paragraph(
            "A complete represented snapshot for both PS5 and the 65-inch TV target "
            "must be Fresh or Due before best-row prices or product names are shown."
        ),
        er.button("Open the dashboard", dashboard_url),
    ]
    return er.shell(
        "PS5 and TV Deal Tracker",
        f"Refresh state: {status}",
        blocks,
        footer_links=[("Open dashboard", dashboard_url)],
        footnote="Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.",
    )


def build(data, dashboard_url, now=None, out_dir=None):
    out_dir = Path(out_dir) if out_dir else ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    state = evaluate_refresh(data.get("refresh"), now=now)
    status = state["state"]
    actionable = status in {"Fresh", "Due"} and snapshot_is_represented(data)

    if not actionable:
        return _non_actionable_body(data, state, dashboard_url), []

    images = []
    blocks = []
    best = best_rows_by_target(data)
    best_ids = {row["id"] for row in best.values() if row.get("id")}
    items = data.get("items", [])

    # ---- headline numbers -------------------------------------------------
    tiles = [("Refresh state", status, "good" if status == "Fresh" else "warn")]
    if best.get("ps5"):
        tiles.append(("PS5 best price", er.money(best["ps5"]["price"], cents=True), "good"))
    if best.get("tv"):
        tiles.append(("TV best price", er.money(best["tv"]["price"], cents=True), "good"))
    tiles.append(("Data age", state["age_label"], "flat"))
    blocks.append(er.kpis(tiles))

    # ---- price trend --------------------------------------------------------
    hist = _history()
    if len(hist) >= 3 and charts.available():
        ps5_by_date = _price_series(hist, "ps5")
        tv_by_date = _price_series(hist, "tv")
        common_dates = sorted(set(ps5_by_date) & set(tv_by_date))
        if len(common_dates) >= 3:
            dates = [d[5:] for d in common_dates]
            ps5_vals = [ps5_by_date[d] for d in common_dates]
            tv_vals = [tv_by_date[d] for d in common_dates]
            png = charts.trend(
                dates,
                [("PS5", ps5_vals, charts.BLUE), ("65-inch TV", tv_vals, charts.VIOLET)],
                money=True,
            )
            (out_dir / "chart-price.png").write_bytes(png)
            images.append({"cid": "priceTrend", "path": "chart-price.png"})
            blocks.append(er.heading("Price trend", f"Best row snapshot for the last {len(common_dates)} tracked days"))
            blocks.append(er.chart("priceTrend", "PS5 and TV price trend"))

    # ---- ranked rows per target --------------------------------------------
    warnings_seen = set()
    rows, tones = [], []
    for target_id in ("ps5", "tv"):
        target_items = sorted(
            (i for i in items if i.get("target_id") == target_id and i.get("price")),
            key=lambda i: i["price"],
        )[:TOP_N_PER_TARGET]
        for item in target_items:
            warnings_seen.update(item.get("warnings", []))
            label = er.link(item.get("product_name") or item.get("model", ""), item["url"]) \
                if item.get("url") else er.esc(item.get("product_name") or item.get("model", ""))
            rows.append([
                TARGET_LABELS.get(target_id, target_id),
                f'{label}<br><span style="font-size:11px;color:#94a3b8;">{er.esc(item.get("retailer", ""))}</span>',
                er.money(item["price"], cents=True),
                _warning_pills(item),
            ])
            tones.append(_row_tone(item, best_ids))

    if rows:
        blocks.append(er.heading("Best rows by target", "Cheapest first within each target. Click a product to open the listing."))
        blocks.append(er.table(
            ["Target", "Retailer / product", "Price", "Flags"],
            rows,
            aligns=["left", "left", "right", "left"],
            tones=tones,
        ))

    # ---- retailer price comparison -----------------------------------------
    for target_id in ("ps5", "tv"):
        comparable = sorted(
            (
                i for i in items
                if i.get("target_id") == target_id
                and i.get("price")
                and i.get("evidence_class") not in BAD_CURRENT_CLASSES
            ),
            key=lambda i: i["price"],
        )
        if len(comparable) >= 2:
            cheapest_id = comparable[0].get("id")
            blocks.append(er.heading(f"{TARGET_LABELS.get(target_id, target_id)} by retailer"))
            blocks.append(er.bar_table(
                [
                    (i.get("retailer", ""), i["price"], "good" if i.get("id") == cheapest_id else "info")
                    for i in comparable
                ],
                money_fmt=True,
            ))

    # ---- data quality flags --------------------------------------------------
    if warnings_seen:
        blocks.append(er.callout(
            "Flagged rows above (marketplace sellers, member-only prices, out-of-stock, and "
            "similar) are shown for transparency; they are not promoted as the default best buy.",
            tone="warn",
            title="Data quality flags: " + ", ".join(sorted(warnings_seen)),
        ))

    blocks.append(er.button("Open the dashboard", dashboard_url))

    body_html = er.shell(
        "PS5 and TV Deal Tracker",
        f"{status} · PS5 console and 60-70 inch 4K TV · Big-box retailers, Houston-area pickup/delivery",
        blocks,
        footer_links=[("Open dashboard", dashboard_url)],
        footnote=(
            "Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying."
        ),
    )
    return body_html, images
