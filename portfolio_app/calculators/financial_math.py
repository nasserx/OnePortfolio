"""Pure deterministic financial calculations.

This module is intentionally independent of Flask, SQLAlchemy, models,
repositories, and services. Callers provide already-ordered records or scalar
values; database-facing ordering and scoping stay in PortfolioCalculator.
"""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Union

from portfolio_app.utils.decimal_utils import ZERO, safe_divide, to_decimal


@dataclass(frozen=True)
class TransactionFinancialProjection:
    """One replay step, calculated only from raw facts and the running pool.

    applicable_average_unit_cost is the post-buy average for a Buy and the
    pre-sale average for a Sell. Buy trading P&L/return are undefined, not zero.
    No ORM references, stored derivatives or implicit history queries belong here.
    """

    transaction_id: Optional[int]
    portfolio_id: Optional[int]
    transaction_type: str
    gross_amount: Decimal
    fee: Decimal
    purchase_cost: Decimal
    net_sale_proceeds: Decimal
    cash_effect: Decimal
    applicable_average_unit_cost: Decimal
    released_cost_basis: Decimal
    realized_trading_pnl: Optional[Decimal]
    trade_return_percent: Optional[Decimal]
    post_quantity: Decimal
    post_cost_basis: Decimal
    post_average_unit_cost: Decimal

    @property
    def cash_amount(self):
        """Unsigned-direction legacy transaction Total: buy cost or sale proceeds."""
        return self.purchase_cost if self.transaction_type == 'Buy' else self.net_sale_proceeds


@dataclass(frozen=True)
class AssetReplayResult:
    summary: Mapping[str, Union[Decimal, int]]
    projections: Tuple[TransactionFinancialProjection, ...]


def calculate_quantity_held(transactions):
    """Calculate held quantity from pre-filtered transaction records."""
    quantity_held = ZERO

    for transaction in transactions:
        quantity = to_decimal(transaction.quantity)
        if transaction.transaction_type == 'Buy':
            quantity_held += quantity
        elif transaction.transaction_type == 'Sell':
            quantity_held -= quantity

    return quantity_held


def calculate_symbol_transaction_summary(transactions):
    """Legacy summary adapter over the single replay implementation."""
    return dict(replay_symbol_transactions(transactions).summary)


