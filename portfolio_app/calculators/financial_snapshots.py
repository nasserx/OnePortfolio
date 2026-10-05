"""Pure, read-only aggregate financial views and canonical response adapters.

SQL loading belongs to PortfolioCalculator; arithmetic belongs to financial_math.
Snapshots are per-read values, never persisted or cached. Dictionary keys in the
adapters use the canonical financial vocabulary across HTTP and templates.
"""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Tuple, Union

from portfolio_app.calculators.financial_math import (
    calculate_realized_earnings_metrics,
    calculate_cash_balance,
    calculate_portfolio_metrics,
    replay_symbol_transactions,
    TransactionFinancialProjection,
)
from portfolio_app.calculators.transaction_order import order_transactions
from portfolio_app.utils.decimal_utils import ZERO, to_decimal
from portfolio_app.utils.financial_arithmetic import (
    exact_add, exact_subtract, exact_multiply, exact_sum, financial_divide,
    financial_percent,
)


def _readonly(values):
    return MappingProxyType(dict(values))


def sum_dividend_income_details(dividends):
    """Canonical Dividend Income grouping from persisted Decimal rows in ID order."""
    totals = {}
    for dividend in dividends:
        symbol = (dividend.symbol or '').strip().upper()
        if symbol:
            totals[symbol] = exact_add(totals.get(symbol, ZERO), dividend.amount)
    return totals


@dataclass(frozen=True)
class AssetFinancialSnapshot:
    symbol: str
    transactions: Mapping[str, Union[Decimal, int]]
    dividend_income: Decimal
    metrics: Mapping[str, Union[Decimal, str, None]]
    transaction_projections: Mapping[int, TransactionFinancialProjection]

    def as_assets_summary(self):
        """Fresh mutable template adapter; never mutate the underlying snapshot."""
        return {**self.transactions, **self.metrics}

    def as_financial_row(self, portfolio_id, portfolio_name):
        summary = self.transactions
        return {
            'portfolio_id': portfolio_id,
            'portfolio_name': portfolio_name,
            'symbol': self.symbol,
            'realized_trading_pnl': summary['realized_trading_pnl'],
            'dividend_income': self.dividend_income,
            'total_purchase_cost': summary['total_purchase_cost'],
            'released_cost_basis': summary['released_cost_basis'],
            'position_cost_basis': summary['position_cost_basis'],
            **self.metrics,
        }


def build_asset_snapshot(symbol, transactions, dividend_income=ZERO):
    """One canonical ordered replay per asset, independent of retrieval order."""
    replay = replay_symbol_transactions(order_transactions(transactions))
    summary = replay.summary
    dividend_income = to_decimal(dividend_income)
    return AssetFinancialSnapshot(
        symbol, _readonly(summary), dividend_income,
        _readonly(calculate_realized_earnings_metrics(summary['realized_trading_pnl'], dividend_income, summary['released_cost_basis'])),
        _readonly({row.transaction_id: row for row in replay.projections if row.transaction_id is not None}),
    )


def aggregate_transaction_summaries(assets):
    """Roll up replay results without replaying any symbol a second time."""
    totals = dict.fromkeys((
        'total_purchase_cost', 'total_buy_fees', 'total_buy_quantity',
        'net_sale_proceeds', 'total_sell_fees', 'total_sell_quantity',
        'total_quantity_held', 'realized_trading_pnl', 'position_cost_basis',
        'released_cost_basis',
    ), ZERO)
    totals['transaction_count'] = 0
    for asset in assets:
        for key in totals:
            if key == 'transaction_count':
                totals[key] += asset.transactions[key]
            else:
                totals[key] = exact_add(totals[key], asset.transactions[key])
    # Preserve the legacy cross-symbol weighted-average semantic concept.
    average = ZERO
    if totals['total_quantity_held'] > ZERO:
        weighted_cost = exact_sum(
            exact_multiply(a.transactions['average_unit_cost'], a.transactions['total_quantity_held'])
            for a in assets
        )
        average = financial_divide(weighted_cost, totals['total_quantity_held'])
    return {**totals, 'average_unit_cost': average}


