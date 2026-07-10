#!/usr/bin/env python3
"""Render the static public dashboard from data/deals.json."""
import csv
import html
import json
import os
from datetime import datetime, timezone

try:
    from .tracker_core import best_rows_by_target, money, snapshot_is_represented
    from .refresh_state import evaluate_refresh, format_central, utc_iso
except ImportError:
    from tracker_core import best_rows_by_target, money, snapshot_is_represented
    from refresh_state import evaluate_refresh, format_central, utc_iso


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data", "deals.json")
HISTORY_PATH = os.path.join(ROOT, "history.csv")
OUT_PATH = os.path.join(ROOT, "index.html")
DEFAULT_DASHBOARD_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"
HISTORICAL_SUMMARY = (
    "Stored values from the last successful refresh are shown for history only. "
    "They are not current recommendations."
)
UNKNOWN_SUMMARY = (
    "Unverified stored rows have no trustworthy refresh time. "
    "They are not current recommendations."
)
HISTORICAL_WARNING = (
    "Stored prices and products are from the last successful refresh. "
    "They are not current recommendations."
)
UNKNOWN_WARNING = (
    "Unverified stored rows - no trustworthy refresh time. "
    "Prices and products are not current recommendations."
)


def esc(value):
    return html.escape(str(value), quote=True) if value is not None else ""


def read_history(path=HISTORY_PATH):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def render_warning_chips(item, provenance="current"):
    warnings = item.get("warnings") or []
    if not warnings:
        classes = {
            "current": "good",
            "historical": "historical",
            "unknown": "unverified",
        }
        texts = {
            "current": "clean buy path",
            "historical": "historical evidence",
            "unknown": "unverified evidence",
        }
        return (
            f'<span class="chip {classes[provenance]}" data-fresh-treatment '
            f'data-fresh-text="clean buy path" data-historical-text="historical evidence" '
            f'data-unknown-text="unverified evidence">{texts[provenance]}</span>'
        )
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


def render_best_card(target_id, label, best, provenance="current"):
    row = best.get(target_id)
    fresh_label = f"Best Buy Today - {label}"
    historical_label = f"Best row from last successful refresh - {label}"
    unknown_label = f"Unverified stored row - no trustworthy refresh time - {label}"
    labels = {
        "current": fresh_label,
        "historical": historical_label,
        "unknown": unknown_label,
    }
    treatment = {
        "current": "",
        "historical": " historical",
        "unknown": " unverified",
    }[provenance]
    if not row:
        return f"""
        <article class="best-card blocked{treatment}" data-recommendation-card>
          <span class="eyebrow" data-recommendation-label data-fresh-text="{esc(fresh_label)}" data-historical-text="{esc(historical_label)}" data-unknown-text="{esc(unknown_label)}">{esc(labels[provenance])}</span>
          <h3>No represented row</h3>
          <p>The complete snapshot does not contain an available row for this target.</p>
        </article>"""
    product = row.get("product_name") or row.get("model")
    return f"""
        <article class="best-card{treatment}" data-recommendation-card>
          <span class="eyebrow" data-recommendation-label data-fresh-text="{esc(fresh_label)}" data-historical-text="{esc(historical_label)}" data-unknown-text="{esc(unknown_label)}">{esc(labels[provenance])}</span>
          <h3>{esc(row.get("retailer"))}: {esc(money(row.get("price")))}</h3>
          <p><a href="{esc(row.get("url"))}">{esc(product)}</a></p>
          <div class="chips">{render_warning_chips(row, provenance=provenance)}</div>
          <dl class="fact-list">
            <div><dt>Availability</dt><dd>{esc(row.get("stock_status") or "check retailer")}</dd></div>
            <div><dt>Pickup / delivery</dt><dd>{esc(row.get("pickup_delivery") or "check retailer")}</dd></div>
            <div><dt>Evidence</dt><dd>{esc(readable_evidence(row.get("evidence_class")))}</dd></div>
          </dl>
        </article>"""


