#!/usr/bin/env python3
"""Fail-closed Central-time gate for the PS5/TV scheduled automation."""

import argparse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_ANCHOR_DATE = date(2026, 7, 2)
UTC_ZONE_KEYS = {"UTC", "Etc/UTC"}


def _validated_utc(now_utc):
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise ValueError("now_utc must be an aware UTC datetime")

    is_named_utc = getattr(now_utc.tzinfo, "key", None) in UTC_ZONE_KEYS
    if now_utc.tzinfo is not timezone.utc and not is_named_utc:
        raise ValueError("now_utc must be an aware UTC datetime")
    if now_utc.utcoffset() != timedelta(0):
        raise ValueError("now_utc must be an aware UTC datetime")
    return now_utc.astimezone(timezone.utc)


def _validated_settings(timezone_name, anchor_date, local_hour, interval_days):
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        raise ValueError("timezone_name must name an IANA timezone")
    try:
        local_zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"invalid timezone_name: {timezone_name!r}") from exc

    if isinstance(anchor_date, datetime) or not isinstance(anchor_date, date):
        raise ValueError("anchor_date must be a date")
    if isinstance(local_hour, bool) or not isinstance(local_hour, int):
        raise ValueError("local_hour must be an integer from 0 through 23")
    if not 0 <= local_hour <= 23:
        raise ValueError("local_hour must be an integer from 0 through 23")
    if isinstance(interval_days, bool) or not isinstance(interval_days, int):
        raise ValueError("interval_days must be a positive integer")
    if interval_days <= 0:
        raise ValueError("interval_days must be a positive integer")
    return local_zone


def _decision(
    now_utc,
    *,
    timezone_name="America/Chicago",
    anchor_date=DEFAULT_ANCHOR_DATE,
    local_hour=6,
    interval_days=2,
):
    normalized_utc = _validated_utc(now_utc)
    local_zone = _validated_settings(
        timezone_name, anchor_date, local_hour, interval_days
    )
    local_now = normalized_utc.astimezone(local_zone)
    day_delta = (local_now.date() - anchor_date).days

    if day_delta < 0:
        return False, normalized_utc, local_now, "local date is before the anchor date"
    if local_now.hour != local_hour:
        return (
            False,
            normalized_utc,
            local_now,
            f"local hour {local_now.hour} is outside the required {local_hour} AM hour",
        )
    if day_delta % interval_days:
        return (
            False,
            normalized_utc,
            local_now,
            f"local date is off the {interval_days}-day anchor parity",
        )
    return (
        True,
        normalized_utc,
        local_now,
        f"local date matches the {interval_days}-day anchor parity in the {local_hour} AM hour",
    )


def should_run(
    now_utc,
    *,
    timezone_name="America/Chicago",
    anchor_date=DEFAULT_ANCHOR_DATE,
    local_hour=6,
    interval_days=2,
):
    """Return whether an aware UTC instant is an allowed local schedule run."""

    allowed, _, _, _ = _decision(
        now_utc,
        timezone_name=timezone_name,
        anchor_date=anchor_date,
        local_hour=local_hour,
        interval_days=interval_days,
    )
    return allowed


def _parse_utc(value):
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid --now-utc timestamp: {value!r}") from exc
    return _validated_utc(parsed)


def _format_utc(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Gate the PS5/TV automation by Central hour and two-day parity."
    )
    parser.add_argument(
        "--now-utc",
        help="Aware UTC ISO-8601 timestamp; defaults to the current UTC time.",
    )
    args = parser.parse_args(argv)

    try:
        now_utc = (
            _parse_utc(args.now_utc)
            if args.now_utc is not None
            else datetime.now(timezone.utc)
        )
        allowed, normalized_utc, local_now, reason = _decision(now_utc)
    except ValueError as exc:
        print(
            "SCHEDULE_GATE=INVALID UTC=unavailable LOCAL=unavailable "
            f"REASON={exc}"
        )
        return 2

    marker = "RUN" if allowed else "SKIP"
    print(
        f"SCHEDULE_GATE={marker} "
        f"UTC={_format_utc(normalized_utc)} "
        f"LOCAL={local_now.isoformat(timespec='seconds')} "
        f"REASON={reason}"
    )
    return 0 if allowed else 3


if __name__ == "__main__":
    raise SystemExit(main())
