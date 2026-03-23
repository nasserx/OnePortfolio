"""Token utilities for email verification and password reset.

Uses itsdangerous.URLSafeTimedSerializer to generate and verify
time-limited signed tokens. The payload is the user's email address.
"""

from typing import Optional
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from flask import current_app

# Salt values separate verification tokens from reset tokens,
# so a verification token cannot be reused as a reset token.
_VERIFICATION_SALT = 'email-verification'
_RESET_SALT = 'password-reset'


def _get_serializer() -> URLSafeTimedSerializer:
    """Return a serializer bound to the app's SECRET_KEY."""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# ---------------------------------------------------------------------------
# Email verification tokens
# ---------------------------------------------------------------------------

def generate_verification_token(email: str) -> str:
    """Generate a signed token encoding the given email address.

    Args:
        email: The user's email address to encode.

    Returns:
        A URL-safe signed token string.
    """
    return _get_serializer().dumps(email, salt=_VERIFICATION_SALT)


def verify_verification_token(token: str) -> Optional[str]:
    """Verify an email verification token and return the email it encodes.

    Args:
        token: The signed token to verify.

    Returns:
        The email address if the token is valid and not expired,
        or None if the token is invalid or expired.
    """
    expiry = current_app.config.get('EMAIL_VERIFICATION_EXPIRY', 86400)
    try:
        email = _get_serializer().loads(token, salt=_VERIFICATION_SALT, max_age=expiry)
        return email
    except (SignatureExpired, BadSignature):
        return None


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