@dataclass(frozen=True)
class PortfolioFinancialSnapshot:
    portfolio_id: int
    name: str
    assets: Mapping[str, AssetFinancialSnapshot]
    transactions: Mapping[str, Union[Decimal, int]]
    gross_deposits: Decimal
    net_contributions: Decimal
    cash_balance: Decimal
    dividend_income: Decimal
    metrics: Mapping[str, Union[Decimal, str, None]]
    dividend_income_by_symbol: Mapping[str, Decimal]

    @property
    def withdrawals(self):
        return exact_subtract(self.gross_deposits, self.net_contributions)

    def asset(self, symbol):
        if symbol in self.assets:
            return self.assets[symbol]
        return build_asset_snapshot(symbol, [])

    def as_portfolio_row(self):
        return {
            'id': self.portfolio_id,
            'name': self.name,
            'gross_deposits': self.gross_deposits,
            'net_contributions': self.net_contributions,
            'cash_balance': self.cash_balance,
            'position_cost_basis': self.transactions['position_cost_basis'],
            'realized_trading_pnl': self.transactions['realized_trading_pnl'],
            'dividend_income': self.dividend_income,
            **self.metrics,
        }

    def as_realized_earnings(self):
        return {
            **{key: self.transactions[key] for key in (
                'realized_trading_pnl', 'released_cost_basis', 'net_sale_proceeds',
            )},
            'dividend_income': self.dividend_income,
            **{key: self.metrics[key] for key in (
                'realized_trading_pnl', 'released_cost_basis', 'dividend_income',
                'total_realized_earnings', 'realized_trading_return',
            )},
        }


def build_portfolio_snapshot(*, portfolio_id, name, assets, gross_deposits,
                             net_contributions, cash_transactions, dividend_income,
                             dividend_income_by_symbol):
    summary = aggregate_transaction_summaries(tuple(assets.values()))
    # Keep the existing sequential cash_balance calculation (not a reassociated
    # N - total_buys + total_sales expression); do not change cash_balance policy.
    cash_balance = calculate_cash_balance(net_contributions, cash_transactions, dividend_income)
    metrics = calculate_portfolio_metrics(
        cash_balance, summary['position_cost_basis'], summary['realized_trading_pnl'], dividend_income, summary['released_cost_basis'],
    )
    return PortfolioFinancialSnapshot(
        portfolio_id, name, _readonly(assets), _readonly(summary),
        gross_deposits, net_contributions, cash_balance, dividend_income, _readonly(metrics),
        _readonly(dividend_income_by_symbol),
    )


@dataclass(frozen=True)
class GlobalFinancialSnapshot:
    portfolios: Tuple[PortfolioFinancialSnapshot, ...]
    totals: Mapping[str, Union[Decimal, str, None]]
    total_book_value: Decimal

    def as_portfolio_summary(self):
        rows = []
        for portfolio in self.portfolios:
            row = portfolio.as_portfolio_row()
            row['allocation'] = (
                financial_percent(row['book_value'], self.total_book_value.copy_abs())
                if self.total_book_value != ZERO else ZERO
            )
            rows.append(row)
        return rows, self.total_book_value

    def as_symbol_financials(self):
        # Preserve the existing response order: traded symbols across all
        # portfolios first, then the dividend_income-only symbols.
        traded, income_only = [], []
        for portfolio in self.portfolios:
            for asset in portfolio.assets.values():
                target = traded if asset.transactions['transaction_count'] else income_only
                target.append(asset.as_financial_row(portfolio.portfolio_id, portfolio.name))
        return traded + income_only


def build_global_snapshot(portfolios):
    portfolios = tuple(portfolios)
    totals = {
        'gross_deposits': exact_sum(p.gross_deposits for p in portfolios),
        'net_contributions': exact_sum(p.net_contributions for p in portfolios),
        'cash_balance': exact_sum(p.cash_balance for p in portfolios),
        'position_cost_basis': exact_sum(p.transactions['position_cost_basis'] for p in portfolios),
        'realized_trading_pnl': exact_sum(p.transactions['realized_trading_pnl'] for p in portfolios),
        'released_cost_basis': exact_sum(p.transactions['released_cost_basis'] for p in portfolios),
        'dividend_income': exact_sum(p.dividend_income for p in portfolios),
    }
    metrics = calculate_portfolio_metrics(
        totals['cash_balance'], totals['position_cost_basis'], totals['realized_trading_pnl'],
        totals['dividend_income'], totals['released_cost_basis'],
    )
    totals.update(metrics)
    total_book_value = exact_sum(p.metrics['book_value'] for p in portfolios)
    return GlobalFinancialSnapshot(portfolios, _readonly(totals), total_book_value)
