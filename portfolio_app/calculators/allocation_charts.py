"""Allocation chart data builders for the Overview page."""

from decimal import Decimal
from typing import Any, Dict, List

from portfolio_app.utils.decimal_utils import ZERO, safe_divide

ALLOCATION_TOP_N = 7
ALLOCATION_OTHERS_LABEL = 'Other Portfolios'


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
