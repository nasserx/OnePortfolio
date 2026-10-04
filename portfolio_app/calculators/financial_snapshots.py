"""Pure, read-only aggregate financial views and legacy response adapters.

SQL loading belongs to PortfolioCalculator; arithmetic belongs to financial_math.
Snapshots are per-read values, never persisted or cached. Dictionary keys in the
adapters intentionally preserve the existing HTTP/template vocabulary.
"""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Tuple, Union

from portfolio_app.calculators.financial_math import (
    calculate_asset_return,
    calculate_cash_balance,
    calculate_portfolio_metrics,
    replay_symbol_transactions,
    TransactionFinancialProjection,
)
from portfolio_app.calculators.transaction_order import order_transactions
from portfolio_app.utils.decimal_utils import ZERO, to_decimal


def _readonly(values):
    return MappingProxyType(dict(values))


def apply_asset_summary_return(summary, income=ZERO):
    """Legacy Assets adapter: undefined percentage is None, not numeric zero.

    Valid purchase outflows are positive. Keep the shared return calculation and
    only adapt the undefined value used by the existing template.
    """
    purchase_cost = to_decimal(summary.get('total_buy_cost', ZERO) or ZERO)
    result = calculate_asset_return(
        summary.get('realized_pnl', ZERO) or ZERO,
        income or ZERO,
        purchase_cost,
    )
    if purchase_cost == ZERO:
        result['return_percent'] = None
    summary.update(result)
    return summary


def sum_income_details(dividends):
    """Canonical income grouping from persisted Decimal rows in ID order."""
    totals = {}
    for dividend in dividends:
        symbol = (dividend.symbol or '').strip().upper()
        if symbol:
            totals[symbol] = totals.get(symbol, ZERO) + to_decimal(dividend.amount)
    return totals


@dataclass(frozen=True)
class AssetFinancialSnapshot:
    symbol: str
    transactions: Mapping[str, Union[Decimal, int]]
    income: Decimal
    returns: Mapping[str, Union[Decimal, str]]
    transaction_projections: Mapping[int, TransactionFinancialProjection]

    def as_assets_summary(self):
        """Fresh mutable template adapter; never mutate the underlying snapshot."""
        return apply_asset_summary_return(
            dict(self.transactions),
            self.income,
        )

    def as_performance_row(self, portfolio_id, portfolio_name):
        summary = self.transactions
        return {
            'portfolio_id': portfolio_id,
            'portfolio_name': portfolio_name,
            'symbol': self.symbol,
            'realized_pnl': summary['realized_pnl'],
            'total_income': self.income,
            'total_buy_cost': summary['total_buy_cost'],
            'realized_cost_basis': summary['realized_cost_basis'],
            'held_cost_basis': summary['cost_basis'],
            'return_base': summary['total_buy_cost'],
            **self.returns,
        }


def build_asset_snapshot(symbol, transactions, income=ZERO):
    """One canonical ordered replay per asset, independent of retrieval order."""
    replay = replay_symbol_transactions(order_transactions(transactions))
    summary = replay.summary
    income = to_decimal(income)
    return AssetFinancialSnapshot(
        symbol, _readonly(summary), income,
        _readonly(calculate_asset_return(summary['realized_pnl'], income, summary['total_buy_cost'])),
        _readonly({row.transaction_id: row for row in replay.projections if row.transaction_id is not None}),
    )


def aggregate_transaction_summaries(assets):
    """Roll up replay results without replaying any symbol a second time."""
    totals = dict.fromkeys((
        'total_buy_cost', 'total_buy_fees', 'total_buy_quantity',
        'total_sell_cost', 'total_sell_fees', 'total_sell_quantity',
        'total_quantity_held', 'realized_pnl', 'cost_basis',
        'realized_cost_basis', 'realized_proceeds',
    ), ZERO)
    totals['transaction_count'] = 0
    for asset in assets:
        for key in totals:
            totals[key] += asset.transactions[key]
    # Preserve the legacy cross-symbol weighted average, including its Decimal
    # operation order. It is not a market price or a new economic metric.
    average = ZERO
    if totals['total_quantity_held'] > ZERO:
        weighted_cost = sum((
            a.transactions['average_cost'] * a.transactions['total_quantity_held']
            for a in assets
        ), ZERO)
        average = weighted_cost / totals['total_quantity_held']
    return {**totals, 'average_cost': average}


