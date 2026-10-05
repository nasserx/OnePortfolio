"""Database-facing financial façade and legacy response adapters.

Aggregate reads compose immutable snapshots using the pure financial engine.
All derived transaction values are read projections; mutations persist raw facts.
"""

from decimal import Decimal
from portfolio_app.calculators.transaction_order import order_transactions
from portfolio_app.calculators.financial_math import (
    calculate_cash_balance,
    calculate_quantity_held,
)
from portfolio_app.calculators.financial_snapshots import (
    build_asset_snapshot, build_portfolio_snapshot, build_global_snapshot,
    sum_dividend_income_details,
)
from portfolio_app.models import Portfolio, Transaction, PortfolioEvent, Dividend
from portfolio_app.utils.decimal_utils import ZERO, to_decimal as _to_decimal
from portfolio_app.utils.financial_arithmetic import exact_sum

# Realized P&L is computed on demand from the transactions table. There is
# intentionally no snapshot table — a single source of truth eliminates the
# class of bugs where a stored snapshot drifts from the underlying trades
# (e.g., orphan rows surviving a deletion under FK-OFF SQLite).

class PortfolioCalculator:
    """Utility class for portfolio calculations.

    Most read methods accept an optional keyword-only ``user_id`` argument.
    When provided, the underlying SQL query joins ``Portfolio`` and filters
    by ``Portfolio.user_id`` — defence-in-depth against a caller that
    accidentally passes a portfolio_id that doesn't belong to the current
    user. Callers in the service layer thread the value through from the
    repository's ``user_id`` property so the calculator never trusts the
    caller blindly.

    The argument is *optional* (default ``None``) for backwards
    compatibility with internal recursive calls and tests; treat omitting
    it as a deliberate choice, not a free pass.
    """

    _to_decimal = staticmethod(_to_decimal)

    @staticmethod
    def _scope_to_user(query, model_cls, user_id):
        """Add a Portfolio JOIN + user_id filter when ``user_id`` is given.

        Returns the query unchanged if ``user_id`` is None, so the helper
        is a no-op for legacy unscoped call sites. Models passed in must
        carry a ``portfolio_id`` column (Transaction, Dividend, PortfolioEvent).
        """
        if user_id is not None:
            query = query.join(Portfolio, model_cls.portfolio_id == Portfolio.id) \
                         .filter(Portfolio.user_id == user_id)
        return query

    @staticmethod
    def normalize_symbol(symbol) -> str:
        if symbol is None:
            return ''
        return str(symbol).strip().upper()

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_quantity_held_for_symbol(portfolio_id, symbol, *, user_id=None, exclude_transaction_id=None):
        """Return current quantity held for a specific symbol inside a portfolio."""
        normalized = PortfolioCalculator.normalize_symbol(symbol)

        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=normalized)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        transactions = query.order_by(Transaction.date.asc()).all()

        return calculate_quantity_held(transactions)

    # ------------------------------------------------------------------
    # Portfolio-level aggregates
    # ------------------------------------------------------------------

    @staticmethod
    def get_total_deposits_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Total deposits = sum of Initial + Deposit events only.

        Withdrawals are excluded: this is gross deposits, not Net Contributions.
        """
        query = (
            PortfolioEvent.query.with_entities(PortfolioEvent.amount_delta)
            .filter(
                PortfolioEvent.portfolio_id == portfolio_id,
                PortfolioEvent.event_type.in_(['Initial', 'Deposit']),
            )
        )
        query = PortfolioCalculator._scope_to_user(query, PortfolioEvent, user_id)
        return exact_sum(row.amount_delta for row in query.order_by(PortfolioEvent.id).all())

    @staticmethod
    def get_net_contributions_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Net Contributions = signed sum of all Funding Entries.

        ``amount_delta`` is positive for Initial/Deposit and negative for
        Withdrawal, so a plain SUM gives ``deposits − withdrawals``. This
        replaces the denormalized ``portfolio.net_deposits`` column whose
        value could drift if the events log was edited outside the service.
        """
        query = (
            PortfolioEvent.query.with_entities(PortfolioEvent.amount_delta)
            .filter(PortfolioEvent.portfolio_id == portfolio_id)
        )
        query = PortfolioCalculator._scope_to_user(query, PortfolioEvent, user_id)
        return exact_sum(row.amount_delta for row in query.order_by(PortfolioEvent.id).all())

    @staticmethod
    def _cash_transactions(portfolio_id, *, user_id=None, exclude_transaction_id=None):
        """Cash and replay reads share deterministic canonical ordering."""
        query = Transaction.query.filter_by(portfolio_id=portfolio_id)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        return order_transactions(query.all())

    @staticmethod
    def get_cash_balance_for_portfolio(portfolio_id, *, user_id=None, exclude_transaction_id=None) -> Decimal:
        """Lightweight validation read, using the same pure cash_balance function as snapshots."""
        return calculate_cash_balance(
            PortfolioCalculator.get_net_contributions_for_portfolio(portfolio_id, user_id=user_id),
            PortfolioCalculator._cash_transactions(
                portfolio_id, user_id=user_id, exclude_transaction_id=exclude_transaction_id,
            ),
            PortfolioCalculator.get_dividend_total_for_portfolio(portfolio_id, user_id=user_id),
        )

    @staticmethod
    def get_portfolio_snapshot(portfolio_id, *, user_id=None):
        """Load scoped inputs once per financial view; never persist or cache results.

        Funding/dividend_income sum individually loaded Decimal column values, never SQL
        floating-point reductions. Trading values always come from fresh canonical
        replay, never persisted derivatives (removed in schema 36).
        """
        query = Portfolio.query.filter_by(id=portfolio_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        portfolio = query.first()

        dividend_income_by_symbol = PortfolioCalculator._dividend_income_by_symbol(portfolio_id, user_id=user_id)

        sym_query = Transaction.query.with_entities(Transaction.symbol).filter_by(portfolio_id=portfolio_id)
        sym_query = PortfolioCalculator._scope_to_user(sym_query, Transaction, user_id)
        symbols = [
            PortfolioCalculator.normalize_symbol(row.symbol)
            for row in sym_query.distinct().all()
            if PortfolioCalculator.normalize_symbol(row.symbol)
        ]
        assets = {}
        for symbol in symbols:
            assets[symbol] = PortfolioCalculator.get_asset_snapshot(
                portfolio_id, symbol, user_id=user_id,
                dividend_income=dividend_income_by_symbol.get(symbol, ZERO),
            )
        for symbol, dividend_income in dividend_income_by_symbol.items():
            if symbol not in assets:
                assets[symbol] = build_asset_snapshot(symbol, [], dividend_income)

        return build_portfolio_snapshot(
            portfolio_id=portfolio_id,
            name=portfolio.name if portfolio is not None else '',
            assets=assets,
            gross_deposits=PortfolioCalculator.get_total_deposits_for_portfolio(portfolio_id, user_id=user_id),
            net_contributions=PortfolioCalculator.get_net_contributions_for_portfolio(portfolio_id, user_id=user_id),
            cash_transactions=PortfolioCalculator._cash_transactions(portfolio_id, user_id=user_id),
            dividend_income=exact_sum(dividend_income_by_symbol.values()),
            dividend_income_by_symbol=dividend_income_by_symbol,
        )

    @staticmethod
    def get_financial_snapshot(user_id=None):
        """Canonical global read model; every aggregate consumer uses this path."""
        query = Portfolio.query
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        return build_global_snapshot(
            PortfolioCalculator.get_portfolio_snapshot(portfolio.id, user_id=user_id)
            for portfolio in query.all()
        )

    @staticmethod
    def get_portfolio_summary(user_id=None):
        return PortfolioCalculator.get_financial_snapshot(user_id).as_portfolio_summary()

    @staticmethod
    def get_portfolio_dashboard_totals(user_id=None):
        return dict(PortfolioCalculator.get_financial_snapshot(user_id).totals)

    @staticmethod
    def get_realized_earnings_for_portfolio(portfolio_id, *, user_id=None):
        return PortfolioCalculator.get_portfolio_snapshot(
            portfolio_id, user_id=user_id,
        ).as_realized_earnings()

    @staticmethod
    def get_user_symbol_financials(user_id):
        if user_id is None:
            return []
        return PortfolioCalculator.get_financial_snapshot(user_id).as_symbol_financials()

    @staticmethod
    def get_portfolio_transactions_summary(portfolio_id, *, user_id=None):
        snapshot = PortfolioCalculator.get_portfolio_snapshot(portfolio_id, user_id=user_id)
        return dict(snapshot.transactions)

    @staticmethod
    def get_asset_snapshot(portfolio_id, symbol, *, user_id=None, dividend_income=None):
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=symbol)
        query = PortfolioCalculator._scope_to_user(query, Transaction, user_id)
        if dividend_income is None:
            dividend_income = PortfolioCalculator._dividend_income_by_symbol(
                portfolio_id, user_id=user_id,
            ).get(symbol, ZERO)
        return build_asset_snapshot(symbol, query.all(), dividend_income)

    @staticmethod
    def get_symbol_transactions_summary(portfolio_id, symbol, *, user_id=None):
        return dict(PortfolioCalculator.get_asset_snapshot(
            portfolio_id, symbol, user_id=user_id,
        ).transactions)

    @staticmethod
    def get_symbol_transactions_summary_from_list(transactions):
        """Pure list entry point shares the same canonical asset replay boundary."""
        return dict(build_asset_snapshot('', transactions).transactions)

    @staticmethod
    def get_dividend_total_for_portfolio(portfolio_id, *, user_id=None) -> Decimal:
        """Return Dividend Income for a portfolio."""
        return exact_sum(PortfolioCalculator._dividend_income_by_symbol(portfolio_id, user_id=user_id).values())

    @staticmethod
    def _dividend_income_by_symbol(portfolio_id, *, user_id=None):
        # Aggregate exact persisted Decimal rows, never SQL numeric coercion.
        query = Dividend.query.with_entities(Dividend.symbol, Dividend.amount).filter_by(
            portfolio_id=portfolio_id,
        )
        query = PortfolioCalculator._scope_to_user(query, Dividend, user_id)
        return sum_dividend_income_details(query.order_by(Dividend.id).all())
