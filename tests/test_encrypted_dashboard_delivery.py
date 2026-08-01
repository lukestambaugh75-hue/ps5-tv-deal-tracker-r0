import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.encrypted_dashboard_delivery import build_bundle  # noqa: E402


def test_encrypted_dashboard_keeps_every_offer_history_and_two_person_audience():
    dashboard, brief = build_bundle()
    source = json.loads((ROOT / "data" / "deals.json").read_text(encoding="utf-8"))
    assert len(dashboard["rows"]) == len(source["items"])
    assert all(row["direct_url"].startswith("https://") for row in dashboard["rows"])
    assert all(row["history"] for row in dashboard["rows"])
    assert [address.lower() for address in brief["to"]] == [
        "lukestambaugh75@gmail.com",
        "devin.mullen89@gmail.com",
    ]
    assert brief["cc"] == [] and brief["bcc"] == []