@dataclass(frozen=True)
class PortfolioFinancialSnapshot:
    portfolio_id: int
    name: str
    assets: Mapping[str, AssetFinancialSnapshot]
    transactions: Mapping[str, Union[Decimal, int]]
    funding_inflows: Decimal
    net_contributions: Decimal
    cash_balance: Decimal
    income: Decimal
    metrics: Mapping[str, Union[Decimal, str]]
    income_by_symbol: Mapping[str, Decimal]

    @property
    def withdrawals(self):
        return self.funding_inflows - self.net_contributions

    def asset(self, symbol):
        if symbol in self.assets:
            return self.assets[symbol]
        return build_asset_snapshot(symbol, [])

    def as_portfolio_row(self):
        return {
            'id': self.portfolio_id,
            'name': self.name,
            'total_contributed': self.funding_inflows,
            'total_capital': self.net_contributions,
            'cash': self.cash_balance,
            'positions': self.transactions['cost_basis'],
            'cost_basis': self.transactions['cost_basis'],
            'realized_pnl': self.transactions['realized_pnl'],
            'total_income': self.income,
            **self.metrics,
        }

    def as_realized_performance(self):
        return {
            **{key: self.transactions[key] for key in (
                'realized_pnl', 'realized_cost_basis', 'realized_proceeds',
            )},
            'total_income': self.income,
            'return_amount': self.metrics['return_amount'],
        }


def build_portfolio_snapshot(*, portfolio_id, name, assets, funding_inflows,
                             net_contributions, cash_transactions, income,
                             income_by_symbol):
    summary = aggregate_transaction_summaries(tuple(assets.values()))
    # Keep the existing sequential cash calculation (not a reassociated
    # N - total_buys + total_sales expression); do not change cash policy.
    cash = calculate_cash_balance(net_contributions, cash_transactions, income)
    metrics = calculate_portfolio_metrics(
        cash, summary['cost_basis'], summary['realized_pnl'], income, funding_inflows,
    )
    return PortfolioFinancialSnapshot(
        portfolio_id, name, _readonly(assets), _readonly(summary),
        funding_inflows, net_contributions, cash, income, _readonly(metrics),
        _readonly(income_by_symbol),
    )


@dataclass(frozen=True)
class GlobalFinancialSnapshot:
    portfolios: Tuple[PortfolioFinancialSnapshot, ...]
    totals: Mapping[str, Union[Decimal, str]]
    total_book_value: Decimal

    def as_portfolio_summary(self):
        rows = []
        for portfolio in self.portfolios:
            row = portfolio.as_portfolio_row()
            row['allocation'] = (
                row['book_value'] / abs(self.total_book_value) * 100
                if self.total_book_value != ZERO else ZERO
            )
            rows.append(row)
        return rows, self.total_book_value

    def as_symbol_performance(self):
        # Preserve the existing response order: traded symbols across all
        # portfolios first, then the income-only symbols.
        traded, income_only = [], []
        for portfolio in self.portfolios:
            for asset in portfolio.assets.values():
                target = traded if asset.transactions['transaction_count'] else income_only
                target.append(asset.as_performance_row(portfolio.portfolio_id, portfolio.name))
        return traded + income_only


def build_global_snapshot(portfolios):
    portfolios = tuple(portfolios)
    totals = {
        'total_contributed': sum((p.funding_inflows for p in portfolios), ZERO),
        'total_capital': sum((p.net_contributions for p in portfolios), ZERO),
        'total_cash': sum((p.cash_balance for p in portfolios), ZERO),
        'total_positions': sum((p.transactions['cost_basis'] for p in portfolios), ZERO),
        'realized_pnl': sum((p.transactions['realized_pnl'] for p in portfolios), ZERO),
        'total_income': sum((p.income for p in portfolios), ZERO),
    }
    metrics = calculate_portfolio_metrics(
        totals['total_cash'], totals['total_positions'], totals['realized_pnl'],
        totals['total_income'], totals['total_contributed'],
    )
    totals.update(metrics)
    totals['total_value'] = totals.pop('book_value')
    # Existing summary and dashboard have distinct Decimal association orders.
    # Do not silently reassociate them in an architectural refactor.
    total_book_value = sum((p.metrics['book_value'] for p in portfolios), ZERO)
    return GlobalFinancialSnapshot(portfolios, _readonly(totals), total_book_value)
