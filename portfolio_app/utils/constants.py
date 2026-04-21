"""Application-wide constants — single source of truth for magic strings."""

import re

# The username reserved for the public demo account.
# Actions that mutate account credentials are disabled for this user.
DEMO_USERNAME = 'demo'


class EventType:
    """Portfolio event types."""
    INITIAL = 'Initial'
    DEPOSIT = 'Deposit'
    WITHDRAWAL = 'Withdrawal'


# Regex for sanitizing strings into safe HTML element IDs.
_HTML_ID_RE = re.compile(r'[^A-Za-z0-9_\-]+')


def safe_html_id(*parts) -> str:
    """Build a safe HTML element ID from arbitrary parts.

    >>> safe_html_id(3, 'Commodities')
    '3-Commodities'
    >>> safe_html_id(1, 'My Fund!')
    '1-My_Fund_'
    """
    return _HTML_ID_RE.sub('_', '-'.join(str(p) for p in parts))
