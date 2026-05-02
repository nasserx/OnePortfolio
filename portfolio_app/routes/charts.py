"""Charts blueprint - Portfolio charts and visualizations.

The page exposes two performance heatmaps (portfolio-level and symbol-level)
plus the allocation donut. Both heatmaps share the same shape:

    [{name, abs_pnl, pnl, roi_percent, ...}]

with tile size = ``abs_pnl``, tile color sign = ``pnl``, and label = ``name``
plus ROI%. The shared aggregation helpers below collapse a long tail into a
single 'Others' bucket so the chart stays readable as the dataset grows.
"""

from typing import Any, Callable, Dict, List

from flask import Blueprint, render_template
from flask_login import login_required

from portfolio_app.services import get_services

charts_bp = Blueprint('charts', __name__)

# Aggregation thresholds. We render the top N rows individually and roll the
# tail into a single 'Others' bucket only when at least 2 rows would be
# hidden — otherwise just render every row as-is (one extra tile beats a
# misleading aggregate). Tuned per chart: portfolios are usually few,
# symbols are often many.
TOP_N_PORTFOLIOS = 5
TOP_N_SYMBOLS    = 8
OTHERS_LABEL     = 'Others'


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
    return {
        'name':        portfolio['name'],
        'allocation':  float(portfolio['allocation']),
        'pnl':         float(portfolio['realized_pnl']),
        'contributed': float(portfolio['total_contributed']),
        'roi_percent': float(portfolio['realized_roi_percent'] or 0),
    }


def _portfolio_others(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def _portfolio_rows(portfolio_summary: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort portfolios by book value, then collapse the long tail into 'Others'."""
    return _aggregate_with_others(
        portfolio_summary,
        sort_key=lambda p: p['book_value'],
        project=_portfolio_row,
        build_others=_portfolio_others,
        top_n=TOP_N_PORTFOLIOS,
    )


def _portfolio_treemap(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tile size = |P&L| (default) or |ROI%| (toggled by client).

    Both magnitudes are exposed so the treemap dataset is self-contained
    and the client just swaps the sizing key.
    """
    return [
        {
            'name':        r['name'],
            'abs_pnl':     abs(r['pnl']),
            'abs_roi':     abs(r['roi_percent']),
            'pnl':         r['pnl'],
            'roi_percent': r['roi_percent'],
        }
        for r in rows if r['pnl'] != 0
    ]


# ──────────────────────────────────────────────────────────────────────
# Symbol heatmap: tile size = |(portfolio, symbol) realized P&L + dividends|
# ──────────────────────────────────────────────────────────────────────

def _symbol_tile(*, name: str, portfolio_name: str, pnl: float, roi_percent: float) -> Dict[str, Any]:
    """Final treemap-tile shape for a (portfolio, symbol) row."""
    return {
        'name':           name,
        'portfolio_name': portfolio_name,
        'abs_pnl':        abs(pnl),
        'abs_roi':        abs(roi_percent),
        'pnl':            pnl,
        'roi_percent':    roi_percent,
    }


def _symbol_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project a get_user_symbol_performance row to the final tile shape."""
    return _symbol_tile(
        name           = item['symbol'],
        portfolio_name = item['portfolio_name'],
        pnl            = float(item['total_realized_pnl']),
        roi_percent    = float(item['roi_percent'] or 0),
    )


def _symbol_others(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a tail of (portfolio, symbol) rows into 'Others'.

    ROI is recomputed from the totals using ``roi_base`` (which may be
    realized cost basis or held cost basis depending on the row) — averaging
    ROIs across positions of different sizes would be misleading.
    """
    pnl  = sum(float(item['total_realized_pnl']) for item in tail)
    base = sum(float(item['roi_base']) for item in tail)
    roi  = (pnl / base * 100) if base else 0.0
    return _symbol_tile(
        name           = OTHERS_LABEL,
        portfolio_name = '',
        pnl            = pnl,
        roi_percent    = roi,
    )


def _symbol_treemap(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort symbols by |total realized P&L|, collapse the tail, drop zero-P&L rows."""
    tiles = _aggregate_with_others(
        symbol_performance,
        sort_key=lambda r: abs(float(r['total_realized_pnl'])),
        project=_symbol_row,
        build_others=_symbol_others,
        top_n=TOP_N_SYMBOLS,
    )
    return [t for t in tiles if t['pnl'] != 0]


# ──────────────────────────────────────────────────────────────────────
# Route
# ──────────────────────────────────────────────────────────────────────

@charts_bp.route('/charts')
@login_required
def charts() -> str:
    """Charts page - Portfolio visualizations."""
    svc = get_services()
    portfolio_summary, _ = svc.overview_service.get_portfolio_summary()
    symbol_performance   = svc.overview_service.get_symbol_performance()

    portfolios = _portfolio_rows(portfolio_summary)

    chart_data: Dict[str, Any] = {
        'donut_categories':  [r['name'] for r in portfolios],
        'donut_allocations': [r['allocation'] for r in portfolios],
        'portfolio_treemap': _portfolio_treemap(portfolios),
        'symbol_treemap':    _symbol_treemap(symbol_performance),
        'total_book_value':  float(sum(p['book_value'] for p in portfolio_summary)),
    }
    return render_template('charts.html', chart_data=chart_data)
