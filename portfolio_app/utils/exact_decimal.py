"""Exact financial persistence, independent of presentation or calculation scale."""

import re
from decimal import Decimal

from sqlalchemy.types import TypeDecorator, Text

from portfolio_app.utils.decimal_utils import (
    parse_storage_decimal, MAX_STORED_DECIMAL_CHARS, FinancialNumberLimitError,
)


def read_stored_decimal(value):
    """Read bounded canonical fixed-point TEXT without expanding or rounding.

    In this grammar every exponent position is already present on disk. Checking
    length before parsing bounds both the coefficient and the arithmetic span;
    compressed exponents, non-finite values and noncanonical zeros are rejected.
    """
    if not isinstance(value, str):
        raise ValueError('Exact Decimal storage must be TEXT; migrate the database first.')
    if len(value) > MAX_STORED_DECIMAL_CHARS:
        raise FinancialNumberLimitError('Financial number exceeds the safe storage limit.')
    if value == '-0' or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?', value):
        raise ValueError('Noncanonical persisted Decimal text.')
    return Decimal(value)


def canonical_decimal_text(value):
    """Context-independent canonical fixed point, without normalize()/rounding."""
    value = parse_storage_decimal(value)
    if value.is_zero():
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


class ExactDecimalText(TypeDecorator):
    """TEXT on disk; finite Decimal in Python. Never bind or read binary floats.

    Entry policy belongs to forms/services. A larger resource ceiling also
    bounds storage expansion without rounding safely bounded legacy values.
    Numeric SQL arithmetic/order is intentionally not supported as financial math.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else canonical_decimal_text(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return read_stored_decimal(value)
