"""Pure deterministic financial calculations.

This module is intentionally independent of Flask, SQLAlchemy, models,
repositories, and services. Callers provide already-ordered records or scalar
values; database-facing ordering and scoping stay in PortfolioCalculator.
"""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Union

from portfolio_app.utils.decimal_utils import ZERO, to_decimal
from portfolio_app.utils.financial_arithmetic import (
    FinancialArithmetic, exact_add, exact_subtract, exact_multiply, financial_percent,
)


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
    realized_trading_return: Optional[Decimal]
    post_quantity: Decimal
    post_position_cost_basis: Decimal
    post_average_unit_cost: Decimal

    @property
    def transaction_amount(self):
        """Transaction Total Amount: purchase cost for a Buy, net proceeds for a Sell."""
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
            quantity_held = exact_add(quantity_held, quantity)
        elif transaction.transaction_type == 'Sell':
            quantity_held = exact_subtract(quantity_held, quantity)

    return quantity_held


def calculate_symbol_transaction_summary(transactions):
    """Legacy summary adapter over the single replay implementation."""
    return dict(replay_symbol_transactions(transactions).summary)


def replay_symbol_transactions(transactions):
    """Replay one already-canonically-ordered symbol history once.

    Produce aggregates and the exact individual contributions used to accumulate
    them. Finite operations are exact; divisions share one raw-input budget.
    Canonical sorting remains at the shared snapshot boundary.
    """
    transactions = tuple(transactions)
    arithmetic = FinancialArithmetic.for_values(
        value for transaction in transactions
        for value in (transaction.price, transaction.quantity, transaction.fees)
    )
    total_purchase_cost = ZERO
    total_buy_fees = ZERO
    total_buy_quantity = ZERO
    net_sale_proceeds = ZERO
    total_sell_fees = ZERO
    total_sell_quantity = ZERO

    realized_trading_pnl = ZERO
    released_cost_basis = ZERO
    running_quantity = ZERO
    running_cost = ZERO
    projections = []

    for transaction in transactions:
        price = to_decimal(transaction.price)
        quantity = to_decimal(transaction.quantity)
        fees = to_decimal(transaction.fees)
        gross = exact_multiply(price, quantity)
        cost = proceeds = released_cost = ZERO
        sale_pnl = trade_return = None

        if transaction.transaction_type == 'Buy':
            cost = exact_add(gross, fees)
            total_purchase_cost = exact_add(total_purchase_cost, cost)
            total_buy_fees = exact_add(total_buy_fees, fees)
            total_buy_quantity = exact_add(total_buy_quantity, quantity)
            running_cost = exact_add(running_cost, cost)
            running_quantity = exact_add(running_quantity, quantity)
            avg_cost = arithmetic.divide(running_cost, running_quantity)
            cash_effect = cost.copy_negate()

        elif transaction.transaction_type == 'Sell':
            proceeds = exact_subtract(gross, fees)
            net_sale_proceeds = exact_add(net_sale_proceeds, proceeds)
            total_sell_fees = exact_add(total_sell_fees, fees)
            total_sell_quantity = exact_add(total_sell_quantity, quantity)
            avg_cost = arithmetic.divide(running_cost, running_quantity)
            # A valid closing sale releases the entire pool, not a rounded
            # average multiplied back up. Never clamp a still-open position.
            closes_position = running_quantity > ZERO and quantity == running_quantity
            released_cost = running_cost if closes_position else exact_multiply(avg_cost, quantity)
            # Use the very same released component as the pool. This is the
            # algebraically identical P&L formula without independent rounding.
            sale_pnl = exact_subtract(proceeds, released_cost)
            realized_trading_pnl = exact_add(realized_trading_pnl, sale_pnl)
            released_cost_basis = exact_add(released_cost_basis, released_cost)
            trade_return = calculate_realized_trading_return(sale_pnl, released_cost)

            running_quantity = exact_subtract(running_quantity, quantity)
            running_cost = exact_subtract(running_cost, released_cost)
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
            realized_trading_pnl=sale_pnl, realized_trading_return=trade_return,
            post_quantity=running_quantity, post_position_cost_basis=running_cost,
            post_average_unit_cost=arithmetic.divide(running_cost, running_quantity),
        ))

    summary = {
        'total_purchase_cost': total_purchase_cost,
        'total_buy_fees': total_buy_fees,
        'total_buy_quantity': total_buy_quantity,
        'net_sale_proceeds': net_sale_proceeds,
        'total_sell_fees': total_sell_fees,
        'total_sell_quantity': total_sell_quantity,
        'total_quantity_held': running_quantity,
        'average_unit_cost': arithmetic.divide(running_cost, running_quantity),
        'transaction_count': len(transactions),
        'realized_trading_pnl': realized_trading_pnl,
        'released_cost_basis': released_cost_basis,
        'position_cost_basis': running_cost,
    }
    return AssetReplayResult(MappingProxyType(summary), tuple(projections))


def calculate_realized_trading_return(realized_trading_pnl, released_cost_basis):
    """One percentage at every scope; sum P&L and released basis before calling.

    Dividend Income, funding and open basis are deliberately not inputs.
    Use the Phase 7 direct-operand division policy identically at every scope.
    """
    pnl, basis = map(to_decimal, (realized_trading_pnl, released_cost_basis))
    return financial_percent(pnl, basis) if basis != ZERO else None


def calculate_realized_earnings_metrics(realized_trading_pnl, dividend_income, released_cost_basis):
    """Separate monetary realized earnings from the trading-only percentage."""
    pnl, dividend_income, basis = map(to_decimal, (realized_trading_pnl, dividend_income, released_cost_basis))
    trading_return = calculate_realized_trading_return(pnl, basis)
    if trading_return is None:
        trading_return_display = '—'
    else:
        arithmetic = FinancialArithmetic.for_values((pnl, basis))
        # Preserve the existing half-even two-decimal legacy display independently
        # of ambient rounding. UI ROUND_HALF_UP formatters remain separate.
        with arithmetic.local_context():
            trading_return_display = f"{trading_return:+,.2f}%"

    return {
        'realized_trading_pnl': pnl,
        'released_cost_basis': basis,
        'dividend_income': dividend_income,
        'total_realized_earnings': exact_add(pnl, dividend_income),
        'realized_trading_return': trading_return,
        'trading_return_display': trading_return_display,
    }


def calculate_portfolio_metrics(cash_balance, position_cost_basis, realized_trading_pnl, dividend_income, released_cost_basis):
    """Calculate portfolio-level book value and return metrics."""
    cash_balance = to_decimal(cash_balance)
    position_cost_basis = to_decimal(position_cost_basis)
    book_value = exact_add(cash_balance, position_cost_basis)
    return_result = calculate_realized_earnings_metrics(realized_trading_pnl, dividend_income, released_cost_basis)

    return {
        'book_value': book_value,
        **return_result,
    }


def calculate_cash_balance(net_contributions, transactions, dividend_income):
    """Calculate Cash Balance from Net Contributions, trades and Dividend Income."""
    cash_balance = to_decimal(net_contributions)

    for transaction in transactions:
        price = to_decimal(transaction.price)
        quantity = to_decimal(transaction.quantity)
        fees = to_decimal(transaction.fees)
        gross = exact_multiply(price, quantity)

        if transaction.transaction_type == 'Buy':
            cash_balance = exact_subtract(cash_balance, exact_add(gross, fees))
        elif transaction.transaction_type == 'Sell':
            cash_balance = exact_add(cash_balance, exact_subtract(gross, fees))

    cash_balance = exact_add(cash_balance, dividend_income)
    return cash_balance
