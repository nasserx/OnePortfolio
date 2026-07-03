"""Charts blueprint - Portfolio charts and visualizations."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, render_template
from flask_login import login_required

from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.models import Dividend, Portfolio, Transaction
from portfolio_app.services import get_services
from portfolio_app.utils.decimal_utils import ZERO, safe_divide

charts_bp = Blueprint('charts', __name__)

# Aggregation thresholds. We render the top N rows individually and roll the
# tail into a single 'Others' bucket only when at least 2 rows would be
# hidden — otherwise just render every row as-is (one extra tile beats a
# misleading aggregate). Tuned per chart: portfolios are usually few,
# symbols are often many.
TOP_N_PORTFOLIOS = 5
TOP_N_SYMBOLS    = 8
OTHERS_LABEL     = 'Others'
ALLOCATION_TOP_N = 7
ALLOCATION_OTHERS_LABEL = 'Other Portfolios'
PORTFOLIO_LEADERBOARD_LIMIT = 7
PORTFOLIO_LEADERBOARD_TOP_N = 7
ASSET_LEADERBOARD_LIMIT = 7
ASSET_LEADERBOARD_TOP_N = 7
ASSET_OTHERS_LABEL = 'Other Assets'
MONTH_LABELS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]


# ──────────────────────────────────────────────────────────────────────
# Generic aggregation: "top N + Others" with a domain-specific tail builder
# ──────────────────────────────────────────────────────────────────────

def _aggregate_with_others(
    rows: List[Dict[str, Any]],
    *,
    sort_key: Callable[[Dict[str, Any]], Any],
    project: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_others: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
    top_n: int,
) -> List[Dict[str, Any]]:
    """Sort rows, project each one, and collapse the tail into 'Others'.

    The tail is only aggregated when it would replace at least 2 rows; if
    only one row would fall under 'Others', it's kept as itself.
    """
    ranked = sorted(rows, key=sort_key, reverse=True)
    if len(ranked) >= top_n + 2:
        return [project(r) for r in ranked[:top_n]] + [build_others(ranked[top_n:])]
    return [project(r) for r in ranked]


# ──────────────────────────────────────────────────────────────────────
# Portfolio heatmap: tile size = |portfolio realized P&L|
# ──────────────────────────────────────────────────────────────────────

def _portfolio_row(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Project a portfolio_summary item to the shape consumed by the templates."""
    realized_pnl = Decimal(str(portfolio['realized_pnl']))
    income = Decimal(str(portfolio.get('total_income', ZERO)))
    return_percent = Decimal(str(portfolio.get('return_percent') or ZERO))
    return {
        'name':        portfolio['name'],
        'allocation':  float(portfolio['allocation']),
        'pnl':         float(realized_pnl),
        'income':      float(income),
        'contributed': float(portfolio['total_contributed']),
        'return_percent': float(return_percent),
    }


