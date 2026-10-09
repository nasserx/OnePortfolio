"""Allocation chart data builders for the Overview page."""

from decimal import Decimal
from math import isfinite
from typing import Any, Dict, List

from portfolio_app.utils.decimal_utils import ZERO
from portfolio_app.utils.financial_arithmetic import exact_sum, financial_percent

# A doughnut stops being readable well before it runs out of distinguishable
# colours: past four slices the small ones become unlabelable slivers. The
# ranked remainder is rolled into a single "Other Portfolios" wedge, and the
# full per-portfolio detail is still one row away in the summary table below.
ALLOCATION_TOP_N = 4
ALLOCATION_OTHERS_LABEL = 'Other Portfolios'


def _allocation_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Portfolio allocation rows: top N by book value + Other Portfolios."""
    meaningful = [
        p for p in portfolio_summary
        if Decimal(str(p['book_value'])) > ZERO
    ]
    total_book_value = exact_sum(p['book_value'] for p in meaningful)
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
        other_book_value = exact_sum(p['book_value'] for p in ranked[ALLOCATION_TOP_N:])

    rows = []
    for portfolio in selected:
        book_value = Decimal(str(portfolio['book_value']))
        allocation = (
            financial_percent(book_value, total_book_value.copy_abs())
            if total_book_value != ZERO else ZERO
        )
        rows.append({
            'name': portfolio['name'],
            'book_value': book_value,
            'allocation': allocation,
        })

    if other_book_value != ZERO or len(ranked) > ALLOCATION_TOP_N:
        allocation = (
            financial_percent(other_book_value, total_book_value.copy_abs())
            if total_book_value != ZERO else ZERO
        )
        rows.append({
            'name': ALLOCATION_OTHERS_LABEL,
            'book_value': other_book_value,
            'allocation': allocation,
        })

    return rows


def _contribution_allocation_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Portfolio allocation rows by positive Net Contributions."""
    meaningful = [
        p for p in portfolio_summary
        if Decimal(str(p.get('net_contributions', ZERO))) > ZERO
    ]
    positive_contribution_total = exact_sum(p.get('net_contributions', ZERO) for p in meaningful)
    ranked = sorted(
        meaningful,
        key=lambda p: Decimal(str(p.get('net_contributions', ZERO))),
        reverse=True,
    )

    if len(ranked) <= ALLOCATION_TOP_N:
        selected = ranked
        other_contributions = ZERO
    else:
        selected = ranked[:ALLOCATION_TOP_N]
        other_contributions = exact_sum(p.get('net_contributions', ZERO) for p in ranked[ALLOCATION_TOP_N:])

    rows = []
    for portfolio in selected:
        net_contributions = Decimal(str(portfolio.get('net_contributions', ZERO)))
        allocation = (
            financial_percent(net_contributions, positive_contribution_total)
            if positive_contribution_total != ZERO else ZERO
        )
        rows.append({
            'name': portfolio['name'],
            'net_contributions': net_contributions,
            'allocation': allocation,
        })

    if other_contributions != ZERO or len(ranked) > ALLOCATION_TOP_N:
        allocation = (
            financial_percent(other_contributions, positive_contribution_total)
            if positive_contribution_total != ZERO else ZERO
        )
        rows.append({
            'name': ALLOCATION_OTHERS_LABEL,
            'net_contributions': other_contributions,
            'allocation': allocation,
        })

    return rows


def _chart_dataset(rows, value_key, grouped):
    """Convert only the completed Decimal calculation, never sum float rows.

    Canvas numbers are presentational. If conversion overflows or erases a
    positive value, omit this chart rather than emitting infinity/false zero.
    Canonical metrics and the portfolio table remain independent and exact.
    """
    total = exact_sum(row[value_key] for row in rows)
    decimals = [total, *(row[value_key] for row in rows), *(row['allocation'] for row in rows)]
    converted = [float(value) for value in decimals]
    if any(not isfinite(number) or (value != ZERO and number == 0)
           for value, number in zip(decimals, converted)):
        return {'categories': [], 'allocations': [], 'values': [], 'total': None,
                'grouped': grouped, 'unavailable': True}
    size = len(rows)
    return {'categories': [row['name'] for row in rows],
            'values': converted[1:1 + size], 'allocations': converted[1 + size:],
            'total': converted[0], 'grouped': grouped}


def build_allocation_chart_data(portfolio_summary: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the two portfolio allocation doughnut datasets."""
    allocation_rows = _allocation_rows(portfolio_summary)
    contribution_rows = _contribution_allocation_rows(portfolio_summary)

    return {
        'book_value_chart': _chart_dataset(allocation_rows, 'book_value',
            len([p for p in portfolio_summary if Decimal(str(p['book_value'])) > ZERO]) > ALLOCATION_TOP_N),
        'net_contributions_chart': _chart_dataset(contribution_rows, 'net_contributions',
            len([p for p in portfolio_summary if Decimal(str(p.get('net_contributions', ZERO))) > ZERO]) > ALLOCATION_TOP_N),
    }
