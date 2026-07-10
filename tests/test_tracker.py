import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class TrackerTests(unittest.TestCase):
    DASHBOARD_URL = "https://lukestambaugh75-hue.github.io/ps5-tv-deal-tracker-r0/"

    def _check_commands_from_makefile(self, makefile_path):
        makefile = Path(makefile_path).resolve()
        completed = subprocess.run(
            [
                "make",
                "--no-builtin-rules",
                "--dry-run",
                "--file",
                str(makefile),
                "check",
            ],
            cwd=makefile.parent,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout

    def test_check_command_expansion_includes_mutating_prerequisites(self):
        with tempfile.TemporaryDirectory() as tmp:
            makefile = Path(tmp, "Makefile")
            makefile.write_text(
                """check: hidden-mutations

hidden-mutations:
\t/usr/bin/python3 tools/refresh_prices_browser.py
\t/usr/bin/python3 tools/append_history.py
\t/usr/bin/python3 assets/create_hero_asset.py
\t/usr/bin/python3 tools/render_dashboard.py
\t/usr/bin/python3 tools/build_email.py
""",
                encoding="utf-8",
            )
            expanded = self._check_commands_from_makefile(makefile)

        for expected in (
            "refresh_prices_browser.py",
            "append_history.py",
            "create_hero_asset.py",
            "render_dashboard.py",
            "build_email.py",
        ):
            self.assertIn(expected, expanded)

    def test_check_dry_run_excludes_mutating_tracker_commands(self):
        check_contract = self._check_commands_from_makefile("Makefile")

        for forbidden in (
            "refresh_prices_browser.py",
            "append_history.py",
            "create_hero_asset.py",
            "render_dashboard.py",
            "build_email.py",
        ):
            self.assertNotIn(forbidden, check_contract)

    def _fresh_evidence(self):
        now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        return now, {
            "captured_at": now.isoformat().replace("+00:00", "Z"),
            "purchase_area": "Houston area",
            "sources": [
                {
                    "target_id": "ps5",
                    "retailer": "Walmart",
                    "brand": "Sony",
                    "model": "PlayStation 5 Slim Disc Console - 1TB",
                    "product_name": "PlayStation 5 Disc Console Slim - 1TB",
                    "price": 649.00,
                    "list_price": 649.99,
                    "url": "https://www.walmart.com/ip/PlayStation-5-Disc-Console-Slim/17816601985",
                    "stock_status": "available",
                    "pickup_delivery": "Houston-area pickup or delivery shown",
                    "evidence_class": "houston_visible_buy_path",
                    "condition": "new",
                    "quality_tier": "standard",
                    "evidence_text": "Current price $649.00. Pickup and delivery options shown.",
                },
                {
                    "target_id": "tv",
                    "retailer": "Walmart",
                    "brand": "TCL",
                    "model": "65QM6K",
                    "product_name": "TCL 65 inch QM6K QD-Mini LED QLED 4K Smart TV",
                    "price": 528.00,
                    "list_price": 699.99,
                    "url": "https://www.walmart.com/browse/electronics/65-inch-tvs/tcl/3944_1060825_2489948_3421074/YnJhbmQ6VENM",
                    "stock_status": "available",
                    "pickup_delivery": "Shipping available",
                    "evidence_class": "big_box_public_price",
                    "condition": "new",
                    "quality_tier": "mid",
                    "size_inches": 65,
                    "panel": "Mini LED QLED",
                    "evidence_text": "TCL 65 inch QM6K current price $528.00.",
                },
            ],
        }

    def _seed_data(self):
        return {
            "meta": {"tracker_name": "PS5 and TV Deal Tracker", "blocker": "seed pending"},
            "targets": [
                {"id": "ps5", "label": "PS5", "target": "PlayStation 5 console"},
                {"id": "tv", "label": "65-inch TV", "target": "60-70 inch mid-quality 4K smart TV"},
            ],
            "items": [],
            "daily_brief": {"summary": "Seed data pending fresh evidence.", "warnings": []},
        }

    def _write_guard_fixture(self, directory, html_text, data, payload):
        directory = Path(directory)
        html_path = directory / "index.html"
        data_path = directory / "deals.json"
        email_path = directory / "latest-email.json"
        html_path.write_text(html_text, encoding="utf-8")
        data_path.write_text(json.dumps(data), encoding="utf-8")
        email_path.write_text(json.dumps(payload), encoding="utf-8")
        return html_path, data_path, email_path

    def _run_guard(self, html_text, data, payload):
        with tempfile.TemporaryDirectory() as tmp:
            html_path, data_path, email_path = self._write_guard_fixture(
                tmp, html_text, data, payload
            )
            return subprocess.run(
                [
                    sys.executable,
                    "tools/audience_guard.py",
                    "--html",
                    str(html_path),
                    "--data",
                    str(data_path),
                    "--email",
                    str(email_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

    def _audience_fixture(self):
        from tools.build_email import build_payload
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        first_product_url = data["items"][0]["url"]
        html_text = f"""<!doctype html>
<html lang="en">
<head><style>.hero {{ background-image: url('assets/electronics-hero.png'); }}</style></head>
<body>
  <a href="{self.DASHBOARD_URL}">PS5 and TV Deal Tracker</a>
  <a href="{first_product_url}">Current retailer product</a>
</body>
</html>"""
        payload = build_payload(data, self.DASHBOARD_URL)
        return data, html_text, payload

    def test_stale_evidence_is_rejected(self):
        from tools.tracker_core import validate_evidence

        now, evidence = self._fresh_evidence()
        evidence["captured_at"] = (now - timedelta(hours=20)).isoformat().replace("+00:00", "Z")

        with self.assertRaisesRegex(ValueError, "stale"):
            validate_evidence(evidence, now=now)

    def test_apply_evidence_updates_rows_and_clears_blocker(self):
        from tools.tracker_core import apply_evidence, best_rows_by_target

        now, evidence = self._fresh_evidence()
        updated = apply_evidence(self._seed_data(), evidence, now=now)
        best = best_rows_by_target(updated)

        self.assertIsNone(updated["meta"]["blocker"])
        self.assertEqual(best["ps5"]["retailer"], "Walmart")
        self.assertEqual(best["tv"]["model"], "65QM6K")
        self.assertEqual(updated["daily_brief"]["fresh_evidence_status"], "fresh")

    def test_email_payload_has_exact_allowed_recipients(self):
        from tools.build_email import build_payload
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        payload = build_payload(data, self.DASHBOARD_URL)

        self.assertEqual(payload["to"], ["lukestambaugh75@gmail.com", "devin.mullen89@gmail.com"])
        self.assertEqual(payload["cc"], [])
        self.assertEqual(payload["bcc"], [])
        self.assertIn("PS5", payload["subject"])
        self.assertIn(self.DASHBOARD_URL, payload["body_text"])

    def test_email_payload_rejects_a_non_ps5_dashboard_url(self):
        from tools.audience_guard import AudienceBoundaryError
        from tools.build_email import build_payload
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)

        with self.assertRaisesRegex(AudienceBoundaryError, "dashboard_url"):
            build_payload(data, "https://evil.example/dashboard")

    def test_audience_guard_accepts_only_the_ps5_page_current_products_and_local_assets(self):
        data, html_text, payload = self._audience_fixture()

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("audience boundary passed", completed.stdout)

    def test_audience_guard_rejects_external_href(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>", '<a href="https://evil.example/hub">Main Dashboard</a></body>'
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("evil.example", completed.stderr)

    def test_audience_guard_rejects_external_src(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>", '<img src="https://evil.example/pixel.png" alt=""></body>'
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("evil.example", completed.stderr)

    def test_audience_guard_rejects_external_css_url(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</head>",
            '<style>.leak { background: url("https://evil.example/tracker.png"); }</style></head>',
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("evil.example", completed.stderr)

    def test_audience_guard_rejects_script_redirect(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            '<script>window.location.href = "https://evil.example/dashboard";</script></body>',
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("redirect", completed.stderr.lower())

    def test_audience_guard_rejects_external_email_url(self):
        data, html_text, payload = self._audience_fixture()
        payload["body_text"] += "\nOther dashboard: https://evil.example/dashboard"

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("evil.example", completed.stderr)

    def test_audience_guard_rejects_changed_recipients_or_copy_lists(self):
        data, html_text, payload = self._audience_fixture()
        payload["to"] = ["lukestambaugh75@gmail.com"]
        payload["cc"] = ["other@example.com"]

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("recipients", completed.stderr.lower())

    def test_local_dashboard_verifier_runs_the_generated_output_guard(self):
        from tools.render_dashboard import render_dashboard

        data, _, payload = self._audience_fixture()
        dashboard = render_dashboard(data, history_rows=[])
        with tempfile.TemporaryDirectory() as tmp:
            html_path, data_path, email_path = self._write_guard_fixture(
                tmp, dashboard, data, payload
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/verify_dashboard.py",
                    "--input",
                    str(html_path),
                    "--data",
                    str(data_path),
                    "--email",
                    str(email_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("dashboard verification passed", completed.stdout)

    def test_public_checker_local_mode_rejects_cross_dashboard_output_without_network(self):
        from tools.render_dashboard import render_dashboard

        data, _, payload = self._audience_fixture()
        dashboard = render_dashboard(data, history_rows=[]).replace(
            "</body>", '<a href="https://evil.example/dashboard">Other</a></body>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path, data_path, _ = self._write_guard_fixture(tmp, dashboard, data, payload)
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/check_public_pages.py",
                    "--local",
                    "--input",
                    str(html_path),
                    "--data",
                    str(data_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["source"], "local")
        self.assertFalse(result["ok"])
        self.assertIn("evil.example", result["error"])

    def test_dashboard_contains_core_sections_and_no_raw_home_address(self):
        from tools.render_dashboard import render_dashboard
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        html = render_dashboard(data, history_rows=[], dashboard_url=self.DASHBOARD_URL)

        self.assertIn("Best Buy Today", html)
        self.assertIn("PS5", html)
        self.assertIn("65-inch TV", html)
        self.assertNotIn("https://lukestambaugh75-hue.github.io/kegerator-tracker-r0/", html)
        self.assertNotIn("https://lukestambaugh75-hue.github.io/ford-raptor-tracker-r0/", html)
        self.assertNotIn("Main Dashboard", html)
        self.assertNotIn("Deal Trackers", html)
        self.assertNotIn("https://lukestambaugh75-hue.github.io/daily-dashboards-public-safe-r0/", html)
        self.assertIn("Price History", html)
        self.assertIn("Color index", html)
        self.assertIn("Green", html)
        self.assertIn("Blue", html)
        self.assertIn("Amber", html)
        self.assertIn("Red", html)
        self.assertIn("information only", html)
        self.assertIn("not a recommendation", html)
        self.assertNotIn("Andante", html)
        self.assertNotIn("8826", html)

    def test_history_rows_are_lf_only_and_one_row_per_target(self):
        from tools.append_history import build_history_rows, write_history
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        rows = build_history_rows(data, today="2026-07-01")
        self.assertEqual(len(rows), 2)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.csv")
            write_history(path, rows, today="2026-07-01")
            with open(path, "rb") as f:
                raw = f.read()
            self.assertNotIn(b"\r\n", raw)
            text = raw.decode("utf-8")
            parsed = list(csv.DictReader(io.StringIO(text)))
            self.assertEqual({row["target_id"] for row in parsed}, {"ps5", "tv"})

    def test_seed_evidence_keeps_purchase_paths_ahead_of_manufacturer_reference(self):
        with open("out/browser-price-evidence.json", encoding="utf-8") as f:
            evidence = json.load(f)
        by_retailer = {row["retailer"]: row for row in evidence["sources"] if row["target_id"] == "ps5"}

        self.assertEqual(by_retailer["Walmart"]["evidence_class"], "big_box_public_price")
        self.assertEqual(by_retailer["PlayStation Direct"]["evidence_class"], "manufacturer_direct_reference")


if __name__ == "__main__":
    unittest.main()
