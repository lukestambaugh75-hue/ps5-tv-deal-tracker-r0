#!/usr/bin/env python3
"""Render the static public dashboard from data/deals.json."""
import csv
import html
import json
import os

try:
    from .tracker_core import best_rows_by_target, money
except ImportError:
    from tracker_core import best_rows_by_target, money


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
HISTORY_PATH = os.path.join(ROOT, "history.csv")
OUT_PATH = os.path.join(ROOT, "index.html")
DEFAULT_DASHBOARD_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"


def esc(value):
    return html.escape(str(value), quote=True) if value is not None else ""


def read_history(path=HISTORY_PATH):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def render_warning_chips(item):
    warnings = item.get("warnings") or []
    if not warnings:
        return '<span class="chip good">clean buy path</span>'
    return "".join(f'<span class="chip warn">{esc(warning)}</span>' for warning in warnings)


def readable_evidence(value):
    labels = {
        "big_box_public_price": "big-box public price",
        "houston_visible_buy_path": "Houston visible buy path",
        "manufacturer_direct_reference": "manufacturer reference",
    }
    if not value:
        return "evidence pending"
    return labels.get(value, str(value).replace("_", " "))


def render_best_card(target_id, label, best):
    row = best.get(target_id)
    if not row:
        return f"""
        <article class="best-card blocked">
          <span class="eyebrow">{esc(label)}</span>
          <h3>No current buy path</h3>
          <p>Fresh evidence did not produce an available row for this target.</p>
        </article>"""
    product = row.get("product_name") or row.get("model")
    return f"""
        <article class="best-card">
          <span class="eyebrow">{esc(label)}</span>
          <h3>{esc(row.get("retailer"))}: {esc(money(row.get("price")))}</h3>
          <p><a href="{esc(row.get("url"))}">{esc(product)}</a></p>
          <div class="chips">{render_warning_chips(row)}</div>
          <dl class="fact-list">
            <div><dt>Availability</dt><dd>{esc(row.get("stock_status") or "check retailer")}</dd></div>
            <div><dt>Pickup / delivery</dt><dd>{esc(row.get("pickup_delivery") or "check retailer")}</dd></div>
            <div><dt>Evidence</dt><dd>{esc(readable_evidence(row.get("evidence_class")))}</dd></div>
          </dl>
        </article>"""


def render_item_row(item):
    product = item.get("product_name") or item.get("model")
    return f"""
          <tr>
            <td>{esc(item.get("target_id", "").upper())}</td>
            <td>{esc(item.get("retailer"))}</td>
            <td><a href="{esc(item.get("url"))}">{esc(product)}</a></td>
            <td>{esc(money(item.get("price")))}</td>
            <td>{esc(item.get("stock_status") or "-")}</td>
            <td>{render_warning_chips(item)}</td>
          </tr>"""


def render_history_rows(history_rows):
    if not history_rows:
        return '<tr><td colspan="5">History starts after the first scheduled run.</td></tr>'
    latest = history_rows[-20:]
    return "\n".join(
        f"<tr><td>{esc(row.get('date'))}</td><td>{esc(row.get('target_id'))}</td><td>{esc(row.get('retailer'))}</td><td>{esc(row.get('product_name'))}</td><td>{esc(money(row.get('price')))}</td></tr>"
        for row in latest
    )


def compact_best_summary(best):
    parts = []
    for target_id, label in (("ps5", "PS5"), ("tv", "TV")):
        row = best.get(target_id)
        if row:
            parts.append(f"{label}: {row.get('retailer')} {money(row.get('price'))}")
    return ". ".join(parts) + "." if parts else "Fresh evidence pending."


