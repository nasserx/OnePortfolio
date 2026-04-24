"""Custom validators for form validation."""

from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple
from portfolio_app.utils.messages import MESSAGES


def parse_decimal_field(
    value: str,
    *,
    allow_blank: bool = False
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Parse a decimal field from form input.

    Returns:
        Tuple of (decimal_value, error_message)
        If successful: (Decimal, None)
        If error: (None, error_message)
    """
    v = (value or '').strip()
    if v == '':
        return (None, None) if allow_blank else (None, MESSAGES['FIELD_REQUIRED'])
    try:
        return Decimal(v), None
    except (InvalidOperation, ValueError, TypeError):
        return None, MESSAGES['INVALID_NUMBER']


def validate_positive_decimal(
    value: str,
    *,
    allow_zero: bool = False,
    allow_blank: bool = False
) -> Tuple[Optional[Decimal], Optional[str]]:
    """Validate that a decimal field is positive.

    Returns:
        Tuple of (decimal_value, error_message)
    """
    dec, err = parse_decimal_field(value, allow_blank=allow_blank)
    if err:
        return None, err
    if dec is None:
        return None, None
    if allow_zero:
        if dec < 0:
            return None, MESSAGES['VALUE_NON_NEGATIVE']
        return dec, None
    if dec <= 0:
        return None, MESSAGES['VALUE_POSITIVE']
    return dec, None
