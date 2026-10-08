"""Date-only cash sufficiency, independent of moving-average trade ordering."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from portfolio_app.utils.decimal_utils import ZERO
from portfolio_app.utils.financial_arithmetic import exact_add, exact_subtract, exact_sum


def cash_day(value):
    """Legacy null dates precede dated history, as in canonical trade ordering."""
    if value is None:
        return date.min
    return value.date() if isinstance(value, datetime) else value


@dataclass(frozen=True)
class CashFact:
    date: date
    component: str
    amount: Decimal


@dataclass(frozen=True)
class DailyCash:
    date: date
    opening_cash: Decimal
    funding_inflows: Decimal
    withdrawals: Decimal
    buy_outflows: Decimal
    net_sale_proceeds: Decimal
    dividends: Decimal
    transfer_in: Decimal
    transfer_out: Decimal
    net_movement: Decimal
    closing_cash: Decimal


@dataclass(frozen=True)
class DailyCashLedger:
    days: tuple[DailyCash, ...]

    @property
    def closing_cash(self):
        return self.days[-1].closing_cash if self.days else ZERO

    @property
    def minimum_closing_cash(self):
        return min((day.closing_cash for day in self.days), default=ZERO)

    @property
    def first_deficit_date(self):
        return next((day.date for day in self.days if day.closing_cash < ZERO), None)

    def maximum_withdrawal(self, effective_date):
        """Additional withdrawal headroom at D and every later recorded day.

        Include D's carried balance even when no record currently exists on D.
        """
        day = cash_day(effective_date)
        at_date = ZERO
        later = []
        for row in self.days:
            if row.date <= day:
                at_date = row.closing_cash
            else:
                later.append(row.closing_cash)
        return max(ZERO, min([at_date, *later]))


def build_daily_cash_ledger(facts):
    """Net all same-calendar-day effects; finite arithmetic is exact."""
    grouped = {}
    for fact in facts:
        components = grouped.setdefault(cash_day(fact.date), {})
        components[fact.component] = exact_add(components.get(fact.component, ZERO), fact.amount)
    rows = []
    closing = ZERO
    for day, components in sorted(grouped.items()):
        values = [components.get(key, ZERO) for key in (
            'funding_inflows', 'withdrawals', 'buy_outflows', 'net_sale_proceeds', 'dividends',
            'transfer_in', 'transfer_out',
        )]
        funding, withdrawals, buys, sales, dividends, incoming, outgoing = values
        movement = exact_subtract(exact_sum((funding, sales, dividends, incoming)), exact_sum((withdrawals, buys, outgoing)))
        opening = closing
        closing = exact_add(opening, movement)
        rows.append(DailyCash(day, opening, *values, movement, closing))
    return DailyCashLedger(tuple(rows))


def permits_cash_mutation(before, after):
    """Strict for valid history; non-worsening minimum for legacy repairs."""
    return after.minimum_closing_cash >= min(ZERO, before.minimum_closing_cash)
