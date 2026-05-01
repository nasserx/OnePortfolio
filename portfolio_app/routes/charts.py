"""Charts blueprint - Portfolio charts and visualizations."""

from typing import Any, Dict, List

from flask import Blueprint, render_template
from flask_login import login_required

from portfolio_app.services import get_services

charts_bp = Blueprint('charts', __name__)

# Show the top N portfolios individually; aggregate the tail into a single
# "Others" row only when at least 2 portfolios would be hidden — otherwise
# just render every portfolio as-is (one extra row beats a misleading bucket).
TOP_N = 5
OTHERS_LABEL = 'Others'


def _to_row(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Project a portfolio_summary item to the shape consumed by the templates."""
    return {
        'name':        portfolio['name'],
        'allocation':  float(portfolio['allocation']),
        'pnl':         float(portfolio['realized_pnl']),
        'contributed': float(portfolio['total_contributed']),
        'roi_percent': float(portfolio['realized_roi_percent'] or 0),
    }


def _others_row(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a tail of portfolios into a single 'Others' row.

    ROI is recomputed from the totals (sum of P&L over sum of contributions),
    not averaged — averaging ROIs across different-sized portfolios is meaningless.
    """
    pnl         = sum(float(p['realized_pnl']) for p in tail)
    contributed = sum(float(p['total_contributed']) for p in tail)
    roi         = (pnl / contributed * 100) if contributed else 0.0
    return {
        'name':        OTHERS_LABEL,
        'allocation':  sum(float(p['allocation']) for p in tail),
        'pnl':         pnl,
        'contributed': contributed,
        'roi_percent': roi,
    }


def _aggregate_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort portfolios by book value, then collapse the long tail into 'Others'."""
    ranked = sorted(portfolio_summary, key=lambda p: p['book_value'], reverse=True)
    if len(ranked) >= TOP_N + 2:
        return [_to_row(p) for p in ranked[:TOP_N]] + [_others_row(ranked[TOP_N:])]
    return [_to_row(p) for p in ranked]


def _treemap_data(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Performance heatmap: tile size = |P&L|, sign drives color, ROI is the label.

    Portfolios with no realized P&L are excluded — they have no performance
    story to tell, and a zero-sized tile would render nothing anyway.
    """
    return [
        {'name': r['name'], 'abs_pnl': abs(r['pnl']), 'pnl': r['pnl'], 'roi_percent': r['roi_percent']}
        for r in rows if r['pnl'] != 0
    ]


@charts_bp.route('/charts')
@login_required
def charts() -> str:
    """Charts page - Portfolio visualizations."""
    svc = get_services()
    portfolio_summary, _ = svc.overview_service.get_portfolio_summary()
    rows = _aggregate_rows(portfolio_summary)

    chart_data: Dict[str, Any] = {
        'donut_categories':  [r['name'] for r in rows],
        'donut_allocations': [r['allocation'] for r in rows],
        'treemap':           _treemap_data(rows),
        'total_book_value':  float(sum(p['book_value'] for p in portfolio_summary)),
    }
    return render_template('charts.html', chart_data=chart_data)
