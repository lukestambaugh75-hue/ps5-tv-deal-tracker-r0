#!/usr/bin/env python3
"""Core evidence validation and ranking for the PS5/TV tracker."""
import copy
import re
from datetime import datetime, timezone

try:
    from .refresh_state import (
        DEFAULT_CADENCE_MINUTES,
        DEFAULT_GRACE_MINUTES,
        utc_iso,
    )
except ImportError:
    from refresh_state import (
        DEFAULT_CADENCE_MINUTES,
        DEFAULT_GRACE_MINUTES,
        utc_iso,
    )


MAX_EVIDENCE_AGE_HOURS = 12
TARGET_IDS = {"ps5", "tv"}
EVIDENCE_CLASSES = {
    "houston_visible_buy_path",
    "big_box_public_price",
    "member_only",
    "cart_only",
    "manufacturer_direct_reference",
    "marketplace_seller",
    "open_box_or_refurb",
    "out_of_stock",
    "blocked_or_stale",
}
BAD_CURRENT_CLASSES = {"out_of_stock", "blocked_or_stale"}
PENALTY_BY_CLASS = {
    "houston_visible_buy_path": -25,
    "big_box_public_price": 0,
    "member_only": 35,
    "cart_only": 50,
    "manufacturer_direct_reference": 40,
    "marketplace_seller": 250,
    "open_box_or_refurb": 300,
    "out_of_stock": 10000,
    "blocked_or_stale": 10000,
}


def parse_timestamp(value):
    if not value:
        raise ValueError("evidence missing captured_at")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid captured_at: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def money(value):
    if value is None or value == "":
        return "not shown"
    amount = float(value)
    return f"${amount:,.2f}".replace(".00", "")


def slug(value):
    text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return text or "item"


def validate_evidence(evidence, now=None, max_age_hours=MAX_EVIDENCE_AGE_HOURS):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    captured_at = parse_timestamp(evidence.get("captured_at"))
    age_hours = (now - captured_at).total_seconds() / 3600
    if age_hours < -1:
        raise ValueError("evidence captured_at is in the future")
    if age_hours > max_age_hours:
        raise ValueError(f"evidence is stale: {age_hours:.1f} hours old")

    sources = evidence.get("sources") or []
    if not sources:
        raise ValueError("evidence contains no sources")

    normalized = []
    seen_targets = set()
    for raw in sources:
        source = dict(raw)
        target_id = str(source.get("target_id") or "").strip().lower()
        if target_id not in TARGET_IDS:
            raise ValueError(f"invalid target_id: {target_id or 'missing'}")
        seen_targets.add(target_id)

        retailer = str(source.get("retailer") or "").strip()
        if not retailer:
            raise ValueError("source missing retailer")

        evidence_class = str(source.get("evidence_class") or "").strip()
        if evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"invalid evidence_class for {retailer}: {evidence_class or 'missing'}")

        url = str(source.get("url") or "").strip()
        if not url.startswith("https://"):
            raise ValueError(f"source URL must be https for {retailer}")

        evidence_text = str(source.get("evidence_text") or "").strip()
        if not evidence_text:
            raise ValueError(f"source missing evidence_text for {retailer}")

        price = source.get("price")
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
            raise ValueError(f"source price must be a positive number for {retailer}")

        if target_id == "tv" and source.get("size_inches") is not None:
            size = float(source["size_inches"])
            if size < 60 or size > 70:
                raise ValueError(f"TV source size must be 60-70 inches for {retailer}")

        source["target_id"] = target_id
        source["retailer"] = retailer
        source["price"] = float(price)
        if source.get("list_price") is not None:
            source["list_price"] = float(source["list_price"])
        source["captured_at"] = captured_at.isoformat().replace("+00:00", "Z")
        source["id"] = source_id(source)
        source["warnings"] = warnings_for(source)
        normalized.append(source)

    if seen_targets != TARGET_IDS:
        missing = ", ".join(sorted(TARGET_IDS - seen_targets))
        raise ValueError(f"fresh evidence missing target(s): {missing}")

    return captured_at, normalized


def source_id(source):
    return "-".join(
        [
            str(source["target_id"]),
            slug(source.get("retailer")),
            slug(source.get("model") or source.get("product_name")),
        ]
    )


def warnings_for(source):
    warnings = []
    evidence_class = source.get("evidence_class")
    stock_status = str(source.get("stock_status") or "").lower()
    condition = str(source.get("condition") or "new").lower()

    if evidence_class == "member_only":
        warnings.append("member-only price")
    if evidence_class == "cart_only":
        warnings.append("cart-only price")
    if evidence_class == "manufacturer_direct_reference":
        warnings.append("manufacturer-direct reference")
    if evidence_class == "marketplace_seller":
        warnings.append("marketplace seller")
    if evidence_class == "open_box_or_refurb" or condition in {"open-box", "refurbished", "renewed", "used"}:
        warnings.append("open-box/refurbished")
    if evidence_class == "out_of_stock" or "out" in stock_status:
        warnings.append("out of stock")
    if evidence_class == "blocked_or_stale":
        warnings.append("blocked or stale evidence")
    if source.get("target_id") == "tv" and str(source.get("quality_tier") or "").lower() == "entry":
        warnings.append("entry-tier TV")
    if source.get("target_id") == "ps5" and "pro" in str(source.get("model") or "").lower():
        warnings.append("PS5 Pro, not the standard target")
    return warnings


