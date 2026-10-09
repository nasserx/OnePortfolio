"""Exact financial persistence, independent of presentation or calculation scale."""

from decimal import Decimal
from sqlalchemy.types import TypeDecorator, Text

from portfolio_app.utils.decimal_utils import parse_financial_decimal


def canonical_decimal_text(value):
    """Context-independent canonical fixed point, without normalize()/rounding."""
    value = parse_financial_decimal(value)
    if value.is_zero():
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


class ExactDecimalText(TypeDecorator):
    """TEXT on disk; finite Decimal in Python. Never bind or read binary floats.

    No scale/range or positivity policy is imposed by this storage type.
    Numeric SQL arithmetic/order is intentionally not supported as financial math.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else canonical_decimal_text(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Exact Decimal storage must be TEXT; migrate the database first.')
        result = Decimal(value)
        if not result.is_finite():
            raise ValueError('Non-finite persisted Decimal.')
        if canonical_decimal_text(result) != value:
            raise ValueError('Noncanonical persisted Decimal text.')
        return result
