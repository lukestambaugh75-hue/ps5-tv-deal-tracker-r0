import csv
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone


class TrackerTests(unittest.TestCase):
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
        payload = build_payload(data, "https://example.com/dashboard")

        self.assertEqual(payload["to"], ["lukestambaugh75@gmail.com", "devin.mullen89@gmail.com"])
        self.assertEqual(payload["cc"], [])
        self.assertEqual(payload["bcc"], [])
        self.assertIn("PS5", payload["subject"])
        self.assertIn("https://example.com/dashboard", payload["body_text"])

    def test_dashboard_contains_core_sections_and_no_raw_home_address(self):
        from tools.render_dashboard import render_dashboard
        from tools.tracker_core import apply_evidence

        now, evidence = self._fresh_evidence()
        data = apply_evidence(self._seed_data(), evidence, now=now)
        html = render_dashboard(data, history_rows=[], dashboard_url="https://example.com/dashboard")

        self.assertIn("Best Buy Today", html)
        self.assertIn("PS5", html)
        self.assertIn("65-inch TV", html)
        self.assertIn("https://lukestambaugh75-hue.github.io/kegerator-tracker-r0/", html)
        self.assertIn("Main Dashboard", html)
        self.assertIn("https://lukestambaugh75-hue.github.io/daily-dashboards-public-safe-r0/", html)
        self.assertIn("Price History", html)
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
