"""Context-independent financial arithmetic, separate from storage and display.

Finite sums/products are exact (Inexact is trapped). Only division is rounded.
A replay fixes one division budget from all its raw operands, not from ambient
context or growing intermediate averages. See FINANCIAL_READ_MODEL.md.
"""

from dataclasses import dataclass
from decimal import (
    Context, Decimal, DivisionByZero, Inexact, InvalidOperation, MAX_EMAX,
    MIN_EMIN, Overflow, Underflow, ROUND_HALF_EVEN, localcontext,
)

from portfolio_app.utils.decimal_utils import ZERO, to_decimal

MIN_DIVISION_DIGITS = 28
GUARD_DIGITS = 28


def _context(precision, *, exact=False):
    return Context(
        prec=precision, rounding=ROUND_HALF_EVEN, Emin=MIN_EMIN, Emax=MAX_EMAX,
        capitals=1, clamp=0, flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow, Underflow] + ([Inexact] if exact else []),
    )


def exact_sum(values):
    """Exact signed sum including cancellation and widely separated exponents."""
    values = tuple(to_decimal(value) for value in values)
    nonzero = [value for value in values if value]
    if not nonzero:
        return ZERO
    low = min(value.as_tuple().exponent for value in nonzero)
    high = max(value.adjusted() for value in nonzero)
    # Aligned coefficient width plus enough carry digits for every summand.
    context = _context(max(1, high - low + 1 + len(str(len(nonzero)))), exact=True)
    total = ZERO
    for value in nonzero:
        total = context.add(total, value)
    return total


def exact_add(left, right):
    return exact_sum((left, right))


def exact_subtract(left, right):
    return exact_sum((left, to_decimal(right).copy_negate()))


def exact_multiply(left, right):
    left, right = to_decimal(left), to_decimal(right)
    precision = len(left.as_tuple().digits) + len(right.as_tuple().digits)
    return _context(precision, exact=True).multiply(left, right)


def division_precision(values):
    """max(28, 2 * decimal span + count carry digits) + 28 guard digits.

    Span covers the units position and all significant input positions; trailing
    coefficient zeros do not affect it. Doubling covers raw price*quantity
    widths. Carry accounts for accumulation. Guards protect recurring ratios;
    they are not a promise of an exact infinite expansion or relative accuracy
    after arbitrary cancellation. Finite operations never consume this budget.
    """
    values = tuple(to_decimal(value) for value in values)
    high, low = 0, 0
    for value in values:
        if not value:
            continue
        _, digits, exponent = value.as_tuple()
        trailing = len(digits) - len(''.join(map(str, digits)).rstrip('0'))
        high = max(high, value.adjusted() + 1)
        low = min(low, exponent + trailing)
    return max(MIN_DIVISION_DIGITS, 2 * (high - low) + len(str(max(1, len(values))))) + GUARD_DIGITS


@dataclass(frozen=True)
class FinancialArithmetic:
    """One deterministic division precision for a complete replay operation.

    Exact finite operations need no rounding budget. Their operand-sized local
    Contexts are implementation capacity, not changing approximation policies.
    Context methods never read or mutate the thread's global Decimal context.
    """

    precision: int

    @classmethod
    def for_values(cls, values):
        return cls(division_precision(values))

    def divide(self, numerator, denominator, default=ZERO):
        numerator, denominator = to_decimal(numerator), to_decimal(denominator)
        if not denominator:
            return default
        return _context(self.precision).divide(numerator, denominator)

    def local_context(self):
        """Explicit scope for adapters needing Decimal operators (e.g. format)."""
        return localcontext(_context(self.precision))

    def percent(self, numerator, denominator):
        return exact_multiply(self.divide(numerator, denominator), Decimal('100'))


def financial_divide(numerator, denominator, default=ZERO):
    return FinancialArithmetic.for_values((numerator, denominator)).divide(numerator, denominator, default)


def financial_percent(numerator, denominator):
    return FinancialArithmetic.for_values((numerator, denominator)).percent(numerator, denominator)
