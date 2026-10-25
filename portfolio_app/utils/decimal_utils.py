"""Shared decimal utilities for financial calculations."""

import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext

ZERO = Decimal('0')

# Entry limits cover cash, price, quantity and fees alike, without quantization.
MAX_FINANCIAL_INPUT_CHARS = 256
MAX_FINANCIAL_INTEGER_DIGITS = 64
MAX_FINANCIAL_DECIMAL_PLACES = 64
# Bound the actual fixed-point representation, not the entry policy or an
# arbitrary exponent cutoff. Historical fixed-point text needs no expansion.
MAX_STORED_DECIMAL_CHARS = 32768


class FinancialNumberLimitError(ValueError):
    """A numeric representation exceeds its explicitly bounded work budget."""


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
    validate_financial_input_length(value)
    return _parse_bounded_decimal(
        value, MAX_FINANCIAL_INPUT_CHARS,
        MAX_FINANCIAL_INTEGER_DIGITS, MAX_FINANCIAL_DECIMAL_PLACES,
        'Financial number exceeds 256 characters, 64 integer digits or 64 decimal places.',
    )


def validate_financial_input_length(value):
    """Check original action text before whitespace/blank normalization."""
    if isinstance(value, str) and len(value) > MAX_FINANCIAL_INPUT_CHARS:
        raise FinancialNumberLimitError(
            f'Financial number exceeds {MAX_FINANCIAL_INPUT_CHARS} characters.'
        )


def parse_storage_decimal(value) -> Decimal:
    """Bound fixed-point output size before allocating it; never quantize."""
    result = _parse_bounded_decimal(
        value, MAX_STORED_DECIMAL_CHARS,
        MAX_STORED_DECIMAL_CHARS, MAX_STORED_DECIMAL_CHARS,
        'Financial number exceeds the safe storage limit.',
    )
    if not result.is_zero():
        parts = result.as_tuple()
        width = parts.sign + max(1, result.adjusted() + 1)
        if parts.exponent < 0:
            width += 1 - parts.exponent  # decimal point and fractional places
        if width > MAX_STORED_DECIMAL_CHARS:
            raise FinancialNumberLimitError('Financial number exceeds the safe storage limit.')
    return result


def _parse_bounded_decimal(value, max_chars, integer_digits, decimal_places, message):
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError('Invalid finite decimal.')
    if isinstance(value, Decimal):
        result = value  # Inspect the exponent; never expand it to fixed point.
    else:
        text = str(value)
        # Bound work before regex matching or Decimal construction, including
        # redundant leading zeros and enormous textual exponent coefficients.
        if len(text) > max_chars:
            raise FinancialNumberLimitError(message)
        text = text.strip()
        if not re.fullmatch(
            r'[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)'
            r'(?:[eE][+-]?[0-9]+)?', text,
        ):
            raise ValueError('Invalid finite decimal.')
        result = to_decimal(text.replace(',', ''))
    if not result.is_finite():
        raise ValueError('Invalid finite decimal.')
    exponent = result.as_tuple().exponent
    if result.adjusted() + 1 > integer_digits or exponent < -decimal_places:
        raise FinancialNumberLimitError(message)
    return result


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
