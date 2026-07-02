"""Token utilities for password reset.

Uses itsdangerous.URLSafeTimedSerializer to generate and verify
time-limited signed tokens. The payload is a dict carrying the user's
email and a single-use token id (jti) that the DB cross-checks so each
link can only be redeemed once.

Note: Email verification now uses a 6-digit OTP code stored in the database,
not a URL token. Only password reset still uses URL tokens.
"""

from typing import Optional, Tuple
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app

_RESET_SALT = 'password-reset'


def _get_serializer() -> URLSafeTimedSerializer:
    """Return a serializer bound to the app's SECRET_KEY."""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------

def generate_reset_token(email: str, jti: str = '') -> str:
    """Generate a signed token encoding ``(email, jti)`` for password reset.

    The jti is a one-shot identifier the DB also stores on the user; on
    redemption we compare and clear it so the same link can't be reused.
    Pass ``jti=''`` for the timing-parity dummy generated for unknown
    emails (it will never be verified against a real user).
    """
    return _get_serializer().dumps({'email': email, 'jti': jti}, salt=_RESET_SALT)


def verify_reset_token(token: str) -> Optional[Tuple[str, str]]:
    """Verify a password reset token and return its ``(email, jti)`` payload.

    Returns ``None`` if the token is malformed, tampered, or expired.
    The caller is responsible for matching the jti against the value
    persisted on the user (so the link is single-use).
    """
    expiry = current_app.config.get('PASSWORD_RESET_EXPIRY', 3600)
    try:
        payload = _get_serializer().loads(token, salt=_RESET_SALT, max_age=expiry)
    except (SignatureExpired, BadSignature):
        return None

    # Backwards-compat: pre-MED-A6 tokens were a bare email string.
    # Treat them as having no jti so they fail the per-user check below
    # (they'd be > 1h old anyway in any normal deploy).
    if isinstance(payload, str):
        return payload, ''
    if isinstance(payload, dict):
        email = payload.get('email')
        jti = payload.get('jti', '')
        if isinstance(email, str):
            return email, jti or ''
    return None