def _refresh_metadata(data):
    existing = dict(data.get("refresh") or {})
    legacy_success = data.get("meta", {}).get("generated_at_utc")
    existing.setdefault("data_refreshed_at_utc", legacy_success)
    existing.setdefault("last_attempt_at_utc", legacy_success)
    existing.setdefault("last_attempt_status", "success" if legacy_success else "unknown")
    existing.setdefault("last_attempt_reason", None)
    existing.setdefault("cadence_minutes", DEFAULT_CADENCE_MINUTES)
    existing.setdefault("grace_minutes", DEFAULT_GRACE_MINUTES)
    existing.setdefault("timezone", "America/Chicago")
    existing.setdefault("archived", False)
    existing.setdefault("source_count", len(data.get("items") or []))
    existing.setdefault("row_count", len(data.get("items") or []))
    existing.setdefault("quality_counts", {})
    existing.setdefault("rendered_at_utc", None)
    existing.setdefault("published_at_utc", None)
    return existing


def _quality_counts(sources):
    counts = {}
    for source in sources:
        label = str(source.get("evidence_class") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def record_unsuccessful_attempt(data, status, reason, attempted_at=None):
    """Record an attempt without altering the last complete evidence snapshot."""
    if status not in {"blocked", "partial", "failed"}:
        raise ValueError(f"invalid unsuccessful attempt status: {status}")
    attempted_at = attempted_at or datetime.now(timezone.utc)
    updated = copy.deepcopy(data)
    refresh = _refresh_metadata(updated)
    refresh["last_attempt_at_utc"] = utc_iso(attempted_at)
    refresh["last_attempt_status"] = status
    refresh["last_attempt_reason"] = str(reason or "Refresh attempt did not complete.").strip()
    updated["refresh"] = refresh
    return updated


def apply_evidence(data, evidence, now=None):
    captured_at, sources = validate_evidence(evidence, now=now)
    attempted_at = now or datetime.now(timezone.utc)
    updated = copy.deepcopy(data)
    updated["items"] = sorted(
        sources,
        key=lambda item: (item["target_id"], rank_score(item), item["retailer"]),
    )
    updated.setdefault("meta", {}).pop("generated_at_utc", None)
    updated["meta"]["purchase_area"] = evidence.get("purchase_area") or (
        "Big-box retailers and Houston-area pickup/delivery"
    )
    updated["meta"]["blocker"] = None

    refresh = _refresh_metadata(updated)
    refresh.update(
        {
            "data_refreshed_at_utc": utc_iso(captured_at),
            "last_attempt_at_utc": utc_iso(attempted_at),
            "last_attempt_status": "success",
            "last_attempt_reason": None,
            "cadence_minutes": DEFAULT_CADENCE_MINUTES,
            "grace_minutes": DEFAULT_GRACE_MINUTES,
            "timezone": "America/Chicago",
            "archived": False,
            "source_count": len(evidence.get("sources") or []),
            "row_count": len(sources),
            "quality_counts": _quality_counts(sources),
        }
    )
    updated["refresh"] = refresh

    best = best_rows_by_target(updated)
    warnings = sorted({warning for item in updated["items"] for warning in item.get("warnings", [])})
    updated["daily_brief"] = {
        "summary": build_summary(best),
        "warnings": warnings,
        "data_quality_gaps": [
            "Confirm final cart total, tax, pickup/delivery timing, and seller identity before buying.",
            "Member-only and cart-only prices are shown as warnings until checkout proof is visible.",
        ],
    }
    return updated


def process_evidence_attempt(data, evidence, now=None):
    """Apply a complete packet or preserve truth and record the failed attempt."""
    attempted_at = now or datetime.now(timezone.utc)
    evidence = evidence if isinstance(evidence, dict) else {}
    explicit_status = str(evidence.get("status") or "").strip().lower()
    if explicit_status in {"blocked", "partial", "failed"}:
        reason = evidence.get("reason") or evidence.get("blocker") or (
            "Refresh attempt did not complete."
        )
        return record_unsuccessful_attempt(data, explicit_status, reason, attempted_at), False

    try:
        return apply_evidence(data, evidence, now=attempted_at), True
    except Exception as exc:
        source_targets = {
            str(source.get("target_id") or "").strip().lower()
            for source in evidence.get("sources") or []
            if isinstance(source, dict)
        }
        status = "partial" if source_targets and source_targets != TARGET_IDS else "failed"
        return record_unsuccessful_attempt(data, status, str(exc), attempted_at), False


def rank_score(item):
    score = float(item.get("price") or 999999)
    score += PENALTY_BY_CLASS.get(item.get("evidence_class"), 100)
    condition = str(item.get("condition") or "new").lower()
    if condition != "new":
        score += 300
    if item.get("target_id") == "tv":
        tier = str(item.get("quality_tier") or "").lower()
        if tier == "mid":
            score -= 25
        elif tier == "premium":
            score += 150
        elif tier == "entry":
            score += 75
    return score


def best_rows_by_target(data):
    best = {}
    for target_id in TARGET_IDS:
        candidates = [
            item
            for item in data.get("items", [])
            if item.get("target_id") == target_id
            and item.get("evidence_class") not in BAD_CURRENT_CLASSES
            and "out of stock" not in item.get("warnings", [])
        ]
        if candidates:
            best[target_id] = min(candidates, key=rank_score)
    return best


def build_summary(best):
    parts = []
    if "ps5" in best:
        row = best["ps5"]
        parts.append(f"PS5: {row['retailer']} {money(row['price'])} for {row.get('product_name') or row.get('model')}.")
    if "tv" in best:
        row = best["tv"]
        parts.append(f"TV: {row['retailer']} {money(row['price'])} for {row.get('product_name') or row.get('model')}.")
    return " ".join(parts) if parts else "No current buy path passed the freshness and availability checks."