def render_dashboard(data, history_rows=None, dashboard_url=DEFAULT_DASHBOARD_URL):
    history_rows = history_rows if history_rows is not None else read_history()
    best = best_rows_by_target(data)
    items = data.get("items", [])
    generated = data.get("meta", {}).get("generated_at_utc", "not generated")
    summary = data.get("daily_brief", {}).get("summary", "Fresh evidence pending.")
    mobile_summary = compact_best_summary(best)
    status = data.get("daily_brief", {}).get("fresh_evidence_status", "unknown")
    warnings = data.get("daily_brief", {}).get("warnings", [])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PS5 and TV Deal Tracker</title>
  <meta name="robots" content="noindex, nofollow">
  <style>
    :root {{
      color-scheme: dark;
      --bg: #101318;
      --panel: #171d26;
      --panel-2: #202938;
      --ink: #f5f7fb;
      --muted: #b8c3d6;
      --line: #334155;
      --blue: #65a7ff;
      --green: #9be66d;
      --amber: #ffcb6b;
      --red: #ff8b8b;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; overflow-x: hidden; background: var(--bg); color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }}
    a {{ color: var(--blue); text-underline-offset: 3px; }}
    .wrap {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    .hero {{ min-height: 560px; display: flex; align-items: flex-end; background: linear-gradient(90deg, rgba(16,19,24,.98), rgba(16,19,24,.9) 48%, rgba(16,19,24,.48) 78%, rgba(16,19,24,.26)), url("assets/electronics-hero.png") center/cover no-repeat; border-bottom: 1px solid var(--line); }}
    .hero-content {{ padding: 68px 0 38px; max-width: 900px; }}
    h1 {{ font-size: clamp(2.4rem, 7vw, 5.2rem); line-height: .96; margin: 12px 0 18px; letter-spacing: 0; overflow-wrap: anywhere; }}
    h2 {{ font-size: 1.45rem; margin: 0 0 14px; }}
    h3 {{ margin: 0 0 8px; font-size: 1.15rem; }}
    p {{ margin: 8px 0; }}
    .lead {{ color: var(--muted); font-size: 1.08rem; max-width: 760px; }}
    .mobile-summary {{ display: none; }}
    .eyebrow {{ color: var(--green); text-transform: uppercase; font-size: .76rem; font-weight: 800; letter-spacing: .08em; }}
    .metrics, .best-grid {{ display: grid; gap: 14px; }}
    .metrics {{ grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 26px; }}
    .metric, .best-card, .panel {{ background: linear-gradient(180deg, var(--panel), var(--panel-2)); border: 1px solid var(--line); border-radius: 8px; padding: 16px; overflow: hidden; }}
    .metric strong {{ display: block; font-size: 1.75rem; margin-top: 4px; }}
    .metric small {{ overflow-wrap: anywhere; }}
    .color-index {{ margin-top: 14px; background: rgba(101,167,255,.08); }}
    .color-index p {{ margin-bottom: 0; }}
    .best-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 26px 0 0; }}
    .section {{ padding: 32px 0; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0; }}
    .chip {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 9px; font-size: .78rem; border: 1px solid var(--line); color: var(--muted); }}
    .chip.good {{ color: #17351e; background: var(--green); border-color: var(--green); }}
    .chip.warn {{ color: #2f1e00; background: var(--amber); border-color: var(--amber); }}
    dl {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; }}
    .fact-list {{ grid-template-columns: 1fr; gap: 8px; }}
    .fact-list div {{ padding: 10px; border: 1px solid rgba(255,255,255,.08); border-radius: 6px; background: rgba(255,255,255,.035); }}
    dt {{ color: var(--muted); font-size: .78rem; }}
    dd {{ margin: 0; font-weight: 700; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
    th, td {{ text-align: left; padding: 11px 9px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--green); font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; }}
    .note {{ color: var(--muted); }}
    .footer {{ color: var(--muted); font-size: .85rem; padding: 26px 0 40px; }}
    @media (max-width: 760px) {{
      .wrap {{ width: min(1180px, calc(100% - 32px)); }}
      .hero {{ min-height: auto; align-items: flex-start; background: linear-gradient(180deg, rgba(16,19,24,.97), rgba(16,19,24,.9) 58%, rgba(16,19,24,.7)), url("assets/electronics-hero.png") center/cover no-repeat; }}
      .wrap.hero-content {{ width: 100%; max-width: 100%; margin: 0 auto; }}
      .hero-content {{ padding: 32px 16px 26px; }}
      h1 {{ max-width: 100%; font-size: clamp(1.85rem, 10vw, 2.45rem); line-height: 1; word-break: break-word; }}
      .lead {{ max-width: 100%; font-size: .96rem; overflow-wrap: anywhere; word-break: break-word; }}
      .desktop-summary {{ display: none; }}
      .mobile-summary {{ display: inline; }}
      .metrics, .best-grid, dl {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      td {{ border-bottom: 0; padding: 9px 0; }}
      tr {{ border-bottom: 1px solid var(--line); padding: 10px 0; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="wrap hero-content">
      <span class="eyebrow">Electronics price tracker</span>
      <h1>PS5 and 65-inch TV Deal Tracker</h1>
      <p class="lead"><span class="desktop-summary">{esc(summary)}</span><span class="mobile-summary">{esc(mobile_summary)}</span></p>
      <div class="metrics">
        <div class="metric"><span class="eyebrow">Freshness</span><strong>{esc(status)}</strong><small>Generated {esc(generated)}</small></div>
        <div class="metric"><span class="eyebrow">Tracked Rows</span><strong>{len(items)}</strong><small>Current retailer evidence rows</small></div>
        <div class="metric"><span class="eyebrow">Warnings</span><strong>{len(warnings)}</strong><small>{esc(", ".join(warnings) if warnings else "No warning chips")}</small></div>
      </div>
      <div class="panel color-index">
        <span class="eyebrow">Color index</span>
        <p class="note"><strong>Green</strong> = recommended or ready to act. <strong>Blue</strong> = information only, like links, charts, totals, or neutral controls; it is not a recommendation. <strong>Amber</strong> = caution; check details before acting. <strong>Red</strong> = blocked or stop; do not act until fixed.</p>
      </div>
      <div class="best-grid" id="best-buys">
        {render_best_card("ps5", "Best Buy Today - PS5", best)}
        {render_best_card("tv", "Best Buy Today - 65-inch TV", best)}
      </div>
    </div>
  </header>
  <main>
    <section class="section" id="price-ladder">
      <div class="wrap panel">
        <span class="eyebrow">Price ladder</span>
        <h2>Current Retailer Rows</h2>
        <table>
          <thead><tr><th>Target</th><th>Retailer</th><th>Product</th><th>Price</th><th>Stock</th><th>Warnings</th></tr></thead>
          <tbody>{''.join(render_item_row(item) for item in items) or '<tr><td colspan="6">Fresh evidence pending.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="section" id="price-history">
      <div class="wrap panel">
        <span class="eyebrow">Price History</span>
        <h2>Best Row Trend</h2>
        <table>
          <thead><tr><th>Date</th><th>Target</th><th>Retailer</th><th>Product</th><th>Price</th></tr></thead>
          <tbody>{render_history_rows(history_rows)}</tbody>
        </table>
      </div>
    </section>
    <section class="section" id="evidence-guardrails">
      <div class="wrap panel">
        <span class="eyebrow">Run Rules</span>
        <h2>Evidence Guardrails</h2>
        <p class="note">The scheduled run must prove fresh visible evidence before quoting a current price. Member-only, cart-only, marketplace, open-box/refurbished, out-of-stock, blocked, and stale rows are visible as warnings instead of being promoted silently.</p>
        <p class="note">Dashboard URL: <a href="{esc(dashboard_url)}">{esc(dashboard_url)}</a></p>
      </div>
    </section>
  </main>
  <footer class="wrap footer">Confirm final cart total, tax, pickup or delivery timing, and seller identity before buying.</footer>
</body>
</html>"""


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    html_text = render_dashboard(data, read_history())
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"rendered {OUT_PATH}")


if __name__ == "__main__":
    main()
