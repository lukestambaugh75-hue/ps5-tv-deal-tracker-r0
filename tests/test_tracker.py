import csv
import html
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
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

        self.assertIn("node --test tests/test_dashboard_ui.mjs", check_contract)

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
  <script type="application/json" id="refresh-metadata">{{"state":"Fresh"}}</script>
  <script type="module" src="assets/dashboard-ui.mjs"></script>
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

    def test_schedule_gate_runs_on_anchor_parity_and_scheduler_jitter(self):
        from tools.schedule_gate import should_run

        for allowed in (
            datetime(2026, 7, 2, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 4, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 10, 11, 1, 57, tzinfo=timezone.utc),
        ):
            with self.subTest(now_utc=allowed):
                self.assertTrue(should_run(allowed))

        self.assertFalse(
            should_run(datetime(2026, 7, 3, 11, 0, tzinfo=timezone.utc))
        )

    def test_schedule_gate_rejects_observed_one_am_run_and_handles_dst(self):
        from tools.schedule_gate import should_run

        self.assertFalse(
            should_run(datetime(2026, 7, 10, 6, 0, 43, tzinfo=timezone.utc))
        )
        self.assertTrue(
            should_run(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc))
        )
        self.assertFalse(
            should_run(datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc))
        )

    def test_schedule_gate_skips_before_anchor_and_outside_six_am_hour(self):
        from tools.schedule_gate import should_run

        for rejected in (
            datetime(2026, 7, 1, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 10, 59, tzinfo=timezone.utc),
            datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        ):
            with self.subTest(now_utc=rejected):
                self.assertFalse(should_run(rejected))

    def test_schedule_gate_rejects_naive_or_non_utc_datetimes(self):
        from tools.schedule_gate import should_run

        with self.assertRaisesRegex(ValueError, "aware UTC"):
            should_run(datetime(2026, 7, 2, 11, 0))

        with self.assertRaisesRegex(ValueError, "aware UTC"):
            should_run(
                datetime(
                    2026,
                    7,
                    2,
                    6,
                    0,
                    tzinfo=timezone(timedelta(hours=-5)),
                )
            )

    def test_schedule_gate_rejects_invalid_configuration(self):
        from tools.schedule_gate import should_run

        now = datetime(2026, 7, 2, 11, 0, tzinfo=timezone.utc)
        invalid_settings = (
            {"timezone_name": "Not/A_Timezone"},
            {"local_hour": -1},
            {"local_hour": 24},
            {"local_hour": True},
            {"interval_days": 0},
            {"interval_days": -2},
            {"interval_days": True},
            {"anchor_date": datetime(2026, 7, 2, 0, 0)},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                should_run(now, **settings)

    def _run_schedule_gate(self, now_utc):
        return subprocess.run(
            [sys.executable, "tools/schedule_gate.py", "--now-utc", now_utc],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_schedule_gate_cli_reports_run_with_utc_local_and_reason(self):
        completed = self._run_schedule_gate("2026-07-10T11:01:57Z")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("SCHEDULE_GATE=RUN", completed.stdout)
        self.assertIn("UTC=2026-07-10T11:01:57Z", completed.stdout)
        self.assertIn("LOCAL=2026-07-10T06:01:57-05:00", completed.stdout)
        self.assertIn("REASON=", completed.stdout)

    def test_schedule_gate_cli_reports_skip_with_exit_three(self):
        completed = self._run_schedule_gate("2026-07-03T11:00:00Z")

        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertIn("SCHEDULE_GATE=SKIP", completed.stdout)
        self.assertIn("UTC=2026-07-03T11:00:00Z", completed.stdout)
        self.assertIn("LOCAL=2026-07-03T06:00:00-05:00", completed.stdout)
        self.assertIn("REASON=", completed.stdout)

    def test_schedule_gate_cli_invalid_input_exits_two_without_run_marker(self):
        for invalid in ("", "not-a-timestamp", "2026-07-02T11:00:00"):
            with self.subTest(now_utc=invalid):
                completed = self._run_schedule_gate(invalid)
                self.assertEqual(completed.returncode, 2)
                self.assertNotIn("SCHEDULE_GATE=RUN", completed.stdout)
                self.assertNotIn("SCHEDULE_GATE=RUN", completed.stderr)

    def test_automation_mirror_uses_daily_local_candidate_and_fixed_project(self):
        mirror = Path("automation/ps5-tv-deal-tracker-email.toml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'rrule = "RRULE:FREQ=DAILY;BYHOUR=6;BYMINUTE=0;BYSECOND=0"',
            mirror,
        )
        self.assertNotIn("DTSTART", mirror)
        self.assertNotIn("INTERVAL=2", mirror)
        self.assertIn('status = "ACTIVE"', mirror)
        self.assertIn('model = "gpt-5.5"', mirror)
        self.assertIn('reasoning_effort = "high"', mirror)
        self.assertIn(
            'target = { type = "project", project_id = "9135bf61-1c2f-4c3f-8b44-5d82c4a665bf" }',
            mirror,
        )

    def test_automation_mirror_gates_before_pull_and_preserves_recipients(self):
        mirror = Path("automation/ps5-tv-deal-tracker-email.toml").read_text(
            encoding="utf-8"
        )

        gate_command = "/usr/bin/python3 tools/schedule_gate.py"
        pull_command = "git pull --ff-only"
        self.assertLess(mirror.index(gate_command), mirror.index(pull_command))
        self.assertIn("exit 0", mirror)
        self.assertIn("SCHEDULE_GATE=RUN", mirror)
        self.assertIn("SCHEDULE_GATE=SKIP", mirror)
        self.assertIn("malformed output", mirror)
        self.assertIn("no pull, browsing, writes, commit, Pages action, or email", mirror)

        email_addresses = set(
            __import__("re").findall(
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", mirror
            )
        )
        self.assertEqual(
            email_addresses,
            {"lukestambaugh75@gmail.com", "devin.mullen89@gmail.com"},
        )

    def test_failed_attempt_without_prior_success_remains_unknown(self):
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

        self.assertEqual(state["state"], "Unknown")
        self.assertIn("No successful data refresh", state["reason"])

    def test_unsuccessful_attempt_equal_to_success_time_does_not_block(self):
        from tools.refresh_state import evaluate_refresh

        now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
        refresh = {
            "data_refreshed_at_utc": "2026-07-01T12:00:00Z",
            "last_attempt_at_utc": "2026-07-01T12:00:00Z",
            "last_attempt_status": "failed",
            "last_attempt_reason": "Equal-time failure record.",
            "cadence_minutes": 2880,
            "grace_minutes": 180,
            "timezone": "America/Chicago",
            "archived": False,
        }

        state = evaluate_refresh(refresh, now=now)

        self.assertEqual(state["state"], "Fresh")

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

    def test_older_complete_evidence_never_replaces_newer_success_values(self):
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        older = json.loads(json.dumps(evidence))
        older["captured_at"] = (now - timedelta(hours=1)).isoformat().replace(
            "+00:00", "Z"
        )
        older["sources"][0]["price"] = 1.00
        older["sources"][1]["price"] = 2.00

        preserved, succeeded = process_evidence_attempt(
            complete, older, now=now + timedelta(hours=1)
        )

        self.assertFalse(succeeded)
        self.assertEqual(preserved["items"], complete["items"])
        self.assertEqual(preserved["daily_brief"], complete["daily_brief"])
        self.assertEqual(
            preserved["refresh"]["data_refreshed_at_utc"],
            complete["refresh"]["data_refreshed_at_utc"],
        )
        self.assertEqual(preserved["refresh"]["last_attempt_status"], "failed")
        self.assertEqual(
            preserved["refresh"]["last_attempt_at_utc"], "2026-07-01T13:00:00Z"
        )
        self.assertIn("older than", preserved["refresh"]["last_attempt_reason"])

    def test_older_attempt_timestamp_never_overwrites_newer_attempt_fields(self):
        from tools.tracker_core import apply_evidence, process_evidence_attempt

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        newest, _ = process_evidence_attempt(
            complete,
            {"status": "blocked", "reason": "Newer source challenge."},
            now=now + timedelta(hours=2),
        )
        older = json.loads(json.dumps(evidence))
        older["captured_at"] = (now - timedelta(hours=1)).isoformat().replace(
            "+00:00", "Z"
        )
        older["sources"][0]["price"] = 1.00

        preserved, succeeded = process_evidence_attempt(
            newest, older, now=now + timedelta(hours=1)
        )

        self.assertFalse(succeeded)
        self.assertEqual(preserved, newest)

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

    def test_fresh_email_suppresses_claims_when_snapshot_is_not_fully_represented(self):
        from tools.build_email import build_payload
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        complete = apply_evidence(self._seed_data(), evidence, now=now)
        missing_tv = json.loads(json.dumps(complete))
        missing_tv["items"] = [
            row for row in missing_tv["items"] if row["target_id"] == "ps5"
        ]
        missing_tv["refresh"]["row_count"] = len(missing_tv["items"])
        missing_tv["refresh"]["source_count"] = len(missing_tv["items"])
        mismatched_time = json.loads(json.dumps(complete))
        mismatched_time["items"][0]["captured_at"] = "2026-07-01T11:59:00Z"

        for label, data in (
            ("missing target", missing_tv),
            ("mismatched capture", mismatched_time),
        ):
            with self.subTest(case=label):
                payload = build_payload(data, self.DASHBOARD_URL, now=now)
                combined = payload["body_text"] + payload["body_html"]
                self.assertEqual(payload["refresh_state"], "Fresh")
                self.assertIn("Recommendations are withheld", payload["body_text"])
                self.assertNotIn("$", combined)
                for row in complete["items"]:
                    self.assertNotIn(row["product_name"], combined)

    def test_dashboard_embeds_refresh_metadata_and_uses_local_hydration_module(self):
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
        self.assertIn('id="hero-data-state"', html_text)
        self.assertIn("Last successful data refresh", html_text)
        self.assertIn("Jul 1, 2026 7:00 AM CDT", html_text)
        self.assertIn("Age", html_text)
        self.assertIn("Every 48 hours", html_text)
        self.assertIn("Next due", html_text)
        self.assertIn("Latest attempt", html_text)
        self.assertIn("State reason", html_text)
        self.assertIn("Render / publish", html_text)
        self.assertIn('<script type="application/json" id="refresh-metadata">', html_text)
        self.assertIn('src="assets/dashboard-ui.mjs"', html_text)
        self.assertIn('"state": "Fresh"', html_text)
        self.assertNotIn("data-refresh-hydration", html_text)

    def test_future_success_stays_unknown_in_static_and_hydrated_state(self):
        from tools.render_dashboard import render_dashboard
        from tools.tracker_core import apply_evidence

        success_at, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=success_at)
        viewed_at = success_at - timedelta(hours=2)

        html_text = render_dashboard(data, history_rows=[], now=viewed_at)

        self.assertIn('id="refresh-status" class="state-badge unknown"', html_text)
        self.assertIn('<dd id="refresh-age">Unknown</dd>', html_text)
        self.assertIn('"state": "Unknown"', html_text)
        self.assertIn(
            ">Unverified stored row - no trustworthy refresh time - PS5</span>",
            html_text,
        )
        self.assertIn(
            "Unverified stored rows have no trustworthy refresh time. They are not current recommendations.",
            html_text,
        )
        self.assertNotIn(">Best row from last successful refresh", html_text)
        self.assertNotIn(">Stored values from the last successful refresh", html_text)
        self.assertIn('src="assets/dashboard-ui.mjs"', html_text)

    def test_no_success_dashboard_uses_unverified_provenance(self):
        from tools.render_dashboard import render_dashboard

        now = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

        html_text = render_dashboard(self._seed_data(), history_rows=[], now=now)

        self.assertIn(
            ">Unverified stored row - no trustworthy refresh time - PS5</span>",
            html_text,
        )
        self.assertIn("Unverified stored rows have no trustworthy refresh time", html_text)
        self.assertIn("no trustworthy refresh time", html_text)
        self.assertNotIn(">Best row from last successful refresh", html_text)
        self.assertNotIn(">Stored values from the last successful refresh", html_text)

    def test_stale_dashboard_labels_preserved_values_as_historical(self):
        from tools.render_dashboard import render_dashboard
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        stale_at = now + timedelta(minutes=3060, seconds=1)

        html_text = render_dashboard(data, history_rows=[], now=stale_at)

        self.assertIn("Best row from last successful refresh", html_text)
        self.assertIn("Stored Retailer Rows", html_text)
        self.assertIn("not current", html_text)
        self.assertIn('<body class="recommendations-historical">', html_text)
        self.assertIn('class="best-card historical"', html_text)
        self.assertNotIn(">Best Buy Today", html_text)
        self.assertNotIn(">Current Retailer Rows<", html_text)
        self.assertNotIn('class="chip good"', html_text)

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

    def test_audience_guard_reads_local_module_and_rejects_network_or_navigation_code(self):
        from tools.audience_guard import AudienceBoundaryError, _validate_script_source

        cases = {
            "absolute URL": 'const endpoint = "https://evil.example/data";',
            "dynamic import": 'import("./other.mjs");',
            "comment-separated dynamic import": 'import/**/("./other.mjs");',
            "multiline static import": 'import {\n  unsafe\n} from "./other.mjs";',
            "multiline re-export": 'export {\n  unsafe\n} from "./other.mjs";',
            "fetch": 'fetch("/data.json");',
            "navigation": 'window.location.assign("/other");',
        }
        for label, source in cases.items():
            with self.subTest(case=label), self.assertRaises(AudienceBoundaryError):
                _validate_script_source(source, "fixture.mjs")

    def test_audience_guard_ignores_import_words_inside_comments_and_strings(self):
        from tools.audience_guard import _validate_script_source

        safe_source = """
const message = 'import(\"./not-code.mjs\")';
// import { notCode } from "./not-code.mjs";
/* import ("./still-not-code.mjs"); */
window.history.replaceState(null, "", "?view=details");
"""
        _validate_script_source(safe_source, "fixture.mjs")

    def test_audience_guard_allows_safe_history_replace_state_in_local_module(self):
        from tools.audience_guard import _validate_script_source

        _validate_script_source(
            'window.history.replaceState(null, "", "?view=details");',
            "fixture.mjs",
        )

    def test_audience_guard_rejects_aliases_computed_members_and_network_globals(self):
        from tools.audience_guard import AudienceBoundaryError, _validate_script_source

        cases = {
            "fetch alias": 'const request = fetch; request("/data.json");',
            "open alias": 'const launch = open; launch("/kegerator");',
            "computed window": 'window["fetch"]("/data.json");',
            "computed history": 'history["replaceState"](null, "", "/kegerator");',
            "computed globalThis": 'globalThis["fetch"]("/data.json");',
            "computed self": 'self["open"]("/kegerator");',
            "XMLHttpRequest": 'const request = new XMLHttpRequest();',
            "WebSocket": 'const socket = new WebSocket("/socket");',
            "EventSource": 'const events = new EventSource("/events");',
            "sendBeacon": 'const beacon = navigator.sendBeacon;',
            "bare history": 'history.replaceState(null, "", "?view=details");',
            "history alias": 'const replace = window.history.replaceState;',
            "bare location": 'const query = location.search;',
            "location alias": 'const current = window.location;',
        }
        for label, source in cases.items():
            with self.subTest(case=label), self.assertRaises(AudienceBoundaryError):
                _validate_script_source(source, "fixture.mjs")

    def test_audience_guard_treats_regex_literal_text_as_non_executable(self):
        from tools.audience_guard import _javascript_tokens, _validate_script_tokens

        source = r'''
const importPattern = /import\s*\(/;
const fetchPattern = /fetch\s*\(/;
if (true) {} /fetch/.test("fetch");
'''
        _validate_script_tokens(_javascript_tokens(source), "regex-fixture.mjs")

    def test_script_semantics_reject_remaining_navigation_and_execution_bypasses(self):
        from tools.audience_guard import (
            AudienceBoundaryError,
            _javascript_tokens,
            _validate_script_tokens,
        )

        cases = {
            "document computed location": 'document["location"] = "/kegerator";',
            "parent computed navigation": 'parent["location"] = "/kegerator";',
            "top computed navigation": 'top["location"] = "/kegerator";',
            "shadowed query builder": 'const setViewQuery = () => "/kegerator"; window.history.replaceState(null, "", setViewQuery(window.location.search, selected) + window.location.hash);',
            "image beacon": 'const pixel = new Image(); pixel.src = "/collect";',
            "eval alias": 'const execute = eval; execute("2 + 2");',
            "Function constructor": 'const execute = new Function("return 2 + 2");',
        }
        for label, source in cases.items():
            with self.subTest(case=label), self.assertRaises(AudienceBoundaryError):
                _validate_script_tokens(_javascript_tokens(source), "fixture.mjs")

    def test_dashboard_guard_pins_the_only_allowed_local_ui_module(self):
        from tools.audience_guard import AudienceBoundaryError, validate_dashboard_html

        data, html_text, _ = self._audience_fixture()
        source = Path("assets/dashboard-ui.mjs").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "assets" / "electronics-hero.png").write_bytes(b"fixture")
            module = root / "assets" / "dashboard-ui.mjs"
            module.write_bytes(source)
            validate_dashboard_html(html_text, data, asset_root=root)

            module.write_bytes(source + b"\n// mutation")
            with self.assertRaises(AudienceBoundaryError):
                validate_dashboard_html(html_text, data, asset_root=root)

            module.write_bytes(source)
            wrong_path = html_text.replace(
                "assets/dashboard-ui.mjs", "assets/test-ui.mjs"
            )
            (root / "assets" / "test-ui.mjs").write_bytes(source)
            with self.assertRaises(AudienceBoundaryError):
                validate_dashboard_html(wrong_path, data, asset_root=root)

    def test_dashboard_guard_allows_only_valid_refresh_json_inline(self):
        from tools.audience_guard import AudienceBoundaryError, validate_dashboard_html

        data, base_html, _ = self._audience_fixture()
        valid_metadata = '<script type="application/json" id="refresh-metadata">{"state":"Fresh"}</script>'
        validate_dashboard_html(base_html, data)

        invalid_cases = (
            base_html.replace("</body>", '<script>eval("2 + 2")</script></body>'),
            base_html.replace("</body>", '<script>const value = 2;</script></body>'),
            base_html.replace(valid_metadata, '<script type="application/json" id="refresh-metadata">{not-json}</script>'),
            base_html.replace("</body>", '<script type="application/json" id="other-data">{}</script></body>'),
            base_html.replace(valid_metadata, ""),
            base_html.replace(
                '<script type="module" src="assets/dashboard-ui.mjs"></script>',
                "",
            ),
        )
        for candidate in invalid_cases:
            with self.subTest(candidate=candidate[:80]), self.assertRaises(AudienceBoundaryError):
                validate_dashboard_html(candidate, data)

    def test_audience_guard_rejects_cross_path_history_replace_state(self):
        from tools.audience_guard import AudienceBoundaryError, _validate_script_source

        cases = (
            'window.history.replaceState(null, "", "/kegerator");',
            'window.history.replaceState(null, "", "/kegerator" + "?view=details");',
            'window.history.replaceState(null, "", window.location.pathname + "?view=details");',
            'const setViewQuery = () => "/kegerator"; window.history.replaceState(null, "", setViewQuery() + window.location.hash);',
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(AudienceBoundaryError):
                _validate_script_source(source, "fixture.mjs")

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

    def test_audience_guard_allows_a_cid_inline_chart_declared_in_inline_images(self):
        data, html_text, payload = self._audience_fixture()
        payload["body_html"] += '\n<img src="cid:priceTrend" alt="Price trend">'
        payload["inline_images"] = [{"cid": "priceTrend", "path": "chart-price.png"}]

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("audience boundary passed", completed.stdout)

    def test_audience_guard_rejects_external_image_src_even_when_inline_images_present(self):
        data, html_text, payload = self._audience_fixture()
        payload["body_html"] += '\n<img src="https://evil.example/track.png" alt="tracker">'
        payload["inline_images"] = [{"cid": "priceTrend", "path": "chart-price.png"}]

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("evil.example", completed.stderr)

    def test_audience_guard_rejects_a_cid_reference_with_no_matching_inline_image(self):
        data, html_text, payload = self._audience_fixture()
        payload["body_html"] += '\n<img src="cid:unknownChart" alt="chart">'

        completed = self._run_guard(html_text, data, payload)

        self.assertEqual(completed.returncode, 1)
        self.assertIn("audience boundary violation", completed.stderr)
        self.assertIn("resource loading is not allowed", completed.stderr)

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
        html = render_dashboard(
            data,
            history_rows=[],
            dashboard_url=self.DASHBOARD_URL,
            now=now,
        )

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

    def test_dashboard_renders_each_fixture_row_once_in_six_field_compact_table(self):
        import re

        from tools.render_dashboard import render_dashboard

        with open("data/deals.json", encoding="utf-8") as f:
            data = json.load(f)
        html_text = render_dashboard(
            data,
            history_rows=[],
            dashboard_url=self.DASHBOARD_URL,
            now=datetime(2026, 7, 8, 7, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(html_text.count('data-deal-row="'), len(data["items"]))
        for item in data["items"]:
            self.assertEqual(html_text.count(f'data-deal-row="{item["id"]}"'), 1)
        rendered_rows = re.findall(r'<tr data-deal-row="[^"]+".*?</tr>', html_text, re.DOTALL)
        self.assertEqual(len(rendered_rows), len(data["items"]))
        self.assertTrue(all(row.count("<td data-label=") == 6 for row in rendered_rows))
        self.assertIn('data-view-control="compact"', html_text)
        self.assertIn('data-view-control="details"', html_text)
        self.assertIn('data-row-controls', html_text)
        self.assertIn('data-empty-state', html_text)
        self.assertIn('data-result-count', html_text)
        self.assertIn('<details class="row-details">', html_text)
        self.assertIn('<details class="history-disclosure panel"', html_text)
        self.assertNotIn('<details class="history-disclosure panel" open', html_text)
        self.assertIn(
            '</header>\n  <main>\n    <section class="section" id="price-ladder">',
            html_text,
        )
        self.assertLess(html_text.index('data-view-control="details"'), html_text.index('id="price-ladder"'))
        self.assertLess(html_text.index('id="price-ladder"'), html_text.index('class="panel color-index"'))
        self.assertLess(html_text.index('id="price-ladder"'), html_text.index('id="best-buys"'))

        summaries = re.findall(r'<summary>Evidence: ([^<]+)</summary>', html_text)
        self.assertEqual(len(summaries), len(data["items"]))
        self.assertEqual(len(set(summaries)), len(summaries))
        for item in data["items"]:
            expected = (
                f'<summary>Evidence: {html.escape(item["retailer"])} · '
                f'{html.escape(item["product_name"])}</summary>'
            )
            self.assertIn(expected, html_text)

    def test_every_generated_table_cell_has_a_nonempty_mobile_label(self):
        from html.parser import HTMLParser
        from tools.render_dashboard import render_dashboard

        class CellParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.labels = []

            def handle_starttag(self, tag, attrs):
                if tag == "td":
                    self.labels.append(dict(attrs).get("data-label"))

        with open("data/deals.json", encoding="utf-8") as f:
            data = json.load(f)
        parser = CellParser()
        parser.feed(render_dashboard(data, history_rows=[]))

        self.assertTrue(parser.labels)
        self.assertTrue(all(label and label.strip() for label in parser.labels))

    def test_dashboard_css_keeps_mobile_table_visible_without_fixed_width_escape_hatches(self):
        from tools.render_dashboard import render_dashboard

        with open("data/deals.json", encoding="utf-8") as f:
            data = json.load(f)
        html_text = render_dashboard(data, history_rows=[])

        self.assertNotIn("overflow-x: hidden", html_text)
        self.assertNotRegex(html_text, r"min-width:\s*[1-9][0-9]*(?:px|rem)")
        self.assertIn("position: sticky", html_text)
        self.assertIn(":focus-visible", html_text)
        self.assertIn("button { min-height: 44px", html_text)
        self.assertIn(".control select { width: 100%; min-height: 44px", html_text)
        with open("assets/dashboard-ui.mjs", encoding="utf-8") as f:
            ui_source = f.read()
        self.assertNotIn("location.pathname", ui_source)
        self.assertIn(
            "setViewQuery(window.location.search, selected) + window.location.hash",
            ui_source,
        )

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
