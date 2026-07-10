# PS5 and TV Deal Tracker r0

Public dashboard and scheduled email automation for PS5 and 60-70 inch TV deals.

Live dashboard:

```text
https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/
```

## Scope

- PS5: standard PlayStation 5 Disc or Digital console from authorized big-box sellers.
- TV: default 65-inch mid-quality 4K smart TV; 60-70 inch deals are allowed.
- Purchase area: big-box retailers and Houston-area pickup/delivery paths.
- Recipients: `lukestambaugh75@gmail.com` and `devin.mullen89@gmail.com` only, no CC/BCC.
- Schedule: 6:00 AM Central every other day.

## Run Locally

```bash
make check
make open
```

`make check` is the safe, non-mutating validation gate. It validates both saved
JSON inputs, runs the Python tests (including in-memory dashboard and email
rendering), checks the saved dashboard structure, and finishes with
`git diff --check`. `make verify` is an alias for the same safe gate.

`make refresh` is deliberately separate and mutating: it applies the saved
browser evidence to `data/deals.json` and rewrites `index.html`. The scheduled
run then calls the history and email targets once before using `make check`.

## Refresh Rules

Each scheduled run must gather fresh live web or browser-visible evidence before quoting a current price. If fresh evidence fails, the run must send a blocker or stale-data warning instead of treating old prices as current.

Evidence classes are visible on the dashboard:

- Houston-visible buy path
- Big-box public price
- Member-only
- Cart-only
- Manufacturer-direct reference
- Marketplace seller
- Open-box/refurbished
- Out-of-stock
- Blocked/stale

## Files

- `data/deals.json` - current source-of-truth tracker data.
- `out/browser-price-evidence.json` - latest evidence packet consumed by the refresh script.
- `history.csv` - durable best-price trend ledger.
- `index.html` - rendered public dashboard.
- `out/latest-email.json` - generated email payload for the browser Gmail send.
- `automation/ps5-tv-deal-tracker-email.toml` - repo mirror of the Codex automation.
- `tools/*.py` - refresh, render, email, history, and verification scripts.

Prices and stock are point-in-time evidence. Confirm cart total, tax, pickup/delivery timing, and seller identity before buying.
