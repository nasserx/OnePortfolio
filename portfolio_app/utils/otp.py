"""Keyed storage verification for short-lived numeric OTP credentials."""

import hashlib
import hmac
from collections.abc import Sequence

from flask import current_app


_KEY_DERIVATION_DOMAIN = b'oneportfolio:otp-storage:key:v1'
_CREDENTIAL_DOMAIN = b'oneportfolio:otp-storage:credential:v1'


def otp_digest(raw_code: str, *, purpose: str, context: Sequence[str]) -> str:
    """Return a domain- and context-bound HMAC-SHA-256 OTP digest."""
    secret = current_app.config['SECRET_KEY']
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    elif not isinstance(secret, bytes):
        raise RuntimeError('SECRET_KEY must be text or bytes.')

    storage_key = hmac.new(
        secret,
        _KEY_DERIVATION_DOMAIN,
        hashlib.sha256,
    ).digest()
    message = b''.join(
        _frame(part)
        for part in (_CREDENTIAL_DOMAIN, purpose, *context, raw_code)
    )
    return hmac.new(storage_key, message, hashlib.sha256).hexdigest()


def verify_otp(
    stored_digest: str,
    raw_code: str,
    *,
    purpose: str,
    context: Sequence[str],
) -> bool:
    """Verify a submitted raw OTP against its stored keyed digest."""
    if not stored_digest:
        return False
    expected = otp_digest(raw_code, purpose=purpose, context=context)
    return hmac.compare_digest(stored_digest, expected)


def _frame(value) -> bytes:
    encoded = value if isinstance(value, bytes) else str(value).encode('utf-8')
    return len(encoded).to_bytes(4, 'big') + encoded
