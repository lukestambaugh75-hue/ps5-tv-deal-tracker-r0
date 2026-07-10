# Open Me First

Run:

```bash
cd "/Users/lukestambaugh/Documents/Files for GitHub/PS5 and TV Deal Tracker r0"
make check
make open
```

`make check` only validates the saved data, evidence, dashboard, and email
renderers. It does not acquire prices or rewrite tracker files. Use
`make refresh` only when you intentionally want to apply a newly captured
browser-evidence packet and regenerate the dashboard.

This is a standalone direct-link tracker for Luke and Devin. It must not link
to a shared dashboard hub, Ford/Raptor, Kegerator, or any other tracker. Its
generated page may link only to this PS5/TV page and exact current retailer
URLs; loaded assets must stay local. `make check` enforces that boundary across
`index.html` and `out/latest-email.json`.

Useful focused checks:

```bash
/usr/bin/python3 tools/audience_guard.py
/usr/bin/python3 tools/check_public_pages.py --local
```

Read the first screen first. It shows the current best PS5 row, current best 65-inch TV row, warning chips, retailer rows, and price history.

Important: confirm final cart total, tax, pickup/delivery timing, and seller identity before buying. Do not treat old rows as current unless the latest run proved fresh evidence.
