"""Custom validators for form validation."""

from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple
from portfolio_app.utils.messages import ValidationMessages


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
        return (None, None) if allow_blank else (None, ValidationMessages.REQUIRED)
    try:
        return Decimal(v), None
    except (InvalidOperation, ValueError, TypeError):
        return None, ValidationMessages.INVALID_NUMBER


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
            return None, ValidationMessages.VALUE_NON_NEGATIVE
        return dec, None
    if dec <= 0:
        return None, ValidationMessages.VALUE_POSITIVE
    return dec, None


def get_field_error_message(field_name: str) -> str:
    """Get field-specific positive-value error message.

    Args:
        field_name: Name of the field

    Returns:
        Field-specific error message
    """
    if field_name in ('price', 'edit_price'):
        return ValidationMessages.PRICE_POSITIVE
    if field_name in ('quantity', 'edit_quantity'):
        return ValidationMessages.QUANTITY_POSITIVE
    if field_name in ('amount', 'amount_delta', 'edit_amount', 'edit_event_amount'):
        return ValidationMessages.AMOUNT_POSITIVE
    return ValidationMessages.VALUE_POSITIVE
