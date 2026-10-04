"""Shared decimal utilities for financial calculations."""

import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext

ZERO = Decimal('0')


def to_decimal(value) -> Decimal:
    """Convert a numeric value, rejecting non-finite values before arithmetic."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid finite decimal.') from exc
    if not result.is_finite():
        raise ValueError('Invalid finite decimal.')
    return result


def parse_financial_decimal(value) -> Decimal:
    """Parse exact decimal text. Commas are grouped thousands, never decimals.

    Accept surrounding whitespace, signs, decimal points and scientific notation.
    Reject malformed grouping, internal whitespace and non-finite input. Floats
    are not accepted at action boundaries: their original digits are unknowable.
    """
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError('Invalid finite decimal.')
    text = str(value).strip()
    if not re.fullmatch(
        r'[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)'
        r'(?:[eE][+-]?[0-9]+)?', text,
    ):
        raise ValueError('Invalid finite decimal.')
    return to_decimal(text.replace(',', ''))


def decimal_text(value) -> str:
    """Exact fixed-point action/JSON text, independent of display formatting."""
    return format(to_decimal(value), 'f')


def withdrawal_max_text(cash) -> str:
    """Executable two-decimal funding amount; never round positive cash up."""
    cash = max(to_decimal(cash), ZERO)
    with localcontext() as context:
        context.prec = max(context.prec, cash.adjusted() + 3)
        return decimal_text(cash.quantize(Decimal('0.01'), rounding=ROUND_DOWN))


def decimal_json(value):
    """Serialize only Decimal leaves as exact text; preserve other JSON types."""
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, dict):
        return {key: decimal_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimal_json(item) for item in value]
    return value


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = ZERO) -> Decimal:
    """Divide numerator by denominator, returning default if denominator is zero."""
    return numerator / denominator if denominator else default
