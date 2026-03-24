"""Token utilities for password reset.

Uses itsdangerous.URLSafeTimedSerializer to generate and verify
time-limited signed tokens. The payload is the user's email address.

Note: Email verification now uses a 6-digit OTP code stored in the database,
not a URL token. Only password reset still uses URL tokens.
"""

from typing import Optional
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app

_RESET_SALT = 'password-reset'


def _get_serializer() -> URLSafeTimedSerializer:
    """Return a serializer bound to the app's SECRET_KEY."""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------

def generate_reset_token(email: str) -> str:
    """Generate a signed token encoding the given email address for password reset.

    Args:
        email: The user's email address to encode.

    Returns:
        A URL-safe signed token string.
    """
    return _get_serializer().dumps(email, salt=_RESET_SALT)


def verify_reset_token(token: str) -> Optional[str]:
    """Verify a password reset token and return the email it encodes.

    Args:
        token: The signed token to verify.

    Returns:
        The email address if the token is valid and not expired,
        or None if the token is invalid or expired.
    """
    expiry = current_app.config.get('PASSWORD_RESET_EXPIRY', 3600)
    try:
        email = _get_serializer().loads(token, salt=_RESET_SALT, max_age=expiry)
        return email
    except (SignatureExpired, BadSignature):
        return None
