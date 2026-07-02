"""Pure deterministic financial calculations.

This module is intentionally independent of Flask, SQLAlchemy, models,
repositories, and services. Callers provide already-ordered records or scalar
values; database-facing ordering and scoping stay in PortfolioCalculator.
"""

from decimal import Decimal

from portfolio_app.utils.decimal_utils import ZERO, safe_divide, to_decimal


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
    """Summarize a pre-sorted transaction list using the Average Cost Method."""
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

    for transaction in transactions:
        price = to_decimal(transaction.price)
        quantity = to_decimal(transaction.quantity)
        fees = to_decimal(transaction.fees)

        if transaction.transaction_type == 'Buy':
            cost = (price * quantity) + fees
            total_buy_cost += cost
            total_buy_fees += fees
            total_buy_quantity += quantity
            running_cost += cost
            running_quantity += quantity

        elif transaction.transaction_type == 'Sell':
            proceeds = (price * quantity) - fees
            total_sell_cost += proceeds
            total_sell_fees += fees
            total_sell_quantity += quantity
            realized_proceeds += proceeds

            avg_cost = safe_divide(running_cost, running_quantity)
            realized_pnl += (price - avg_cost) * quantity - fees
            realized_cost_basis += avg_cost * quantity

            running_quantity -= quantity
            running_cost -= avg_cost * quantity

    return {
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
