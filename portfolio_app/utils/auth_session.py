"""Signed-session timestamps for idle, absolute, and recent-auth policy."""

from datetime import datetime, timedelta, timezone
from typing import Mapping, MutableMapping, Optional


AUTH_ISSUED_AT_KEY = 'auth_issued_at'
AUTH_LAST_SEEN_AT_KEY = 'auth_last_seen_at'
RECENT_AUTH_AT_KEY = 'recent_auth_at'

IDLE_LIFETIME = timedelta(days=7)
ABSOLUTE_LIFETIME = timedelta(days=30)
RECENT_AUTH_WINDOW = timedelta(minutes=15)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def establish_auth_session(state: MutableMapping, now: Optional[datetime] = None) -> None:
    moment = now or utc_now()
    timestamp = moment.timestamp()
    state[AUTH_ISSUED_AT_KEY] = timestamp
    state[AUTH_LAST_SEEN_AT_KEY] = timestamp
    state[RECENT_AUTH_AT_KEY] = timestamp


def auth_session_is_valid(state: Mapping, now: Optional[datetime] = None) -> bool:
    moment = now or utc_now()
    issued = _read_timestamp(state.get(AUTH_ISSUED_AT_KEY))
    last_seen = _read_timestamp(state.get(AUTH_LAST_SEEN_AT_KEY))
    if issued is None or last_seen is None:
        return False
    return (
        moment - issued <= ABSOLUTE_LIFETIME
        and moment - last_seen <= IDLE_LIFETIME
        and moment >= issued
        and moment >= last_seen
    )


def recent_auth_is_valid(state: Mapping, now: Optional[datetime] = None) -> bool:
    moment = now or utc_now()
    authenticated_at = _read_timestamp(state.get(RECENT_AUTH_AT_KEY))
    return bool(
        authenticated_at is not None
        and moment >= authenticated_at
        and moment - authenticated_at <= RECENT_AUTH_WINDOW
    )


def touch_auth_session(state: MutableMapping, now: Optional[datetime] = None) -> None:
    state[AUTH_LAST_SEEN_AT_KEY] = (now or utc_now()).timestamp()


def mark_recent_auth(state: MutableMapping, now: Optional[datetime] = None) -> None:
    state[RECENT_AUTH_AT_KEY] = (now or utc_now()).timestamp()


def _read_timestamp(value) -> Optional[datetime]:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
