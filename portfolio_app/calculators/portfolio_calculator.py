"""Portfolio calculator for financial calculations."""

from decimal import Decimal
from sqlalchemy import case, func
from portfolio_app import db
from portfolio_app.models import Portfolio, Transaction, PortfolioEvent, Dividend
from portfolio_app.utils.decimal_utils import ZERO, to_decimal as _to_decimal, safe_divide as _safe_divide

# Realized P&L is computed on demand from the transactions table. There is
# intentionally no snapshot table — a single source of truth eliminates the
# class of bugs where a stored snapshot drifts from the underlying trades
# (e.g., orphan rows surviving a deletion under FK-OFF SQLite).


def _roi_display(pnl: Decimal, base: Decimal) -> tuple:
    """Compute ROI percentage and display string.

    Returns:
        (roi_percent, roi_display) — both ZERO/'—' when base is zero.
    """
    if base == 0:
        return ZERO, '—'
    roi = (pnl / abs(base)) * 100
    return roi, f"{roi:+,.2f}%"


class PortfolioCalculator:
    """Utility class for portfolio calculations."""

    _to_decimal = staticmethod(_to_decimal)

    @staticmethod
    def normalize_symbol(symbol) -> str:
        if symbol is None:
            return ''
        return str(symbol).strip().upper()

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_quantity_held_for_symbol(portfolio_id, symbol, exclude_transaction_id=None):
        """Return current quantity held for a specific symbol inside a portfolio."""
        normalized = PortfolioCalculator.normalize_symbol(symbol)

        query = Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=normalized)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        transactions = query.order_by(Transaction.date.asc()).all()

        running_quantity = ZERO
        for t in transactions:
            qty = _to_decimal(t.quantity)
            if t.transaction_type == 'Buy':
                running_quantity += qty
            elif t.transaction_type == 'Sell':
                running_quantity -= qty

        return running_quantity

    # ------------------------------------------------------------------
    # Portfolio-level aggregates
    # ------------------------------------------------------------------

    @staticmethod
    def get_total_portfolio_value(user_id=None):
        """Total portfolio value (invested + cash across all portfolios)."""
        q = Portfolio.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        portfolios = q.all()
        total = ZERO
        for p in portfolios:
            cash = PortfolioCalculator.get_available_cash_for_portfolio(p.id)
            tx_summary = PortfolioCalculator.get_portfolio_transactions_summary(p.id)
            invested = _to_decimal(tx_summary['cost_basis'] or 0)
            total += invested + cash
        return total

    @staticmethod
    def get_total_deposits_for_portfolio(portfolio_id) -> Decimal:
        """Total deposits = sum of Initial + Deposit events only.

        Withdrawals are excluded so this represents gross capital ever allocated.
        """
        result = (
            db.session.query(func.sum(PortfolioEvent.amount_delta))
            .filter(
                PortfolioEvent.portfolio_id == portfolio_id,
                PortfolioEvent.event_type.in_(['Initial', 'Deposit']),
            )
            .scalar()
        )
        return _to_decimal(result) if result is not None else ZERO

    @staticmethod
    def get_net_deposits_for_portfolio(portfolio_id) -> Decimal:
        """Net deposits = signed sum of all PortfolioEvent rows.

        ``amount_delta`` is positive for Initial/Deposit and negative for
        Withdrawal, so a plain SUM gives ``deposits − withdrawals``. This
        replaces the denormalized ``portfolio.net_deposits`` column whose
        value could drift if the events log was edited outside the service.
        """
        result = (
            db.session.query(func.sum(PortfolioEvent.amount_delta))
            .filter(PortfolioEvent.portfolio_id == portfolio_id)
            .scalar()
        )
        return _to_decimal(result) if result is not None else ZERO

    @staticmethod
    def get_available_cash_for_portfolio(portfolio_id, exclude_transaction_id=None) -> Decimal:
        """Available cash: net deposits − buy_outflows + sell_inflows + dividends."""
        cash = PortfolioCalculator.get_net_deposits_for_portfolio(portfolio_id)
        query = Transaction.query.filter_by(portfolio_id=portfolio_id)
        if exclude_transaction_id is not None:
            query = query.filter(Transaction.id != exclude_transaction_id)
        transactions = query.order_by(Transaction.date.asc()).all()

        for t in transactions:
            price = _to_decimal(t.price)
            quantity = _to_decimal(t.quantity)
            fees = _to_decimal(t.fees)
            gross = price * quantity

            if t.transaction_type == 'Buy':
                cash -= gross + fees
            elif t.transaction_type == 'Sell':
                cash += gross - fees

        cash += PortfolioCalculator.get_dividend_total_for_portfolio(portfolio_id)
        return cash

    # ------------------------------------------------------------------
    # Portfolio summary (dashboard cards)
    # ------------------------------------------------------------------

    @staticmethod
    def get_portfolio_summary(user_id=None):
        """Get summary for each portfolio."""
        q = Portfolio.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        portfolios = q.all()

        portfolio_rows = []
        total_portfolio_value = ZERO
        for portfolio in portfolios:
            total_contributed = PortfolioCalculator.get_total_deposits_for_portfolio(portfolio.id)

            realized_perf = PortfolioCalculator.get_realized_performance_for_portfolio(portfolio.id)
            realized_pnl = realized_perf['realized_pnl']
            total_dividends = realized_perf['total_dividends']

            transactions_summary = PortfolioCalculator.get_portfolio_transactions_summary(portfolio.id)
            cost_basis = _to_decimal(transactions_summary['cost_basis'] or 0)

            cash = PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id)
            book_value = cost_basis + cash
            total_portfolio_value += book_value

            roi_base = total_contributed if total_contributed != 0 else realized_perf['realized_cost_basis']
            realized_roi_percent, realized_roi_display = _roi_display(realized_pnl, roi_base)

            portfolio_rows.append({
                'portfolio': portfolio,
                'total_contributed': total_contributed,
                'realized_pnl': realized_pnl,
                'cost_basis': cost_basis,
                'cash': cash,
                'book_value': book_value,
                'realized_roi_percent': realized_roi_percent,
                'realized_roi_display': realized_roi_display,
                'total_dividends': total_dividends,
            })

        summary = []
        for row in portfolio_rows:
            allocation = (row['book_value'] / abs(total_portfolio_value) * 100) if total_portfolio_value != 0 else ZERO

            summary.append({
                'name': row['portfolio'].name,
                'total_contributed': row['total_contributed'],
                'allocation': Decimal(str(allocation)),
                'id': row['portfolio'].id,
                'realized_pnl': row['realized_pnl'],
                'cost_basis': row['cost_basis'],
                'book_value': row['book_value'],
                'cash': row['cash'],
                'realized_roi_percent': row['realized_roi_percent'],
                'realized_roi_display': row['realized_roi_display'],
                'total_dividends': row['total_dividends'],
            })

        return summary, total_portfolio_value

    # ------------------------------------------------------------------
    # Dividend helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_dividend_total_for_portfolio(portfolio_id) -> Decimal:
        """Return the sum of dividend income for a portfolio."""
        result = (
            Dividend.query
            .with_entities(func.sum(Dividend.amount))
            .filter(Dividend.portfolio_id == portfolio_id)
            .scalar()
        )
        return _to_decimal(result) if result else ZERO

    # ------------------------------------------------------------------
    # Realized P&L helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_realized_performance_for_portfolio(portfolio_id):
        """Return realized P&L (including dividends), cost basis, and proceeds for a portfolio.

        Computed by walking the transactions table per symbol with the
        average-cost method — no snapshot table involved, so deleting a
        sell removes its contribution immediately.
        """
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(portfolio_id=portfolio_id)
            .distinct()
            .all()
        )

        realized_pnl        = ZERO
        realized_cost_basis = ZERO
        realized_proceeds   = ZERO

        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            s = PortfolioCalculator.get_symbol_transactions_summary(portfolio_id, sym_norm)
            realized_pnl        += _to_decimal(s['realized_pnl'])
            realized_cost_basis += _to_decimal(s['realized_cost_basis'])
            realized_proceeds   += _to_decimal(s['realized_proceeds'])

        dividends = PortfolioCalculator.get_dividend_total_for_portfolio(portfolio_id)
        realized_pnl += dividends

        return {
            'realized_pnl':        realized_pnl,
            'realized_cost_basis': realized_cost_basis,
            'realized_proceeds':   realized_proceeds,
            'total_dividends':     dividends,
        }

    # ------------------------------------------------------------------
    # Dashboard totals
    # ------------------------------------------------------------------

    @staticmethod
    def get_portfolio_dashboard_totals(user_id=None):
        """Dashboard totals: investment, cash, ROI."""
        q = Portfolio.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        portfolios = q.all()

        total_contributed = ZERO
        total_cash = ZERO
        total_cost_basis = ZERO
        total_realized_pnl = ZERO
        total_realized_cost_basis = ZERO
        total_dividends = ZERO

        for portfolio in portfolios:
            total_contributed += PortfolioCalculator.get_total_deposits_for_portfolio(portfolio.id)
            total_cash += PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id)

            tx_summary = PortfolioCalculator.get_portfolio_transactions_summary(portfolio.id)
            total_cost_basis += _to_decimal(tx_summary['cost_basis'] or 0)

            realized_perf = PortfolioCalculator.get_realized_performance_for_portfolio(portfolio.id)
            total_realized_pnl += realized_perf['realized_pnl']
            total_realized_cost_basis += realized_perf['realized_cost_basis']
            total_dividends += realized_perf['total_dividends']

        total_value = total_cost_basis + total_cash

        roi_base = total_contributed if total_contributed != 0 else total_realized_cost_basis
        realized_roi_percent, realized_roi_display = _roi_display(total_realized_pnl, roi_base)

        return {
            'total_contributed': total_contributed,
            'total_cash': total_cash,
            'total_realized_pnl': total_realized_pnl,
            'total_dividends': total_dividends,
            'total_value': total_value,
            'realized_roi_percent': realized_roi_percent,
            'realized_roi_display': realized_roi_display,
        }

    # ------------------------------------------------------------------
    # Symbol-level performance (across a user's portfolios)
    # ------------------------------------------------------------------

    @staticmethod
    def get_user_symbol_performance(user_id):
        """Per-(portfolio, symbol) realized performance across a user's portfolios.

        Each row represents a single (portfolio, ticker) pair. A ticker held
        in multiple portfolios surfaces as multiple rows by design — the
        unique constraint on Symbol is per-portfolio, not per-user, and the
        consequence of that duplication belongs to the user.

        ``total_realized_pnl`` combines:
          * trading P&L from Sells (average-cost method, computed per
            (portfolio, symbol) so cross-portfolio lots stay independent), and
          * dividends attributed to the symbol via Dividend.symbol.

        The ROI base falls back from ``realized_cost_basis`` (cost of closed
        lots) to ``held_cost_basis`` (running cost of the still-open
        position) so a dividend-only or hold-only position still gets a
        meaningful denominator instead of '—'.

        Returns a flat list — sorting and Top-N aggregation are caller
        concerns so this stays composable across views.
        """
        if user_id is None:
            return []

        portfolios = Portfolio.query.filter_by(user_id=user_id).all()
        if not portfolios:
            return []

        portfolio_ids = [p.id for p in portfolios]
        portfolios_by_id = {p.id: p for p in portfolios}

        # One round-trip for all dividends grouped by (portfolio, symbol) —
        # avoids an N×M lookup inside the symbol loop below.
        dividend_rows = (
            db.session.query(
                Dividend.portfolio_id,
                Dividend.symbol,
                func.sum(Dividend.amount).label('total'),
            )
            .filter(Dividend.portfolio_id.in_(portfolio_ids))
            .group_by(Dividend.portfolio_id, Dividend.symbol)
            .all()
        )
        dividend_by_key = {
            (r.portfolio_id, PortfolioCalculator.normalize_symbol(r.symbol)): _to_decimal(r.total)
            for r in dividend_rows
        }

        rows = []
        seen_keys = set()

        for portfolio in portfolios:
            symbols = (
                Transaction.query.with_entities(Transaction.symbol)
                .filter_by(portfolio_id=portfolio.id)
                .distinct()
                .all()
            )
            for (sym,) in symbols:
                sym_norm = PortfolioCalculator.normalize_symbol(sym)
                if not sym_norm:
                    continue
                key = (portfolio.id, sym_norm)
                seen_keys.add(key)

                summary = PortfolioCalculator.get_symbol_transactions_summary(portfolio.id, sym_norm)
                rows.append(
                    PortfolioCalculator._build_symbol_performance_row(
                        portfolio=portfolio,
                        symbol=sym_norm,
                        trading_pnl=_to_decimal(summary['realized_pnl']),
                        dividends=dividend_by_key.get(key, ZERO),
                        realized_cost_basis=_to_decimal(summary['realized_cost_basis']),
                        held_cost_basis=_to_decimal(summary['cost_basis']),
                    )
                )

        # Surface dividend-only symbols (Dividend rows with no matching
        # Transaction history). Rare, but possible for transferred-in
        # holdings recorded only as income.
        for (pid, sym_norm), divs in dividend_by_key.items():
            if (pid, sym_norm) in seen_keys:
                continue
            portfolio = portfolios_by_id.get(pid)
            if portfolio is None:
                continue
            rows.append(
                PortfolioCalculator._build_symbol_performance_row(
                    portfolio=portfolio,
                    symbol=sym_norm,
                    trading_pnl=ZERO,
                    dividends=divs,
                    realized_cost_basis=ZERO,
                    held_cost_basis=ZERO,
                )
            )

        return rows

    @staticmethod
    def _build_symbol_performance_row(*, portfolio, symbol, trading_pnl, dividends,
                                      realized_cost_basis, held_cost_basis):
        """Shape a single symbol-performance row with derived ROI fields."""
        total_pnl = trading_pnl + dividends
        roi_base = realized_cost_basis if realized_cost_basis != 0 else held_cost_basis
        roi_percent, roi_display = _roi_display(total_pnl, roi_base)
        return {
            'portfolio_id':         portfolio.id,
            'portfolio_name':       portfolio.name,
            'symbol':               symbol,
            'realized_pnl':         trading_pnl,
            'dividend_total':       dividends,
            'total_realized_pnl':   total_pnl,
            'realized_cost_basis':  realized_cost_basis,
            'held_cost_basis':      held_cost_basis,
            'roi_base':             roi_base,
            'roi_percent':          roi_percent,
            'roi_display':          roi_display,
        }

    # ------------------------------------------------------------------
    # Transaction summaries
    # ------------------------------------------------------------------

    @staticmethod
    def get_portfolio_transactions_summary(portfolio_id):
        """Get aggregated transaction summary for a portfolio (all symbols combined)."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(portfolio_id=portfolio_id)
            .distinct()
            .all()
        )

        totals = {
            'total_buy_cost': ZERO,
            'total_buy_fees': ZERO,
            'total_buy_quantity': ZERO,
            'total_sell_cost': ZERO,
            'total_sell_fees': ZERO,
            'total_sell_quantity': ZERO,
            'total_quantity_held': ZERO,
            'realized_pnl': ZERO,
            'cost_basis': ZERO,
            'transaction_count': 0,
        }

        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            summary = PortfolioCalculator.get_symbol_transactions_summary(portfolio_id, sym_norm)
            for key in totals:
                if key == 'transaction_count':
                    totals[key] += int(summary[key])
                else:
                    totals[key] += _to_decimal(summary[key])

        avg_cost = ZERO
        if totals['total_quantity_held'] > 0:
            weighted_cost = ZERO
            for (sym,) in symbols:
                sym_norm = PortfolioCalculator.normalize_symbol(sym)
                if not sym_norm:
                    continue
                s = PortfolioCalculator.get_symbol_transactions_summary(portfolio_id, sym_norm)
                weighted_cost += _to_decimal(s['average_cost']) * _to_decimal(s['total_quantity_held'])
            avg_cost = weighted_cost / totals['total_quantity_held']

        return {**totals, 'average_cost': avg_cost}

    @staticmethod
    def get_symbol_transactions_summary(portfolio_id, symbol):
        """Get aggregated transaction summary for a specific symbol."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        buy_first = case((Transaction.transaction_type == 'Buy', 0), else_=1)
        transactions = (
            Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=symbol)
            .order_by(func.date(Transaction.date).asc(), buy_first, Transaction.id.asc())
            .all()
        )
        return PortfolioCalculator.get_symbol_transactions_summary_from_list(transactions)

    @staticmethod
    def get_symbol_transactions_summary_from_list(transactions):
        """Get aggregated summary from a pre-sorted list of transactions.

        Uses average-cost method: each sell realizes P&L based on the
        weighted-average cost of the remaining position at time of sale.
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

        for t in transactions:
            price = _to_decimal(t.price)
            quantity = _to_decimal(t.quantity)
            fees = _to_decimal(t.fees)

            if t.transaction_type == 'Buy':
                cost = (price * quantity) + fees
                total_buy_cost += cost
                total_buy_fees += fees
                total_buy_quantity += quantity
                running_cost += cost
                running_quantity += quantity

            elif t.transaction_type == 'Sell':
                proceeds = (price * quantity) - fees
                total_sell_cost += proceeds
                total_sell_fees += fees
                total_sell_quantity += quantity
                realized_proceeds += proceeds

                avg_cost = _safe_divide(running_cost, running_quantity)
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
            'average_cost': _safe_divide(running_cost, running_quantity),
            'transaction_count': len(transactions),
            'realized_pnl': realized_pnl,
            'realized_cost_basis': realized_cost_basis,
            'realized_proceeds': realized_proceeds,
            'cost_basis': running_cost,
        }

    # ------------------------------------------------------------------
    # Recalculation (after add/edit/delete transaction)
    # ------------------------------------------------------------------

    @staticmethod
    def recalculate_all_averages_for_portfolio(portfolio_id):
        """Recalculate average costs for all transactions of a portfolio."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(portfolio_id=portfolio_id)
            .distinct()
            .all()
        )

        updated = []
        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            updated.extend(PortfolioCalculator.recalculate_all_averages_for_symbol(portfolio_id, sym_norm))

        return updated

    @staticmethod
    def recalculate_all_averages_for_symbol(portfolio_id, symbol):
        """Recalculate average costs and net_amount for all transactions of a
        (portfolio, symbol) pair. The caller is responsible for committing.
        """
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        buy_first = case((Transaction.transaction_type == 'Buy', 0), else_=1)
        transactions = (
            Transaction.query.filter_by(portfolio_id=portfolio_id, symbol=symbol)
            .order_by(func.date(Transaction.date).asc(), buy_first, Transaction.id.asc())
            .all()
        )

        running_quantity = ZERO
        running_cost = ZERO

        for transaction in transactions:
            transaction.calculate_net_amount()

            if transaction.transaction_type == 'Buy':
                cost = (
                    _to_decimal(transaction.price) * _to_decimal(transaction.quantity)
                    + _to_decimal(transaction.fees)
                )
                running_cost += cost
                running_quantity += _to_decimal(transaction.quantity)
                transaction.average_cost = _safe_divide(running_cost, running_quantity)

            elif transaction.transaction_type == 'Sell':
                sell_qty = _to_decimal(transaction.quantity)
                avg_cost = _safe_divide(running_cost, running_quantity)
                transaction.average_cost = avg_cost
                running_quantity -= sell_qty
                running_cost     -= avg_cost * sell_qty

        return transactions
