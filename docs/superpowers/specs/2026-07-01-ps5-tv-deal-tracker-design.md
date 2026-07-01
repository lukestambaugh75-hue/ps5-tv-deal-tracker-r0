# PS5 and TV Deal Tracker Design

## Goal

Build a Raptor-style consumer electronics deal tracker for a PlayStation 5 and a 60-70 inch TV, with a public dashboard, fresh scheduled price checks, a durable price-history ledger, and scheduled email delivery.

## Scope

- Track PlayStation 5 console prices, stock, bundles, and retailer availability.
- Track 60-70 inch TVs, defaulting to a 65-inch mid-quality 4K smart TV.
- Prefer big-box retailers and Houston-area pickup or delivery paths.
- Email both `lukestambaugh75@gmail.com` and `devin.mullen89@gmail.com`.
- Send at 6:00 AM Central every other day.
- Use a public dashboard so both recipients can open it directly.

## Retailer Set

The tracker starts with Best Buy, Walmart, Target, Costco, Sam's Club, Amazon, GameStop, Sony Direct, and Home Depot. Retailer rows can be added later if they are big-box or clearly Houston-area purchase paths.

## Evidence Rules

Each scheduled run must gather fresh live evidence before quoting a current price. Acceptable evidence is a visible retailer page, cart page, pickup/delivery page, or retailer listing captured during the current run. Evidence must include target, retailer, product name, price, URL, stock or availability text, evidence class, and visible evidence text.

If fresh evidence cannot be proven, the run must not email old prices as current. It may send a stale-data or blocker warning instead.

Evidence classes:

- `houston_visible_buy_path`: public page with Houston-area pickup or delivery evidence.
- `big_box_public_price`: public big-box price without location-specific proof.
- `member_only`: Costco/Sam's/login-only/member price.
- `cart_only`: final price appears only in cart or checkout.
- `manufacturer_direct_reference`: official manufacturer price reference, useful for MSRP but not preferred over big-box/Houston-area buy paths.
- `marketplace_seller`: third-party seller or reseller marketplace row.
- `open_box_or_refurb`: open-box, refurbished, renewed, or used.
- `out_of_stock`: product is unavailable.
- `blocked_or_stale`: page was blocked, stale, or unusable.

## Dashboard

The dashboard must show:

- Best buy today for PS5.
- Best buy today for TV.
- Price ladder by target and retailer.
- New today and price-drop notes.
- Stock and pickup/delivery status.
- Warning chips for member-only, cart-only, marketplace seller, open-box/refurb, out-of-stock, and stale evidence.
- A price-history table from `history.csv`.
- A source/evidence timestamp.

The public dashboard must not include Luke's home address.

## Email

Each email must go to exactly:

- `lukestambaugh75@gmail.com`
- `devin.mullen89@gmail.com`

No CC or BCC. This approval is scoped only to this PS5 and TV tracker. The email must include the public dashboard link, current best PS5 and TV rows, price drops, stock warnings, and whether the run used fresh evidence or was blocked.

## Automation

The Codex cron automation must:

1. Work in `/Users/lukestambaugh/Documents/Files for GitHub/PS5 and TV Deal Tracker r0`.
2. Run `git pull --ff-only`.
3. Gather fresh web or browser-visible evidence for all tracked targets.
4. Write evidence to `out/browser-price-evidence.json`.
5. Run `/usr/bin/python3 tools/refresh_prices_browser.py --evidence out/browser-price-evidence.json`.
6. Render the dashboard.
7. Append the price-history ledger.
8. Build the email payload.
9. Run tests and dashboard verification.
10. Commit and push touched files on `main`.
11. Verify the public dashboard.
12. Send one Gmail email to Luke and Devin using the signed-in Chrome/Gmail browser route.

## Testing

Tests must cover:

- Stale evidence is rejected.
- Evidence updates current rows and clears blockers.
- Email recipients are exactly Luke and Devin, with no CC/BCC.
- Dashboard output includes core sections and excludes raw home-address text.
- `history.csv` uses LF line endings and one row per target per run.
