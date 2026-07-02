"""Shared decimal utilities for financial calculations."""

from decimal import Decimal

ZERO = Decimal('0')


def to_decimal(value) -> Decimal:
    """Convert any numeric value to Decimal safely."""
    return Decimal(str(value))


def safe_divide(numerator: Decimal, denominator: Decimal, default: Decimal = ZERO) -> Decimal:
    """Divide numerator by denominator, returning default if denominator is zero."""
    return numerator / denominator if denominator else default