def replay_symbol_transactions(transactions):
    """Replay one already-canonically-ordered symbol history once.

    Produce aggregates and the exact individual contributions used to accumulate
    them. Keep the existing Decimal operation order, including partial-sale P&L.
    Canonical sorting remains at the shared snapshot boundary.
    """
    total_buy_cost = ZERO
    total_buy_fees = ZERO
    total_buy_quantity = ZERO
    total_sell_cost = ZERO
    total_sell_fees = ZERO
    total_sell_quantity = ZERO

    realized_pnl = ZERO
    realized_cost_basis = ZERO
    realized_proceeds = ZERO
    running_quantity = ZERO
    running_cost = ZERO
    projections = []

    for transaction in transactions:
        price = to_decimal(transaction.price)
        quantity = to_decimal(transaction.quantity)
        fees = to_decimal(transaction.fees)
        gross = price * quantity
        cost = proceeds = released_cost = ZERO
        sale_pnl = trade_return = None

        if transaction.transaction_type == 'Buy':
            cost = gross + fees
            total_buy_cost += cost
            total_buy_fees += fees
            total_buy_quantity += quantity
            running_cost += cost
            running_quantity += quantity
            avg_cost = safe_divide(running_cost, running_quantity)
            cash_effect = -cost

        elif transaction.transaction_type == 'Sell':
            proceeds = gross - fees
            total_sell_cost += proceeds
            total_sell_fees += fees
            total_sell_quantity += quantity
            realized_proceeds += proceeds

            avg_cost = safe_divide(running_cost, running_quantity)
            # A valid closing sale releases the entire pool, not a rounded
            # average multiplied back up. Never clamp a still-open position.
            closes_position = running_quantity > ZERO and quantity == running_quantity
            released_cost = running_cost if closes_position else avg_cost * quantity
            sale_pnl = (
                proceeds - released_cost if closes_position
                else (price - avg_cost) * quantity - fees
            )
            realized_pnl += sale_pnl
            realized_cost_basis += released_cost
            trade_return = (
                sale_pnl / released_cost * Decimal('100')
                if released_cost != ZERO else None
            )

            running_quantity -= quantity
            running_cost -= released_cost
            cash_effect = proceeds
        else:
            # Preserve summary handling of unsupported historical types. Such
            # records have no valid trade projection and cannot be reported as one.
            continue

        projections.append(TransactionFinancialProjection(
            transaction_id=getattr(transaction, 'id', None),
            portfolio_id=getattr(transaction, 'portfolio_id', None),
            transaction_type=transaction.transaction_type,
            gross_amount=gross, fee=fees, purchase_cost=cost,
            net_sale_proceeds=proceeds, cash_effect=cash_effect,
            applicable_average_unit_cost=avg_cost, released_cost_basis=released_cost,
            realized_trading_pnl=sale_pnl, trade_return_percent=trade_return,
            post_quantity=running_quantity, post_cost_basis=running_cost,
            post_average_unit_cost=safe_divide(running_cost, running_quantity),
        ))

    summary = {
        'total_buy_cost': total_buy_cost,
        'total_buy_fees': total_buy_fees,
        'total_buy_quantity': total_buy_quantity,
        'total_sell_cost': total_sell_cost,
        'total_sell_fees': total_sell_fees,
        'total_sell_quantity': total_sell_quantity,
        'total_quantity_held': running_quantity,
        'average_cost': safe_divide(running_cost, running_quantity),
        'transaction_count': len(transactions),
        'realized_pnl': realized_pnl,
        'realized_cost_basis': realized_cost_basis,
        'realized_proceeds': realized_proceeds,
        'cost_basis': running_cost,
    }
    return AssetReplayResult(MappingProxyType(summary), tuple(projections))


def calculate_return(realized_pnl, total_income, base):
    """Calculate return amount, percentage, and display text."""
    realized_pnl = to_decimal(realized_pnl)
    total_income = to_decimal(total_income)
    base = to_decimal(base)

    return_amount = realized_pnl + total_income
    if base == ZERO:
        return_percent = ZERO
        return_display = '—'
    else:
        return_percent = (return_amount / abs(base)) * Decimal('100')
        return_display = f"{return_percent:+,.2f}%"

    return {
        'return_amount': return_amount,
        'return_percent': return_percent,
        'return_display': return_display,
    }


def calculate_portfolio_metrics(total_cash, positions, realized_pnl, total_income, return_base):
    """Calculate portfolio-level book value and return metrics."""
    total_cash = to_decimal(total_cash)
    positions = to_decimal(positions)
    book_value = total_cash + positions
    return_result = calculate_return(realized_pnl, total_income, return_base)

    return {
        'book_value': book_value,
        'return_amount': return_result['return_amount'],
        'return_percent': return_result['return_percent'],
        'return_display': return_result['return_display'],
    }


def calculate_asset_return(realized_pnl, total_income, total_buy_cost):
    """Calculate asset-level return metrics."""
    return calculate_return(realized_pnl, total_income, total_buy_cost)


def calculate_cash_balance(total_capital, transactions, total_income):
    """Calculate total cash from capital, buy/sell cash flows, and income."""
    cash = to_decimal(total_capital)

    for transaction in transactions:
        price = to_decimal(transaction.price)
        quantity = to_decimal(transaction.quantity)
        fees = to_decimal(transaction.fees)
        gross = price * quantity

        if transaction.transaction_type == 'Buy':
            cash -= gross + fees
        elif transaction.transaction_type == 'Sell':
            cash += gross - fees

    cash += to_decimal(total_income)
    return cash
