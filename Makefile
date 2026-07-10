PY := /usr/bin/python3
PORT ?= 8766

.PHONY: refresh render history email-content json test check verify open serve pages-check public-verify hero

hero:
	$(PY) assets/create_hero_asset.py

refresh:
	$(PY) tools/refresh_prices_browser.py --evidence out/browser-price-evidence.json
	$(PY) tools/render_dashboard.py

render:
	$(PY) tools/render_dashboard.py

history:
	$(PY) tools/append_history.py

email-content:
	$(PY) tools/build_email.py --output-dir out

json:
	$(PY) -m json.tool data/deals.json >/dev/null
	$(PY) -m json.tool out/browser-price-evidence.json >/dev/null

test:
	$(PY) -m unittest discover -s tests

check: json test
	$(PY) tools/verify_dashboard.py
	git diff --check

verify: check

open:
	$(PY) tools/serve_dashboard.py --port $(PORT)

serve:
	$(PY) tools/serve_dashboard.py --port $(PORT) --no-browser

pages-check:
	$(PY) tools/check_public_pages.py

public-verify:
	$(PY) tools/verify_dashboard.py --public
