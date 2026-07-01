# PS5 and TV Deal Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scheduled public PS5 and TV deal dashboard with fresh evidence checks and email delivery to Luke and Devin.

**Architecture:** Use a static HTML dashboard rendered from `data/deals.json`, with Python tools for evidence validation, rendering, history, email payloads, and public verification. A Codex cron automation gathers fresh browser/web evidence every other day, updates the repo, pushes to GitHub Pages, and sends the generated summary email.

**Tech Stack:** Python 3 standard library, Pillow for a generated local PNG hero asset, unittest, static HTML/CSS, GitHub Pages, Codex cron automation.

## Global Constraints

- New repo path: `/Users/lukestambaugh/Documents/Files for GitHub/PS5 and TV Deal Tracker r0`.
- Public dashboard is allowed and required.
- Purchase area is big-box retailers or Houston-area pickup/delivery.
- TV default is a 65-inch mid-quality 4K smart TV, with 60-70 inch deals allowed.
- Email recipients are exactly `lukestambaugh75@gmail.com` and `devin.mullen89@gmail.com`; no CC/BCC.
- Schedule is 6:00 AM Central every other day.
- Do not quote old prices as current when fresh evidence fails.
- Manufacturer-direct reference rows are useful for MSRP context but should not outrank equivalent big-box or Houston-area buy paths.
- Do not include Luke's home address on the dashboard.

---

### Task 1: Core Evidence and Ranking

**Files:**
- Create: `tests/test_tracker.py`
- Create: `tools/tracker_core.py`

**Interfaces:**
- Consumes: evidence packets shaped as `{"captured_at": "...", "sources": [...]}`.
- Produces: `validate_evidence(evidence, now=None)`, `apply_evidence(data, evidence, now=None)`, `best_rows_by_target(data)`.

- [ ] **Step 1: Write the failing tests**

Create tests that import `tools.tracker_core`, reject stale evidence, apply fresh evidence, and rank available rows.

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`

Expected: import failure because `tools.tracker_core` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `tools/tracker_core.py` with timestamp parsing, retailer/source validation, evidence freshness checks, row updates, best-row ranking, and dashboard summary helpers.

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`

Expected: all tests pass.

### Task 2: Render Dashboard, History, and Email Payload

**Files:**
- Create: `data/deals.json`
- Create: `tools/render_dashboard.py`
- Create: `tools/append_history.py`
- Create: `tools/build_email.py`
- Create: `assets/create_hero_asset.py`
- Generate: `assets/electronics-hero.png`

**Interfaces:**
- Consumes: `data/deals.json`, `history.csv`, and `tracker_core.best_rows_by_target(data)`.
- Produces: `index.html`, `history.csv`, `out/latest-email.json`, and a local PNG hero asset.

- [ ] **Step 1: Extend tests**

Add tests for exact email recipients, no CC/BCC, LF-only history output, and dashboard section text without raw home-address leakage.

- [ ] **Step 2: Run test to verify it fails**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`

Expected: failures for missing renderer, history, and email modules.

- [ ] **Step 3: Implement scripts**

Render a self-contained dashboard with best buys, price ladders, warnings, and history. Append one history row per target per run. Build an email JSON payload addressed to Luke and Devin.

- [ ] **Step 4: Run test to verify it passes**

Run: `/usr/bin/python3 -m unittest tests.test_tracker -v`

Expected: all tests pass.

### Task 3: Operations, Verification, and Automation

**Files:**
- Create: `Makefile`
- Create: `README.md`
- Create: `OPEN-ME-FIRST.md`
- Create: `tools/refresh_prices_browser.py`
- Create: `tools/verify_dashboard.py`
- Create: `tools/check_public_pages.py`
- Create: `tools/serve_dashboard.py`
- Create: `automation/ps5-tv-deal-tracker-email.toml`
- Create: `.nojekyll`

**Interfaces:**
- Consumes: source tools from Tasks 1 and 2.
- Produces: a repeatable local run contract and the repo mirror of the Codex automation.

- [ ] **Step 1: Add command targets**

Create `make refresh`, `make render`, `make history`, `make email-content`, `make verify`, `make open`, `make pages-check`, and `make public-verify`.

- [ ] **Step 2: Verify full local run**

Run: `make verify`

Expected: JSON validation, unit tests, dashboard verification, and `git diff --check` pass.

- [ ] **Step 3: Publish**

Create the public GitHub repo, push `main`, enable Pages from the root of `main`, and verify the public URL.

- [ ] **Step 4: Register schedule**

Create the Codex automation at 6:00 AM Central every other day with the same prompt mirrored in `automation/ps5-tv-deal-tracker-email.toml`.
