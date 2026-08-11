"""Shared redirect-target validation."""

from urllib.parse import urlparse


def safe_local_redirect(target):
    """Return a safe local redirect path, or None for unsafe values."""
    if not target:
        return None
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or not target.startswith('/')
        or target.startswith('//')
        or target.startswith('/\\')
    ):
        return None
    return target