def render_item_row(item, provenance="current"):
    product = item.get("product_name") or item.get("model")
    return f"""
          <tr>
            <td>{esc(item.get("target_id", "").upper())}</td>
            <td>{esc(item.get("retailer"))}</td>
            <td><a href="{esc(item.get("url"))}">{esc(product)}</a></td>
            <td>{esc(money(item.get("price")))}</td>
            <td>{esc(item.get("stock_status") or "-")}</td>
            <td>{render_warning_chips(item, provenance=provenance)}</td>
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


def _cadence_label(minutes):
    minutes = int(minutes or 0)
    if minutes and minutes % 60 == 0:
        hours = minutes // 60
        return f"Every {hours} hour{'s' if hours != 1 else ''}"
    return f"Every {minutes} minutes"


def render_dashboard(data, history_rows=None, dashboard_url=DEFAULT_DASHBOARD_URL, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    history_rows = history_rows if history_rows is not None else read_history()
    best = best_rows_by_target(data)
    items = data.get("items", [])
    summary = data.get("daily_brief", {}).get("summary", "Fresh evidence pending.")
    mobile_summary = compact_best_summary(best)
    refresh = evaluate_refresh(data.get("refresh"), now=now)
    status = refresh["state"]
    represented = snapshot_is_represented(data)
    actionable = status in {"Fresh", "Due"} and represented
    provenance = "current" if actionable else "unknown" if status == "Unknown" else "historical"
    visible_summary = {
        "current": summary,
        "historical": HISTORICAL_SUMMARY,
        "unknown": UNKNOWN_SUMMARY,
    }[provenance]
    visible_mobile_summary = {
        "current": mobile_summary,
        "historical": HISTORICAL_SUMMARY,
        "unknown": UNKNOWN_SUMMARY,
    }[provenance]
    row_heading = {
        "current": "Current Retailer Rows",
        "historical": "Stored Retailer Rows",
        "unknown": "Unverified Stored Rows",
    }[provenance]
    row_metric = {
        "current": "Current retailer evidence rows",
        "historical": "Stored retailer evidence rows",
        "unknown": "Unverified stored rows",
    }[provenance]
    provenance_warning = {
        "current": HISTORICAL_WARNING,
        "historical": HISTORICAL_WARNING,
        "unknown": UNKNOWN_WARNING,
    }[provenance]
    body_classes = []
    if not actionable:
        body_classes.append("recommendations-historical")
    if provenance == "unknown":
        body_classes.append("recommendations-unverified")
    body_class_attr = f' class="{" ".join(body_classes)}"' if body_classes else ""
    warnings = data.get("daily_brief", {}).get("warnings", [])
    rendered_at = utc_iso(now)
    published_at = data.get("refresh", {}).get("published_at_utc")
    refresh_metadata = dict(refresh)
    refresh_metadata["rendered_at_utc"] = rendered_at
    refresh_metadata["rendered_at_central"] = format_central(now)
    refresh_metadata["published_at_utc"] = published_at
    refresh_metadata["published_at_central"] = format_central(published_at)
    refresh_json = json.dumps(refresh_metadata, indent=2, sort_keys=True).replace("<", "\\u003c")
    attempt_label = refresh["last_attempt_at_central"]
    if refresh["last_attempt_status"] != "unknown":
        attempt_label = f"{attempt_label} ({refresh['last_attempt_status']})"
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
    .refresh-block {{ margin-top: 14px; background: rgba(23,29,38,.94); }}
    .refresh-heading {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }}
    .state-badge {{ display: inline-flex; align-items: center; min-height: 32px; border-radius: 999px; padding: 5px 12px; font-size: .9rem; border: 1px solid var(--line); }}
    .state-badge.fresh {{ color: #17351e; background: var(--green); border-color: var(--green); }}
    .state-badge.due {{ color: #2f1e00; background: var(--amber); border-color: var(--amber); }}
    .state-badge.stale, .state-badge.blocked {{ color: #3b0b0b; background: var(--red); border-color: var(--red); }}
    .state-badge.unknown, .state-badge.archived {{ color: var(--ink); background: var(--line); }}
    .refresh-facts {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .refresh-facts div {{ min-width: 0; padding: 10px; border: 1px solid rgba(255,255,255,.08); border-radius: 6px; background: rgba(255,255,255,.035); }}
    .refresh-reason {{ margin-top: 12px; color: var(--muted); }}
    .secondary-time {{ color: var(--muted); font-size: .8rem; margin-top: 10px; }}
    .color-index {{ margin-top: 14px; background: rgba(101,167,255,.08); }}
    .color-index p {{ margin-bottom: 0; }}
    .best-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 26px 0 0; }}
    .section {{ padding: 32px 0; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0; }}
    .chip {{ display: inline-flex; align-items: center; min-height: 24px; border-radius: 999px; padding: 3px 9px; font-size: .78rem; border: 1px solid var(--line); color: var(--muted); }}
    .chip.good {{ color: #17351e; background: var(--green); border-color: var(--green); }}
    .chip.warn {{ color: #2f1e00; background: var(--amber); border-color: var(--amber); }}
    .chip.historical {{ color: var(--muted); background: rgba(255,203,107,.1); border-color: var(--amber); }}
    .chip.unverified {{ color: var(--muted); background: rgba(184,195,214,.08); border-color: var(--muted); }}
    .best-card.historical {{ border-color: rgba(255,203,107,.72); box-shadow: inset 0 3px 0 rgba(255,203,107,.32); }}
    .best-card.unverified {{ border-color: var(--muted); box-shadow: inset 0 3px 0 rgba(184,195,214,.24); }}
    .historical-warning {{ margin: 12px 0 18px; padding: 11px 13px; color: var(--amber); background: rgba(255,203,107,.08); border: 1px solid rgba(255,203,107,.45); border-radius: 6px; }}
    .historical-warning[hidden] {{ display: none; }}
    dl {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 14px 0 0; }}
    .fact-list {{ grid-template-columns: 1fr; gap: 8px; }}
    .fact-list div {{ padding: 10px; border: 1px solid rgba(255,255,255,.08); border-radius: 6px; background: rgba(255,255,255,.035); }}
    dt {{ color: var(--muted); font-size: .78rem; }}
    dd {{ margin: 0; font-weight: 700; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
    th, td {{ text-align: left; padding: 11px 9px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--green); font-size: .75rem; text-transform: uppercase; letter-spacing: .06em; }}
    body.recommendations-historical [data-recommendation-label], body.recommendations-historical #price-ladder th {{ color: var(--amber); }}
    body.recommendations-unverified [data-recommendation-label], body.recommendations-unverified #price-ladder th {{ color: var(--muted); }}
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
      .metrics, .best-grid, dl, .refresh-facts {{ grid-template-columns: 1fr; }}
      table, thead, tbody, tr, th, td {{ display: block; }}
      thead {{ display: none; }}
      td {{ border-bottom: 0; padding: 9px 0; }}
      tr {{ border-bottom: 1px solid var(--line); padding: 10px 0; }}
    }}
  </style>
</head>
<body{body_class_attr}>
  <header class="hero">
    <div class="wrap hero-content">
      <span class="eyebrow">Electronics price tracker</span>
      <h1>PS5 and 65-inch TV Deal Tracker</h1>
      <p class="lead"><span class="desktop-summary" data-recommendation-summary data-fresh-text="{esc(summary)}" data-historical-text="{esc(HISTORICAL_SUMMARY)}" data-unknown-text="{esc(UNKNOWN_SUMMARY)}">{esc(visible_summary)}</span><span class="mobile-summary" data-recommendation-summary data-fresh-text="{esc(mobile_summary)}" data-historical-text="{esc(HISTORICAL_SUMMARY)}" data-unknown-text="{esc(UNKNOWN_SUMMARY)}">{esc(visible_mobile_summary)}</span></p>
      <div class="metrics">
        <div class="metric"><span class="eyebrow">Data state</span><strong id="hero-data-state">{esc(status)}</strong><small>Derived from source refresh evidence</small></div>
        <div class="metric"><span class="eyebrow">Tracked Rows</span><strong>{len(items)}</strong><small data-row-metric data-fresh-text="Current retailer evidence rows" data-historical-text="Stored retailer evidence rows" data-unknown-text="Unverified stored rows">{esc(row_metric)}</small></div>
        <div class="metric"><span class="eyebrow">Warnings</span><strong>{len(warnings)}</strong><small>{esc(", ".join(warnings) if warnings else "No warning chips")}</small></div>
      </div>
      <section
        class="panel refresh-block"
        aria-labelledby="refresh-heading"
        data-refresh-root
        data-success-at="{esc(refresh['data_refreshed_at_utc'])}"
        data-attempt-at="{esc(refresh['last_attempt_at_utc'])}"
        data-cadence-minutes="{refresh['cadence_minutes']}"
        data-grace-minutes="{refresh['grace_minutes']}"
        data-attempt-status="{esc(refresh['last_attempt_status'])}"
        data-state-reason="{esc(refresh['reason'])}"
        data-archived="{str(refresh['archived']).lower()}"
        data-represented="{str(represented).lower()}"
      >
        <div class="refresh-heading">
          <div>
            <span class="eyebrow">Actual source data</span>
            <h2 id="refresh-heading">Refresh evidence</h2>
          </div>
          <strong id="refresh-status" class="state-badge {esc(status.lower())}" aria-live="polite">{esc(status)}</strong>
        </div>
        <dl class="refresh-facts">
          <div><dt>Last successful data refresh</dt><dd>{esc(refresh['data_refreshed_at_central'])}</dd></div>
          <div><dt>Age</dt><dd id="refresh-age">{esc(refresh['age_label'])}</dd></div>
          <div><dt>Cadence</dt><dd>{esc(_cadence_label(refresh['cadence_minutes']))} + {refresh['grace_minutes'] // 60}-hour grace</dd></div>
          <div><dt>Next due</dt><dd>{esc(refresh['next_due_at_central'])}</dd></div>
          <div><dt>Latest attempt</dt><dd>{esc(attempt_label)}</dd></div>
          <div><dt>Evidence represented</dt><dd>{refresh['row_count']} rows from {refresh['source_count']} sources</dd></div>
        </dl>
        <p class="refresh-reason"><strong>State reason:</strong> <span id="refresh-reason">{esc(refresh['reason'])}</span></p>
        <p class="secondary-time"><strong>Render / publish:</strong> rendered {esc(format_central(now))}; published {esc(format_central(published_at))}. These do not change the underlying data age.</p>
      </section>
      <div class="panel color-index">
        <span class="eyebrow">Color index</span>
        <p class="note"><strong>Green</strong> = recommended or ready to act. <strong>Blue</strong> = information only, like links, charts, totals, or neutral controls; it is not a recommendation. <strong>Amber</strong> = caution; check details before acting. <strong>Red</strong> = blocked or stop; do not act until fixed.</p>
      </div>
      <div class="best-grid" id="best-buys">
        {render_best_card("ps5", "PS5", best, provenance=provenance)}
        {render_best_card("tv", "65-inch TV", best, provenance=provenance)}
      </div>
    </div>
  </header>
  <main>
    <section class="section" id="price-ladder">
      <div class="wrap panel">
        <span class="eyebrow">Price ladder</span>
        <h2 data-retailer-heading data-fresh-text="Current Retailer Rows" data-historical-text="Stored Retailer Rows" data-unknown-text="Unverified Stored Rows">{esc(row_heading)}</h2>
        <p id="historical-warning" class="historical-warning" data-historical-text="{esc(HISTORICAL_WARNING)}" data-unknown-text="{esc(UNKNOWN_WARNING)}"{' hidden' if actionable else ''}>{esc(provenance_warning)}</p>
        <table>
          <thead><tr><th>Target</th><th>Retailer</th><th>Product</th><th>Price</th><th>Stock</th><th>Warnings</th></tr></thead>
          <tbody>{''.join(render_item_row(item, provenance=provenance) for item in items) or '<tr><td colspan="6">Evidence pending.</td></tr>'}</tbody>
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
  <script type="application/json" id="refresh-metadata">{refresh_json}</script>
  <script data-refresh-hydration>
    (() => {{
      const root = document.querySelector("[data-refresh-root]");
      if (!root) return;
      const stateNode = document.getElementById("refresh-status");
      const heroStateNode = document.getElementById("hero-data-state");
      const ageNode = document.getElementById("refresh-age");
      const reasonNode = document.getElementById("refresh-reason");
      const successAt = Date.parse(root.dataset.successAt || "");
      const attemptAt = Date.parse(root.dataset.attemptAt || "");
      const cadence = Number(root.dataset.cadenceMinutes || 0);
      const grace = Number(root.dataset.graceMinutes || 0);
      const attemptStatus = root.dataset.attemptStatus || "unknown";
      const archived = root.dataset.archived === "true";
      const represented = root.dataset.represented === "true";
      const labels = {{
        Fresh: "Data is within the 48-hour refresh cadence.",
        Due: "Data is due but remains inside the 3-hour grace window.",
        Stale: "Data is older than the cadence and grace window.",
        Unknown: "No successful data refresh is recorded.",
        Archived: "This tracker is archived and no longer refreshes."
      }};
      const ageLabel = (minutes) => {{
        const days = Math.floor(minutes / 1440);
        const hours = Math.floor((minutes % 1440) / 60);
        const mins = minutes % 60;
        if (days) return `${{days}} day${{days === 1 ? "" : "s"}} ${{hours}} hour${{hours === 1 ? "" : "s"}}`;
        if (hours) return `${{hours}} hour${{hours === 1 ? "" : "s"}}`;
        return `${{mins}} minute${{mins === 1 ? "" : "s"}}`;
      }};
      const applyRecommendationState = (state) => {{
        const actionable = represented && ["Fresh", "Due"].includes(state);
        const mode = actionable ? "fresh" : state === "Unknown" ? "unknown" : "historical";
        document.body.classList.toggle("recommendations-historical", !actionable);
        document.body.classList.toggle("recommendations-unverified", mode === "unknown");
        document.querySelectorAll("[data-recommendation-label], [data-recommendation-summary], [data-retailer-heading], [data-row-metric]").forEach((node) => {{
          node.textContent = mode === "fresh" ? node.dataset.freshText : mode === "unknown" ? node.dataset.unknownText : node.dataset.historicalText;
        }});
        document.querySelectorAll("[data-recommendation-card]").forEach((card) => {{
          card.classList.toggle("historical", mode === "historical");
          card.classList.toggle("unverified", mode === "unknown");
        }});
        document.querySelectorAll("[data-fresh-treatment]").forEach((chip) => {{
          chip.classList.toggle("good", mode === "fresh");
          chip.classList.toggle("historical", mode === "historical");
          chip.classList.toggle("unverified", mode === "unknown");
          chip.textContent = mode === "fresh" ? chip.dataset.freshText : mode === "unknown" ? chip.dataset.unknownText : chip.dataset.historicalText;
        }});
        const warning = document.getElementById("historical-warning");
        if (warning) {{
          warning.hidden = actionable;
          warning.textContent = mode === "unknown" ? warning.dataset.unknownText : warning.dataset.historicalText;
        }}
      }};
      const applyState = (state, reason, age) => {{
        stateNode.textContent = state;
        heroStateNode.textContent = state;
        stateNode.className = `state-badge ${{state.toLowerCase()}}`;
        ageNode.textContent = age;
        reasonNode.textContent = reason;
        applyRecommendationState(state);
      }};
      const update = () => {{
        if (archived) {{
          applyState("Archived", labels.Archived, ageNode.textContent);
          return;
        }}
        if (!Number.isFinite(successAt)) {{
          applyState("Unknown", labels.Unknown, "Unknown");
          return;
        }}
        const elapsed = Date.now() - successAt;
        if (elapsed < 0) {{
          applyState("Unknown", "The recorded data refresh is in the future.", "Unknown");
          return;
        }}
        const age = Math.floor(elapsed / 60000);
        if (!["success", "unknown"].includes(attemptStatus) && Number.isFinite(attemptAt) && attemptAt > successAt) {{
          applyState("Blocked", root.dataset.stateReason, ageLabel(age));
          return;
        }}
        const state = elapsed <= cadence * 60000 ? "Fresh" : elapsed <= (cadence + grace) * 60000 ? "Due" : "Stale";
        applyState(state, labels[state], ageLabel(age));
      }};
      update();
      window.setInterval(update, 60000);
    }})();
  </script>
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
