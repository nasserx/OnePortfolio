"""Portfolio calculator for financial calculations."""

from decimal import Decimal
from sqlalchemy import case, func
from portfolio_app.models import Fund, Transaction, FundEvent

ZERO = Decimal('0')


def _safe_divide(numerator, denominator, default=ZERO):
    """Divide numerator by denominator, returning default if denominator is zero."""
    return numerator / denominator if denominator else default


def _to_decimal(value) -> Decimal:
    """Convert any numeric value to Decimal safely."""
    return Decimal(str(value))


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
    def get_quantity_held_for_fund(fund_id, exclude_transaction_id=None):
        """Return current quantity held for a fund."""
        query = Transaction.query.filter_by(fund_id=fund_id)
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

    @staticmethod
    def get_quantity_held_for_symbol(fund_id, symbol, exclude_transaction_id=None):
        """Return current quantity held for a specific symbol inside a fund."""
        normalized = PortfolioCalculator.normalize_symbol(symbol)

        query = Transaction.query.filter_by(fund_id=fund_id, symbol=normalized)
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
        """Total portfolio value (invested + cash across all categories)."""
        q = Fund.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        funds = q.all()
        total = ZERO
        for f in funds:
            cash = PortfolioCalculator.get_cash_balance_for_fund(f.id)
            tx_summary = PortfolioCalculator.get_category_transactions_summary(f.id)
            invested = _to_decimal(tx_summary['current_invested'] or 0)
            total += invested + cash
        return total

    @staticmethod
    def get_total_funds_for_fund(fund_id) -> Decimal:
        """Total Funds = sum of Initial + Deposit events only.

        Withdrawals are excluded so that Total Funds represents the gross
        capital ever allocated to this category, not the net balance.
        Cash is the correct metric for what remains after withdrawals.

        Fallback: legacy funds with no event history return fund.amount
        directly so that old databases display correctly without migration.
        """
        rows = (
            FundEvent.query
            .with_entities(FundEvent.amount_delta)
            .filter(
                FundEvent.fund_id == fund_id,
                FundEvent.event_type.in_(['Initial', 'Deposit']),
            )
            .all()
        )
        if rows:
            return sum((_to_decimal(r.amount_delta) for r in rows), ZERO)

        # No event history — legacy fund. Use fund.amount as best approximation.
        fund = Fund.query.get(fund_id)
        return _to_decimal(fund.amount or 0) if fund else ZERO

    @staticmethod
    def get_cash_balance_for_fund(fund_id, exclude_transaction_id=None) -> Decimal:
        """Compute cash balance: fund_amount - buy_outflows + sell_inflows."""
        fund = Fund.query.get(fund_id)
        if not fund:
            return ZERO

        cash = _to_decimal(fund.amount or 0)
        query = Transaction.query.filter_by(fund_id=fund_id)
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

        return cash

    # ------------------------------------------------------------------
    # Category summary (dashboard cards)
    # ------------------------------------------------------------------

    @staticmethod
    def get_category_summary(user_id=None):
        """Get summary for each category.

        Manual-entry based: funds = cash balance, only REALIZED profit shown.
        """
        q = Fund.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        funds = q.all()

        # First pass: compute per-category values
        categories = []
        portfolio_value = ZERO
        for fund in funds:
            # Total Funds = deposits only (withdrawals excluded), consistent
            # with the Funds page display. fund.amount (net) is only used
            # internally by get_cash_balance_for_fund for cash calculation.
            total_funds = PortfolioCalculator.get_total_funds_for_fund(fund.id)

            realized_perf = PortfolioCalculator.get_realized_performance_for_fund(fund.id)
            realized_pnl = realized_perf['realized_pnl']

            transactions_summary = PortfolioCalculator.get_category_transactions_summary(fund.id)
            current_invested = _to_decimal(transactions_summary['current_invested'] or 0)

            cash = PortfolioCalculator.get_cash_balance_for_fund(fund.id)
            # category_value is the true current worth: what's invested + liquid cash.
            # This is used as total_value so both metrics are consistent.
            category_value = current_invested + cash
            portfolio_value += category_value

            # ROI: prefer total_funds as base; fallback to realized_cost_basis
            # when fund events are deleted (total_funds=0 but trades exist).
            roi_base = total_funds if total_funds != 0 else realized_perf['realized_cost_basis']
            realized_roi_percent, realized_roi_display = _roi_display(realized_pnl, roi_base)

            categories.append({
                'fund': fund,
                'total_funds': total_funds,
                'realized_pnl': realized_pnl,
                'current_invested': current_invested,
                'cash': cash,
                'category_value': category_value,
                'realized_roi_percent': realized_roi_percent,
                'realized_roi_display': realized_roi_display,
            })

        # Second pass: compute allocation based on portfolio value
        summary = []
        for cat in categories:
            allocation = (cat['category_value'] / abs(portfolio_value) * 100) if portfolio_value != 0 else ZERO

            summary.append({
                'category': cat['fund'].category,
                'amount': cat['total_funds'],
                'allocation': Decimal(str(allocation)),
                'id': cat['fund'].id,
                'realized_pnl': cat['realized_pnl'],
                'current_invested': cat['current_invested'],
                'total_value': cat['category_value'],
                'cash': cat['cash'],
                'realized_roi_percent': cat['realized_roi_percent'],
                'realized_roi_display': cat['realized_roi_display'],
            })

        return summary, portfolio_value

    # ------------------------------------------------------------------
    # Realized P&L helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_realized_pnl_for_fund(fund_id):
        """Sum realized P&L across all symbols for a fund."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(fund_id=fund_id)
            .distinct()
            .all()
        )
        realized = ZERO
        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            s = PortfolioCalculator.get_symbol_transactions_summary(fund_id, sym_norm)
            realized += _to_decimal(s['realized_pnl'])
        return realized

    @staticmethod
    def get_realized_performance_for_fund(fund_id):
        """Return realized P&L, cost basis, and proceeds for a fund."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(fund_id=fund_id)
            .distinct()
            .all()
        )

        realized_pnl = ZERO
        realized_cost_basis = ZERO
        realized_proceeds = ZERO

        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            s = PortfolioCalculator.get_symbol_transactions_summary(fund_id, sym_norm)
            realized_pnl += _to_decimal(s['realized_pnl'])
            realized_cost_basis += _to_decimal(s['realized_cost_basis'])
            realized_proceeds += _to_decimal(s['realized_proceeds'])

        return {
            'realized_pnl': realized_pnl,
            'realized_cost_basis': realized_cost_basis,
            'realized_proceeds': realized_proceeds,
        }

    # ------------------------------------------------------------------
    # Dashboard totals
    # ------------------------------------------------------------------

    @staticmethod
    def get_portfolio_dashboard_totals(user_id=None):
        """Dashboard totals: investment, cash, ROI."""
        q = Fund.query
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        funds = q.all()

        total_investment = ZERO
        total_cash = ZERO
        total_invested = ZERO
        total_realized_pnl = ZERO
        total_realized_cost_basis = ZERO

        for fund in funds:
            # Use deposits-only total, consistent with get_category_summary()
            total_investment += PortfolioCalculator.get_total_funds_for_fund(fund.id)

            total_cash += PortfolioCalculator.get_cash_balance_for_fund(fund.id)

            tx_summary = PortfolioCalculator.get_category_transactions_summary(fund.id)
            total_invested += _to_decimal(tx_summary['current_invested'] or 0)

            realized_perf = PortfolioCalculator.get_realized_performance_for_fund(fund.id)
            total_realized_pnl += realized_perf['realized_pnl']
            total_realized_cost_basis += realized_perf['realized_cost_basis']

        total_value = total_invested + total_cash

        # ROI: prefer total_investment (deposits only); fallback to cost basis
        # when fund events are deleted (total_investment=0 but trades exist).
        roi_base = total_investment if total_investment != 0 else total_realized_cost_basis
        realized_roi_percent, realized_roi_display = _roi_display(total_realized_pnl, roi_base)

        return {
            'total_investment': total_investment,
            'total_cash': total_cash,
            'total_realized_pnl': total_realized_pnl,
            'total_value': total_value,
            'realized_roi_percent': realized_roi_percent,
            'realized_roi_display': realized_roi_display,
        }

    # ------------------------------------------------------------------
    # Transaction summaries
    # ------------------------------------------------------------------

    @staticmethod
    def get_category_transactions_summary(fund_id):
        """Get aggregated transaction summary for a category."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(fund_id=fund_id)
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
            'current_invested': ZERO,
            'transaction_count': 0,
        }

        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            summary = PortfolioCalculator.get_symbol_transactions_summary(fund_id, sym_norm)
            for key in totals:
                if key == 'transaction_count':
                    totals[key] += int(summary[key])
                else:
                    totals[key] += _to_decimal(summary[key])

        # Weighted average cost across symbols (approximate)
        avg_cost = ZERO
        if totals['total_quantity_held'] > 0:
            weighted_cost = ZERO
            for (sym,) in symbols:
                sym_norm = PortfolioCalculator.normalize_symbol(sym)
                if not sym_norm:
                    continue
                s = PortfolioCalculator.get_symbol_transactions_summary(fund_id, sym_norm)
                weighted_cost += _to_decimal(s['average_cost']) * _to_decimal(s['total_quantity_held'])
            avg_cost = weighted_cost / totals['total_quantity_held']

        return {**totals, 'average_cost': avg_cost}

    @staticmethod
    def get_symbol_transactions_summary(fund_id, symbol):
        """Get aggregated transaction summary for a specific symbol."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        buy_first = case((Transaction.transaction_type == 'Buy', 0), else_=1)
        transactions = (
            Transaction.query.filter_by(fund_id=fund_id, symbol=symbol)
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

                # P&L = (sell_price - avg_cost) * qty - fees
                avg_cost = _safe_divide(running_cost, running_quantity)
                realized_pnl += (price - avg_cost) * quantity - fees
                realized_cost_basis += avg_cost * quantity

                # Reduce position at average-cost basis
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
            'current_invested': running_cost,
        }

    # ------------------------------------------------------------------
    # Recalculation (after add/edit/delete transaction)
    # ------------------------------------------------------------------

    @staticmethod
    def recalculate_all_averages_for_fund(fund_id):
        """Recalculate average costs for all transactions of a fund."""
        symbols = (
            Transaction.query.with_entities(Transaction.symbol)
            .filter_by(fund_id=fund_id)
            .distinct()
            .all()
        )

        updated = []
        for (sym,) in symbols:
            sym_norm = PortfolioCalculator.normalize_symbol(sym)
            if not sym_norm:
                continue
            updated.extend(PortfolioCalculator.recalculate_all_averages_for_symbol(fund_id, sym_norm))

        return updated

    @staticmethod
    def recalculate_all_averages_for_symbol(fund_id, symbol):
        """Recalculate average costs for all transactions of a (fund, symbol) pair."""
        symbol = PortfolioCalculator.normalize_symbol(symbol)
        buy_first = case((Transaction.transaction_type == 'Buy', 0), else_=1)
        transactions = (
            Transaction.query.filter_by(fund_id=fund_id, symbol=symbol)
            .order_by(func.date(Transaction.date).asc(), buy_first, Transaction.id.asc())
            .all()
        )

        running_quantity = ZERO
        running_cost = ZERO

        for transaction in transactions:
            transaction.calculate_total_cost()

            if transaction.transaction_type == 'Buy':
                cost = (_to_decimal(transaction.price) * _to_decimal(transaction.quantity)) + _to_decimal(transaction.fees)
                running_cost += cost
                running_quantity += _to_decimal(transaction.quantity)
                transaction.average_cost = _safe_divide(running_cost, running_quantity)

            elif transaction.transaction_type == 'Sell':
                sell_qty = _to_decimal(transaction.quantity)
                transaction.average_cost = _safe_divide(running_cost, running_quantity)
                running_quantity -= sell_qty
                running_cost -= transaction.average_cost * sell_qty

        return transactions
