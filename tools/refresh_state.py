#!/usr/bin/env python3
"""Pure refresh-state and Central-time helpers for generated tracker outputs."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


CENTRAL_ZONE = ZoneInfo("America/Chicago")
DEFAULT_CADENCE_MINUTES = 2880
DEFAULT_GRACE_MINUTES = 180


def parse_utc(value):
    """Parse an ISO timestamp and return an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_iso(value):
    """Normalize a datetime or ISO timestamp to the repository's UTC form."""
    parsed = value if isinstance(value, datetime) else parse_utc(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def format_central(value):
    """Format a UTC timestamp in Central time with its truthful CST/CDT label."""
    parsed = value if isinstance(value, datetime) else parse_utc(value)
    if parsed is None:
        return "Not recorded"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(CENTRAL_ZONE)
    hour = local.strftime("%I").lstrip("0") or "0"
    return f"{local.strftime('%b')} {local.day}, {local.year} {hour}:{local.strftime('%M %p %Z')}"


def format_age(age_minutes):
    """Return a compact human-readable duration for a non-negative age."""
    if age_minutes is None:
        return "Unknown"
    total = max(0, int(age_minutes))
    days, remainder = divmod(total, 1440)
    hours, minutes = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not parts or (not days and minutes):
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


def evaluate_refresh(refresh, now=None):
    """Derive Fresh, Due, Stale, Blocked, Archived, or Unknown from metadata.

    Fresh includes the exact cadence boundary. Due begins immediately after
    cadence and includes the exact cadence-plus-grace boundary.
    """
    refresh = dict(refresh or {})
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    cadence = int(refresh.get("cadence_minutes") or DEFAULT_CADENCE_MINUTES)
    grace = int(refresh.get("grace_minutes") or DEFAULT_GRACE_MINUTES)
    data_refreshed = parse_utc(refresh.get("data_refreshed_at_utc"))
    attempt_at = parse_utc(refresh.get("last_attempt_at_utc"))
    attempt_status = str(refresh.get("last_attempt_status") or "unknown").lower()
    attempt_reason = str(refresh.get("last_attempt_reason") or "").strip()

    result = {
        "state": "Unknown",
        "reason": "No successful data refresh is recorded.",
        "evaluated_at_utc": utc_iso(now),
        "data_refreshed_at_utc": utc_iso(data_refreshed),
        "data_refreshed_at_central": format_central(data_refreshed),
        "last_attempt_at_utc": utc_iso(attempt_at),
        "last_attempt_at_central": format_central(attempt_at),
        "last_attempt_status": attempt_status,
        "last_attempt_reason": attempt_reason or None,
        "cadence_minutes": cadence,
        "grace_minutes": grace,
        "age_minutes": None,
        "age_label": "Unknown",
        "next_due_at_utc": None,
        "next_due_at_central": "Not recorded",
        "stale_after_at_utc": None,
        "stale_after_at_central": "Not recorded",
        "timezone": refresh.get("timezone") or "America/Chicago",
        "archived": bool(refresh.get("archived")),
        "source_count": int(refresh.get("source_count") or 0),
        "row_count": int(refresh.get("row_count") or 0),
        "quality_counts": dict(refresh.get("quality_counts") or {}),
        "rendered_at_utc": refresh.get("rendered_at_utc"),
        "published_at_utc": refresh.get("published_at_utc"),
    }

    if data_refreshed is not None:
        age_seconds = (now - data_refreshed).total_seconds()
        age_minutes = max(0, int(age_seconds // 60))
        next_due = data_refreshed + timedelta(minutes=cadence)
        stale_after = next_due + timedelta(minutes=grace)
        result.update(
            {
                "age_minutes": age_minutes,
                "age_label": format_age(age_minutes),
                "next_due_at_utc": utc_iso(next_due),
                "next_due_at_central": format_central(next_due),
                "stale_after_at_utc": utc_iso(stale_after),
                "stale_after_at_central": format_central(stale_after),
            }
        )

    if result["archived"]:
        result["state"] = "Archived"
        result["reason"] = "This tracker is archived and no longer refreshes."
        return result

    if data_refreshed is None:
        return result

    if data_refreshed > now:
        result["age_minutes"] = None
        result["age_label"] = "Unknown"
        result["reason"] = "The recorded data refresh is in the future."
        return result

    if (
        attempt_status not in {"success", "unknown"}
        and attempt_at is not None
        and attempt_at > data_refreshed
    ):
        result["state"] = "Blocked"
        detail = attempt_reason or "The latest refresh attempt did not complete."
        result["reason"] = f"Latest attempt {attempt_status}: {detail}"
        return result

    age_seconds = (now - data_refreshed).total_seconds()
    cadence_seconds = cadence * 60
    stale_seconds = (cadence + grace) * 60
    if age_seconds <= cadence_seconds:
        result["state"] = "Fresh"
        result["reason"] = "Data is within the 48-hour refresh cadence."
    elif age_seconds <= stale_seconds:
        result["state"] = "Due"
        result["reason"] = "Data is due but remains inside the 3-hour grace window."
    else:
        result["state"] = "Stale"
        result["reason"] = "Data is older than the cadence and grace window."
    return result
