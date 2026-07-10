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
        self.assertNotIn("fresh_evidence_status", updated["daily_brief"])
        self.assertEqual(updated["refresh"]["data_refreshed_at_utc"], "2026-07-01T12:00:00Z")
        self.assertEqual(updated["refresh"]["last_attempt_status"], "success")

    def test_refresh_state_uses_inclusive_fresh_due_and_stale_boundaries(self):
        from tools.refresh_state import evaluate_refresh

        refreshed = datetime(2026, 1, 1, tzinfo=timezone.utc)
        refresh = {
            "data_refreshed_at_utc": refreshed.isoformat().replace("+00:00", "Z"),
            "last_attempt_at_utc": refreshed.isoformat().replace("+00:00", "Z"),
            "last_attempt_status": "success",
            "last_attempt_reason": None,
            "cadence_minutes": 2880,
            "grace_minutes": 180,
            "timezone": "America/Chicago",
            "archived": False,
        }

        self.assertEqual(
            evaluate_refresh(refresh, now=refreshed + timedelta(minutes=2880))["state"],
            "Fresh",
        )
        self.assertEqual(
            evaluate_refresh(
                refresh, now=refreshed + timedelta(minutes=2880, seconds=1)
            )["state"],
            "Due",
        )
        self.assertEqual(
            evaluate_refresh(refresh, now=refreshed + timedelta(minutes=3060))["state"],
            "Due",
        )
        self.assertEqual(
            evaluate_refresh(
                refresh, now=refreshed + timedelta(minutes=3060, seconds=1)
            )["state"],
            "Stale",
        )

    def test_central_time_formatting_uses_cst_and_cdt(self):
        from tools.refresh_state import format_central

        self.assertEqual(
            format_central("2026-01-15T12:00:00Z"),
            "Jan 15, 2026 6:00 AM CST",
        )
        self.assertEqual(
            format_central("2026-07-15T12:00:00Z"),
            "Jul 15, 2026 7:00 AM CDT",
        )

    def test_first_failed_attempt_is_blocked_instead_of_unknown(self):
        from tools.refresh_state import evaluate_refresh

        now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        refresh = {
            "data_refreshed_at_utc": None,
            "last_attempt_at_utc": "2026-07-01T12:00:00Z",
            "last_attempt_status": "blocked",
            "last_attempt_reason": "No source was reachable.",
            "cadence_minutes": 2880,
            "grace_minutes": 180,
            "timezone": "America/Chicago",
            "archived": False,
        }

        state = evaluate_refresh(refresh, now=now)

        self.assertEqual(state["state"], "Blocked")
        self.assertIn("No source was reachable", state["reason"])

    def test_blocked_attempt_preserves_complete_truth_and_updates_attempt_only(self):
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        prior_items = json.loads(json.dumps(complete["items"]))
        prior_summary = complete["daily_brief"]["summary"]
        prior_success = complete["refresh"]["data_refreshed_at_utc"]
        attempted = now + timedelta(hours=1)

        blocked, succeeded = process_evidence_attempt(
            complete,
            {"status": "blocked", "reason": "Retailer challenge blocked evidence."},
            now=attempted,
        )

        self.assertFalse(succeeded)
        self.assertEqual(blocked["items"], prior_items)
        self.assertEqual(blocked["daily_brief"]["summary"], prior_summary)
        self.assertEqual(blocked["refresh"]["data_refreshed_at_utc"], prior_success)
        self.assertEqual(blocked["refresh"]["last_attempt_at_utc"], "2026-07-01T13:00:00Z")
        self.assertEqual(blocked["refresh"]["last_attempt_status"], "blocked")
        self.assertEqual(
            blocked["refresh"]["last_attempt_reason"],
            "Retailer challenge blocked evidence.",
        )

    def test_partial_packet_preserves_complete_truth_and_records_partial_attempt(self):
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        partial = json.loads(json.dumps(evidence))
        partial["sources"] = [partial["sources"][0]]
        attempted = now + timedelta(hours=1)

        blocked, succeeded = process_evidence_attempt(complete, partial, now=attempted)

        self.assertFalse(succeeded)
        self.assertEqual(blocked["items"], complete["items"])
        self.assertEqual(blocked["daily_brief"], complete["daily_brief"])
        self.assertEqual(
            blocked["refresh"]["data_refreshed_at_utc"],
            complete["refresh"]["data_refreshed_at_utc"],
        )
        self.assertEqual(blocked["refresh"]["last_attempt_status"], "partial")
        self.assertIn("missing target", blocked["refresh"]["last_attempt_reason"])

    def test_failed_packet_changes_only_attempt_fields(self):
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        invalid = json.loads(json.dumps(evidence))
        invalid["sources"][0]["price"] = None
        attempted = now + timedelta(hours=1)

        failed, succeeded = process_evidence_attempt(complete, invalid, now=attempted)

        self.assertFalse(succeeded)
        self.assertEqual(failed["items"], complete["items"])
        self.assertEqual(failed["daily_brief"], complete["daily_brief"])
        self.assertEqual(failed["meta"], complete["meta"])
        self.assertEqual(
            failed["refresh"]["data_refreshed_at_utc"],
            complete["refresh"]["data_refreshed_at_utc"],
        )
        self.assertEqual(
            failed["refresh"]["source_count"], complete["refresh"]["source_count"]
        )
        self.assertEqual(failed["refresh"]["row_count"], complete["refresh"]["row_count"])
        self.assertEqual(
            failed["refresh"]["quality_counts"], complete["refresh"]["quality_counts"]
        )
        self.assertEqual(failed["refresh"]["last_attempt_status"], "failed")
        self.assertEqual(failed["refresh"]["last_attempt_at_utc"], "2026-07-01T13:00:00Z")

    def test_history_skips_blocked_stale_and_unrepresented_snapshots(self):
        from tools.append_history import build_history_rows
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        blocked, _ = process_evidence_attempt(
            complete,
            {"status": "blocked", "reason": "Source unavailable."},
            now=now + timedelta(hours=1),
        )
        stale_now = now + timedelta(minutes=3060, seconds=1)
        unrepresented = json.loads(json.dumps(complete))
        unrepresented["items"] = [
            row for row in unrepresented["items"] if row["target_id"] == "ps5"
        ]

        self.assertEqual(build_history_rows(blocked, now=now + timedelta(hours=1)), [])
        self.assertEqual(build_history_rows(complete, now=stale_now), [])
        self.assertEqual(build_history_rows(unrepresented, now=now), [])

    def test_non_actionable_email_reports_evidence_without_prices_or_best_claims(self):
        from tools.build_email import build_payload
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        blocked, _ = process_evidence_attempt(
            complete,
            {"status": "blocked", "reason": "Retailer challenge."},
            now=now + timedelta(hours=1),
        )
        stale = complete
        unknown = self._seed_data()

        cases = (
            ("Blocked", blocked, now + timedelta(hours=1)),
            ("Stale", stale, now + timedelta(minutes=3060, seconds=1)),
            ("Unknown", unknown, now),
        )
        for state, data, built_at in cases:
            with self.subTest(state=state):
                payload = build_payload(data, self.DASHBOARD_URL, now=built_at)
                combined = payload["body_text"] + payload["body_html"]
                self.assertIn(f"Refresh state: {state}", payload["body_text"])
                self.assertIn("Last successful data refresh:", payload["body_text"])
                self.assertIn("Latest attempt:", payload["body_text"])
                self.assertIn("State reason:", payload["body_text"])
                self.assertIn(self.DASHBOARD_URL, combined)
                self.assertNotIn("$", combined)
                self.assertNotIn("best row", combined.lower())
                self.assertNotIn("current best", combined.lower())

    def test_dashboard_embeds_and_displays_refresh_metadata_with_inline_hydration(self):
        from tools.render_dashboard import render_dashboard
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)

        html_text = render_dashboard(
            data,
            history_rows=[],
            dashboard_url=self.DASHBOARD_URL,
            now=now,
        )

        self.assertIn('id="refresh-status"', html_text)
        self.assertIn("Last successful data refresh", html_text)
        self.assertIn("Jul 1, 2026 7:00 AM CDT", html_text)
        self.assertIn("Age", html_text)
        self.assertIn("Every 48 hours", html_text)
        self.assertIn("Next due", html_text)
        self.assertIn("Latest attempt", html_text)
        self.assertIn("State reason", html_text)
        self.assertIn("Render / publish", html_text)
        self.assertIn('<script type="application/json" id="refresh-metadata">', html_text)
        self.assertIn("data-refresh-hydration", html_text)
        self.assertIn('"state": "Fresh"', html_text)

    def test_checked_in_data_migrates_exact_july_8_success_without_literal_freshness(self):
        with open("data/deals.json", encoding="utf-8") as f:
            data = json.load(f)

        self.assertNotIn("generated_at_utc", data["meta"])
        self.assertNotIn("fresh_evidence_status", data["daily_brief"])
        self.assertEqual(data["refresh"]["data_refreshed_at_utc"], "2026-07-08T06:02:29Z")
        self.assertEqual(data["refresh"]["last_attempt_at_utc"], "2026-07-08T06:02:29Z")
        self.assertEqual(data["refresh"]["last_attempt_status"], "success")
        self.assertEqual(data["refresh"]["cadence_minutes"], 2880)
        self.assertEqual(data["refresh"]["grace_minutes"], 180)
        self.assertEqual(data["refresh"]["timezone"], "America/Chicago")
        self.assertFalse(data["refresh"]["archived"])
        self.assertEqual(data["refresh"]["source_count"], 16)
        self.assertEqual(data["refresh"]["row_count"], 16)
        self.assertIsInstance(data["refresh"]["quality_counts"], dict)
        self.assertIsNone(data["refresh"]["published_at_utc"])

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

    def test_audience_guard_rejects_inline_event_handler_navigation(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            """<button onclick="window.location='https://lukestambaugh75-hue.github.io/kegerator-tracker-r0/'">Open</button></body>""",
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("event handler", completed.stderr.lower())

    def test_audience_guard_treats_svg_href_as_a_local_resource_load(self):
        data, html_text, payload = self._audience_fixture()
        current_product_url = data["items"][0]["url"]

        for tag in ("image", "use", "feImage"):
            with self.subTest(tag=tag):
                candidate = html_text.replace(
                    "</body>",
                    f'<svg><{tag} href="{current_product_url}"></{tag}></svg></body>',
                )
                completed = self._run_guard(candidate, data, payload)
                self.assertEqual(completed.returncode, 1)
                self.assertIn("external resource", completed.stderr.lower())

    def test_audience_guard_allows_svg_image_to_load_an_existing_local_asset(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            '<svg><image href="assets/electronics-hero.png"></image></svg></body>',
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_audience_guard_rejects_uninspected_srcdoc(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            """<iframe srcdoc="&lt;a href='https://evil.example/dashboard'&gt;Other&lt;/a&gt;"></iframe></body>""",
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("srcdoc", completed.stderr.lower())

    def test_audience_guard_rejects_ping_targets(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            f'<a href="{self.DASHBOARD_URL}" ping="https://evil.example/audit">Open</a></body>',
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("ping", completed.stderr.lower())

    def test_audience_guard_allows_forbidden_words_inside_a_longer_product_name(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "Current retailer product", "PlayStation 5 Raptor Edition product"
        )
        payload["body_text"] += "\nProduct: PlayStation 5 Raptor Edition"
        payload["body_html"] += "\n<p>Product: PlayStation 5 Raptor Edition</p>"

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_audience_guard_rejects_forbidden_words_in_interactive_navigation(self):
        data, html_text, payload = self._audience_fixture()
        html_text = html_text.replace(
            "</body>",
            f'<a href="{self.DASHBOARD_URL}">Main Dashboard</a></body>',
        )

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("forbidden cross-dashboard navigation text", completed.stderr)

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
        rows = build_history_rows(data, today="2026-07-01", now=now)
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