def _portfolio_others(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a tail of portfolios into a single 'Others' row.

    Return is recomputed from the totals, not averaged across different-sized
    portfolios.
    """
    pnl = sum((Decimal(str(p['realized_pnl'])) for p in tail), ZERO)
    income = sum((Decimal(str(p.get('total_income', ZERO))) for p in tail), ZERO)
    contributed = sum((Decimal(str(p['total_contributed'])) for p in tail), ZERO)
    return_percent = safe_divide(pnl + income, contributed) * Decimal('100') if contributed != ZERO else ZERO
    return {
        'name':        OTHERS_LABEL,
        'allocation':  float(sum((Decimal(str(p['allocation'])) for p in tail), ZERO)),
        'pnl':         float(pnl),
        'income':      float(income),
        'contributed': float(contributed),
        'return_percent': float(return_percent),
    }


def _portfolio_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort portfolios by book value, then collapse the long tail into 'Others'."""
    return _aggregate_with_others(
        portfolio_summary,
        sort_key=lambda p: p['book_value'],
        project=_portfolio_row,
        build_others=_portfolio_others,
        top_n=TOP_N_PORTFOLIOS,
    )


def _allocation_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Portfolio allocation rows: top 7 by book value + Other Portfolios."""
    meaningful = [
        p for p in portfolio_summary
        if Decimal(str(p['book_value'])) > ZERO
    ]
    total_book_value = sum((Decimal(str(p['book_value'])) for p in meaningful), ZERO)
    ranked = sorted(
        meaningful,
        key=lambda p: Decimal(str(p['book_value'])),
        reverse=True,
    )

    if len(ranked) <= ALLOCATION_TOP_N:
        selected = ranked
        other_book_value = ZERO
    else:
        selected = ranked[:ALLOCATION_TOP_N]
        other_book_value = sum(
            (Decimal(str(p['book_value'])) for p in ranked[ALLOCATION_TOP_N:]),
            ZERO,
        )

    rows = []
    for portfolio in selected:
        book_value = Decimal(str(portfolio['book_value']))
        allocation = (
            safe_divide(book_value, abs(total_book_value)) * Decimal('100')
            if total_book_value != ZERO else ZERO
        )
        rows.append({
            'name': portfolio['name'],
            'book_value': float(book_value),
            'allocation': float(allocation),
        })

    if other_book_value != ZERO or len(ranked) > ALLOCATION_TOP_N:
        allocation = (
            safe_divide(other_book_value, abs(total_book_value)) * Decimal('100')
            if total_book_value != ZERO else ZERO
        )
        rows.append({
            'name': ALLOCATION_OTHERS_LABEL,
            'book_value': float(other_book_value),
            'allocation': float(allocation),
        })

    return rows


def _capital_allocation_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Portfolio allocation rows by Total Capital (deposits - withdrawals)."""
    meaningful = [
        p for p in portfolio_summary
        if Decimal(str(p.get('total_capital', ZERO))) > ZERO
    ]
    total_capital = sum(
        (Decimal(str(p.get('total_capital', ZERO))) for p in meaningful),
        ZERO,
    )
    ranked = sorted(
        meaningful,
        key=lambda p: Decimal(str(p.get('total_capital', ZERO))),
        reverse=True,
    )

    if len(ranked) <= ALLOCATION_TOP_N:
        selected = ranked
        other_capital = ZERO
    else:
        selected = ranked[:ALLOCATION_TOP_N]
        other_capital = sum(
            (Decimal(str(p.get('total_capital', ZERO))) for p in ranked[ALLOCATION_TOP_N:]),
            ZERO,
        )

    rows = []
    for portfolio in selected:
        capital = Decimal(str(portfolio.get('total_capital', ZERO)))
        allocation = (
            safe_divide(capital, total_capital) * Decimal('100')
            if total_capital != ZERO else ZERO
        )
        rows.append({
            'name': portfolio['name'],
            'capital': float(capital),
            'allocation': float(allocation),
        })

    if other_capital != ZERO or len(ranked) > ALLOCATION_TOP_N:
        allocation = (
            safe_divide(other_capital, total_capital) * Decimal('100')
            if total_capital != ZERO else ZERO
        )
        rows.append({
            'name': ALLOCATION_OTHERS_LABEL,
            'capital': float(other_capital),
            'allocation': float(allocation),
        })

    return rows


def build_allocation_chart_data(portfolio_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the two portfolio allocation doughnut datasets."""
    allocation_rows = _allocation_rows(portfolio_summary)
    capital_rows = _capital_allocation_rows(portfolio_summary)

    return {
        'book_value_chart': {
            'categories':  [r['name'] for r in allocation_rows],
            'allocations': [r['allocation'] for r in allocation_rows],
            'values':      [r['book_value'] for r in allocation_rows],
            'total':       float(sum((Decimal(str(r['book_value'])) for r in allocation_rows), ZERO)),
            'grouped':     len([p for p in portfolio_summary if Decimal(str(p['book_value'])) > ZERO]) > ALLOCATION_TOP_N,
        },
        'capital_chart': {
            'categories':  [r['name'] for r in capital_rows],
            'allocations': [r['allocation'] for r in capital_rows],
            'values':      [r['capital'] for r in capital_rows],
            'total':       float(sum((Decimal(str(r['capital'])) for r in capital_rows), ZERO)),
            'grouped':     len([p for p in portfolio_summary if Decimal(str(p.get('total_capital', ZERO))) > ZERO]) > ALLOCATION_TOP_N,
        },
    }


def _portfolio_performance_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unaggregated portfolio performance rows for ranked bars."""
    return [
        {
            'name': portfolio['name'],
            'realized_pnl': float(portfolio['realized_pnl']),
            'pnl': float(portfolio['realized_pnl']),
            'return_amount': float(portfolio['return_amount']),
            'return_percent': float(portfolio['return_percent'] or 0),
            'income': float(portfolio.get('total_income', ZERO)),
            'book_value': float(portfolio['book_value']),
            'total_contributed': float(portfolio['total_contributed']),
            'is_other': False,
        }
        for portfolio in portfolio_summary
    ]


def _sort_performance_rows(
    rows: List[Dict[str, Any]],
    sort_keys: List[str],
) -> List[Dict[str, Any]]:
    """Sort rows by performance keys, highest first."""
    return sorted(
        rows,
        key=lambda r: tuple(Decimal(str(r.get(key, ZERO))) for key in sort_keys),
        reverse=True,
    )


def _portfolio_leaderboard_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Top portfolios by book value plus an aggregated Other Portfolios row.

    The comparison dashboard keeps portfolio row selection stable by using
    book value, while each metric track still scales from the rendered values.
    """
    ranked = sorted(
        rows,
        key=lambda r: Decimal(str(r.get('book_value', ZERO))),
        reverse=True,
    )
    if len(ranked) <= PORTFOLIO_LEADERBOARD_LIMIT:
        return [row.copy() for row in ranked]

    top = [row.copy() for row in ranked[:PORTFOLIO_LEADERBOARD_TOP_N]]
    tail = ranked[PORTFOLIO_LEADERBOARD_TOP_N:]
    pnl = sum((Decimal(str(row['realized_pnl'])) for row in tail), ZERO)
    income = sum((Decimal(str(row.get('income', ZERO))) for row in tail), ZERO)
    book_value = sum((Decimal(str(row['book_value'])) for row in tail), ZERO)
    contributed = sum((Decimal(str(row.get('total_contributed', ZERO))) for row in tail), ZERO)
    return_percent = (
        safe_divide(pnl + income, contributed) * Decimal('100')
        if contributed != ZERO else None
    )
    top.append({
        'name': ALLOCATION_OTHERS_LABEL,
        'realized_pnl': float(pnl),
        'pnl': float(pnl),
        'return_percent': float(return_percent) if return_percent is not None else None,
        'income': float(income),
        'book_value': float(book_value),
        'total_contributed': float(contributed),
        'is_other': True,
    })
    return top


def _asset_leaderboard_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Top assets by performance magnitude plus an aggregated Other Assets row."""
    ranked = sorted(
        rows,
        key=lambda r: (
            abs(Decimal(str(r.get('realized_pnl', ZERO)))),
            abs(Decimal(str(r.get('return_percent') or ZERO))),
            Decimal(str(r.get('income', ZERO))),
        ),
        reverse=True,
    )
    if len(ranked) <= ASSET_LEADERBOARD_LIMIT:
        return [row.copy() for row in ranked]

    top = [row.copy() for row in ranked[:ASSET_LEADERBOARD_TOP_N]]
    tail = ranked[ASSET_LEADERBOARD_TOP_N:]
    pnl = sum((Decimal(str(row['realized_pnl'])) for row in tail), ZERO)
    income = sum((Decimal(str(row.get('income', ZERO))) for row in tail), ZERO)
    buy_cost = sum((Decimal(str(row.get('buy_cost', ZERO))) for row in tail), ZERO)
    return_percent = (
        safe_divide(pnl + income, buy_cost) * Decimal('100')
        if buy_cost != ZERO else None
    )
    top.append({
        'name': ASSET_OTHERS_LABEL,
        'portfolio_names': ['Multiple'],
        'portfolio_count': len(tail),
        'realized_pnl': float(pnl),
        'abs_pnl': float(abs(pnl)),
        'abs_return': float(abs(return_percent)) if return_percent is not None else 0.0,
        'pnl': float(pnl),
        'return_percent': float(return_percent) if return_percent is not None else None,
        'income': float(income),
        'buy_cost': float(buy_cost),
        'is_other': True,
    })
    return top


def _portfolio_treemap(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tile size = |P&L| (default) or |Return%| (toggled by client).

    Both magnitudes are exposed so the treemap dataset is self-contained
    and the client just swaps the sizing key.
    """
    return [
        {
            'name':        r['name'],
            'abs_pnl':     abs(r['pnl']),
            'abs_return':  abs(r['return_percent']),
            'pnl':         r['pnl'],
            'return_percent': r['return_percent'],
        }
        for r in rows if r['pnl'] != 0
    ]


# ──────────────────────────────────────────────────────────────────────
# Symbol heatmap: tile size = |symbol realized P&L + dividends|
# ──────────────────────────────────────────────────────────────────────

def _symbol_tile(
    *,
    name: str,
    portfolio_names: List[str],
    pnl: float,
    return_percent: Optional[float],
    buy_cost: float = 0.0,
    income: float = 0.0,
) -> Dict[str, Any]:
    """Final treemap-tile shape for a user-level symbol row."""
    return {
        'name':           name,
        'portfolio_names': portfolio_names,
        'portfolio_count': len(portfolio_names),
        'realized_pnl':    pnl,
        'abs_pnl':        abs(pnl),
        'abs_return':     abs(return_percent) if return_percent is not None else 0.0,
        'pnl':            pnl,
        'return_percent':  return_percent,
        'income':          income,
        'return_amount':   pnl + income,
        'buy_cost':        buy_cost,
        'is_other':        False,
    }


def _symbol_rows(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate per-(portfolio, symbol) rows into one row per symbol.

    Return is recomputed from summed P&L and summed total buy cost. We intentionally
    do not average per-portfolio return values because that overweights small
    positions and understates large ones.
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for item in symbol_performance:
        symbol = item['symbol']
        row = grouped.setdefault(symbol, {
            'symbol': symbol,
            'realized_pnl': ZERO,
            'return_amount': ZERO,
            'total_buy_cost': ZERO,
            'income': ZERO,
            'portfolio_names': [],
            '_portfolio_ids': set(),
        })

        trading_pnl = Decimal(str(item.get('realized_pnl', ZERO)))
        income = Decimal(str(item.get('total_income', ZERO)))
        row['realized_pnl'] += trading_pnl
        row['return_amount'] += trading_pnl + income
        row['total_buy_cost'] += Decimal(str(item['total_buy_cost']))
        row['income'] += income

        portfolio_id = item.get('portfolio_id')
        if portfolio_id not in row['_portfolio_ids']:
            row['_portfolio_ids'].add(portfolio_id)
            row['portfolio_names'].append(item['portfolio_name'])

    rows = []
    for row in grouped.values():
        return_percent = (
            safe_divide(row['return_amount'], row['total_buy_cost']) * Decimal('100')
            if row['total_buy_cost'] != ZERO else None
        )
        rows.append({
            'symbol': row['symbol'],
            'realized_pnl': row['realized_pnl'],
            'return_amount': row['return_amount'],
            'total_buy_cost': row['total_buy_cost'],
            'income': row['income'],
            'return_percent': return_percent,
            'portfolio_names': row['portfolio_names'],
        })
    return rows


def _symbol_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project an aggregated symbol-performance row to the final tile shape."""
    return _symbol_tile(
        name           = item['symbol'],
        portfolio_names= item['portfolio_names'],
        pnl            = float(item['realized_pnl']),
        return_percent = float(item['return_percent']) if item['return_percent'] is not None else None,
        buy_cost       = float(item.get('total_buy_cost', ZERO)),
        income         = float(item.get('income', ZERO)),
    ) | {'return_amount': float(item.get('return_amount', ZERO))}


def _symbol_others(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a tail of (portfolio, symbol) rows into 'Others'.

    Return is recomputed from total P&L over total buy cost. Averaging returns
    across positions of different sizes would be misleading.
    """
    pnl = sum((Decimal(str(item['realized_pnl'])) for item in tail), ZERO)
    income = sum((Decimal(str(item.get('income', ZERO))) for item in tail), ZERO)
    base = sum((Decimal(str(item['total_buy_cost'])) for item in tail), ZERO)
    return_percent = safe_divide(pnl + income, base) * Decimal('100') if base != ZERO else None
    return _symbol_tile(
        name           = OTHERS_LABEL,
        portfolio_names= [],
        pnl            = float(pnl),
        return_percent = float(return_percent) if return_percent is not None else None,
        buy_cost       = float(base),
        income         = float(income),
    )


def _symbol_treemap(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort user-level symbols by |total P&L|, collapse the tail, drop zero-P&L rows."""
    symbol_rows = _symbol_rows(symbol_performance)
    tiles = _aggregate_with_others(
        symbol_rows,
        sort_key=lambda r: abs(Decimal(str(r['return_amount']))),
        project=_symbol_row,
        build_others=_symbol_others,
        top_n=TOP_N_SYMBOLS,
    )
    return [t for t in tiles if t['pnl'] != 0 or t.get('income', 0) != 0]


def _asset_performance_rows(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unaggregated user-level asset performance rows for ranked bars."""
    return [
        _symbol_row(item)
        for item in _symbol_rows(symbol_performance)
    ]


def _meaningful_month(monthly: List[Decimal], *, best: bool) -> Optional[Dict[str, Any]]:
    """Return a positive best month or negative worst month for display."""
    if not monthly:
        return None

    idx = max(range(len(monthly)), key=lambda i: monthly[i]) if best else min(range(len(monthly)), key=lambda i: monthly[i])
    value = monthly[idx]
    if best and value <= ZERO:
        return None
    if not best and value >= ZERO:
        return None
    return {'label': MONTH_LABELS[idx], 'value': float(value)}


def _meaningful_asset(rows: List[Dict[str, Any]], *, best: bool) -> Optional[Dict[str, Any]]:
    """Return a positive best asset or negative worst asset for display."""
    if not rows:
        return None

    ranked = sorted(
        rows,
        key=lambda row: Decimal(str(row.get('realized_pnl', ZERO))),
        reverse=best,
    )
    asset = ranked[0]
    value = Decimal(str(asset.get('realized_pnl', ZERO)))
    if best and value <= ZERO:
        return None
    if not best and value >= ZERO:
        return None
    return {'label': asset['name'], 'value': float(value)}


def _portfolio_stats(
    portfolio_summary: List[Dict[str, Any]],
    trend: Dict[str, Any],
) -> Dict[str, Any]:
    """Portfolio performance stat cards from existing summary/trend values."""
    realized_pnl = sum(
        (Decimal(str(row.get('realized_pnl', ZERO))) for row in portfolio_summary),
        ZERO,
    )
    contributed = sum(
        (Decimal(str(row.get('total_contributed', ZERO))) for row in portfolio_summary),
        ZERO,
    )
    income = sum(
        (Decimal(str(row.get('total_income', ZERO))) for row in portfolio_summary),
        ZERO,
    )
    return_percent = (
        safe_divide(realized_pnl + income, contributed) * Decimal('100')
        if contributed != ZERO else None
    )
    trend_stats = trend.get('stats', {})
    return {
        'realized_pnl': float(realized_pnl),
        'return_percent': float(return_percent) if return_percent is not None else None,
        'income': float(income),
        'best_month': trend_stats.get('best_month'),
        'worst_month': trend_stats.get('worst_month'),
    }


def _asset_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Asset performance stat cards from user-level asset rows."""
    realized_pnl = sum(
        (Decimal(str(row.get('realized_pnl', ZERO))) for row in rows),
        ZERO,
    )
    income = sum(
        (Decimal(str(row.get('income', ZERO))) for row in rows),
        ZERO,
    )
    buy_cost = sum(
        (Decimal(str(row.get('buy_cost', ZERO))) for row in rows),
        ZERO,
    )
    return_percent = (
        safe_divide(realized_pnl + income, buy_cost) * Decimal('100')
        if buy_cost != ZERO else None
    )
    return {
        'realized_pnl': float(realized_pnl),
        'return_percent': float(return_percent) if return_percent is not None else None,
        'income': float(income),
        'best_asset': _meaningful_asset(rows, best=True),
        'worst_asset': _meaningful_asset(rows, best=False),
    }


def _monthly_performance_trend(
    portfolio_summary: List[Dict[str, Any]],
    *,
    user_id: int,
    year: int,
) -> Dict[str, Any]:
    """Build a current-year cumulative realized P&L and return trend."""
    monthly_realized_pnl = [ZERO for _ in range(12)]
    monthly_income = [ZERO for _ in range(12)]

    sell_rows = (
        Transaction.query
        .join(Portfolio, Transaction.portfolio_id == Portfolio.id)
        .filter(
            Portfolio.user_id == user_id,
            Transaction.transaction_type == 'Sell',
        )
        .all()
    )
    for transaction in sell_rows:
        if not transaction.date or transaction.date.year != year:
            continue
        monthly_realized_pnl[transaction.date.month - 1] += PortfolioCalculator._to_decimal(transaction.net_pnl or 0)

    income_rows = (
        Dividend.query
        .join(Portfolio, Dividend.portfolio_id == Portfolio.id)
        .filter(Portfolio.user_id == user_id)
        .all()
    )
    for income in income_rows:
        if not income.date or income.date.year != year:
            continue
        amount = PortfolioCalculator._to_decimal(income.amount)
        monthly_income[income.date.month - 1] += amount

    contribution_base = sum(
        (Decimal(str(p.get('total_contributed', ZERO))) for p in portfolio_summary),
        ZERO,
    )
    cumulative = []
    returns = []
    running_realized = ZERO
    running_income = ZERO
    for idx, amount in enumerate(monthly_realized_pnl):
        running_realized += amount
        running_income += monthly_income[idx]
        cumulative.append(float(running_realized))
        return_amount = running_realized + running_income
        returns.append(float(safe_divide(return_amount, contribution_base) * Decimal('100')) if contribution_base else 0.0)

    ytd_pnl = sum(monthly_realized_pnl, ZERO)
    ytd_income = sum(monthly_income, ZERO)
    ytd_return = safe_divide(ytd_pnl + ytd_income, contribution_base) * Decimal('100') if contribution_base else ZERO

    return {
        'year': year,
        'months': MONTH_LABELS,
        'realized_pnl': cumulative,
        'return_percent': returns,
        'income': [float(value) for value in monthly_income],
        'stats': {
            'ytd_realized_pnl': float(ytd_pnl),
            'ytd_return': float(ytd_return),
            'ytd_income': float(ytd_income),
            'best_month': _meaningful_month(monthly_realized_pnl, best=True),
            'worst_month': _meaningful_month(monthly_realized_pnl, best=False),
        },
    }


def _asset_monthly_performance_trend(
    rows: List[Dict[str, Any]],
    *,
    user_id: int,
    year: int,
) -> Dict[str, Any]:
    """Build a current-year cumulative asset performance trend for display."""
    monthly_realized_pnl = [ZERO for _ in range(12)]
    monthly_income = [ZERO for _ in range(12)]

    sell_rows = (
        Transaction.query
        .join(Portfolio, Transaction.portfolio_id == Portfolio.id)
        .filter(
            Portfolio.user_id == user_id,
            Transaction.transaction_type == 'Sell',
        )
        .all()
    )
    for transaction in sell_rows:
        if not transaction.date or transaction.date.year != year:
            continue
        monthly_realized_pnl[transaction.date.month - 1] += PortfolioCalculator._to_decimal(transaction.net_pnl or 0)

    income_rows = (
        Dividend.query
        .join(Portfolio, Dividend.portfolio_id == Portfolio.id)
        .filter(Portfolio.user_id == user_id)
        .all()
    )
    for income in income_rows:
        if not income.date or income.date.year != year:
            continue
        amount = PortfolioCalculator._to_decimal(income.amount)
        monthly_income[income.date.month - 1] += amount

    buy_cost = sum(
        (Decimal(str(row.get('buy_cost', ZERO))) for row in rows),
        ZERO,
    )
    cumulative = []
    returns = []
    running_realized = ZERO
    running_income = ZERO
    for idx, amount in enumerate(monthly_realized_pnl):
        running_realized += amount
        running_income += monthly_income[idx]
        cumulative.append(float(running_realized))
        return_amount = running_realized + running_income
        returns.append(float(safe_divide(return_amount, buy_cost) * Decimal('100')) if buy_cost else 0.0)

    ytd_pnl = sum(monthly_realized_pnl, ZERO)
    ytd_income = sum(monthly_income, ZERO)
    ytd_return = safe_divide(ytd_pnl + ytd_income, buy_cost) * Decimal('100') if buy_cost else ZERO

    return {
        'year': year,
        'months': MONTH_LABELS,
        'realized_pnl': cumulative,
        'return_percent': returns,
        'income': [float(value) for value in monthly_income],
        'stats': {
            'ytd_realized_pnl': float(ytd_pnl),
            'ytd_return': float(ytd_return),
            'ytd_income': float(ytd_income),
            'best_month': _meaningful_month(monthly_realized_pnl, best=True),
            'worst_month': _meaningful_month(monthly_realized_pnl, best=False),
        },
    }


# ──────────────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────────────

@charts_bp.route('/charts')
@login_required
def charts() -> str:
    """Charts page - Portfolio visualizations."""
    svc = get_services()
    portfolio_summary, _ = svc.overview_service.get_portfolio_summary()
    return render_template(
        'charts.html',
        chart_data=build_allocation_chart_data(portfolio_summary),
    )
