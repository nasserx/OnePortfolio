"""Timezone-aware date validation helpers."""

from datetime import datetime, timezone

from portfolio_app.forms.base_form import (
    parse_user_timestamp_for_future_check,
    _truncate_to_minute,
)


def test_riyadh_midnight_date_only_normalizes_to_previous_utc_day():
    stored, utc_dt = parse_user_timestamp_for_future_check(
        '2026-05-10',
        user_timezone='Asia/Riyadh',
    )

    assert stored == datetime(2026, 5, 10)
    assert utc_dt == datetime(2026, 5, 9, 21, 0, tzinfo=timezone.utc)


def test_western_timezone_date_only_normalizes_with_correct_offset():
    stored, utc_dt = parse_user_timestamp_for_future_check(
        '2026-05-10',
        user_timezone='America/Los_Angeles',
    )

    assert stored == datetime(2026, 5, 10)
    assert utc_dt == datetime(2026, 5, 10, 7, 0, tzinfo=timezone.utc)


def test_iso8601_offset_timestamp_normalizes_to_utc():
    stored, utc_dt = parse_user_timestamp_for_future_check(
        '2026-05-10T00:00:00+03:00',
        user_timezone='Asia/Riyadh',
    )

    assert stored == datetime(2026, 5, 10)
    assert utc_dt == datetime(2026, 5, 9, 21, 0, tzinfo=timezone.utc)


def test_minute_precision_ignores_seconds_and_microseconds():
    first = datetime(2026, 5, 9, 21, 0, 59, 999999, tzinfo=timezone.utc)
    second = datetime(2026, 5, 9, 21, 0, 0, tzinfo=timezone.utc)

    assert _truncate_to_minute(first) == _truncate_to_minute(second)
