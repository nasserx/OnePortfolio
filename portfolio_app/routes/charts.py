"""Charts blueprint - Portfolio charts and visualizations.

The page exposes two performance heatmaps (portfolio-level and symbol-level)
plus the allocation donut. Both heatmaps share the same shape:

    [{name, abs_pnl, pnl, roi_percent, ...}]

with tile size = ``abs_pnl``, tile color sign = ``pnl``, and label = ``name``
plus ROI%. The shared aggregation helpers below collapse a long tail into a
single 'Others' bucket so the chart stays readable as the dataset grows.
"""

from decimal import Decimal
from typing import Any, Callable, Dict, List

from flask import Blueprint, render_template
from flask_login import login_required

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
    pnl = sum((Decimal(str(p['realized_pnl'])) for p in tail), ZERO)
    contributed = sum((Decimal(str(p['total_contributed'])) for p in tail), ZERO)
    roi = safe_divide(pnl, contributed) * Decimal('100') if contributed != ZERO else ZERO
    return {
        'name':        OTHERS_LABEL,
        'allocation':  float(sum((Decimal(str(p['allocation'])) for p in tail), ZERO)),
        'pnl':         float(pnl),
        'contributed': float(contributed),
        'roi_percent': float(roi),
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
# Symbol heatmap: tile size = |symbol realized P&L + dividends|
# ──────────────────────────────────────────────────────────────────────

def _symbol_tile(*, name: str, portfolio_names: List[str], pnl: float, roi_percent: float) -> Dict[str, Any]:
    """Final treemap-tile shape for a user-level symbol row."""
    return {
        'name':           name,
        'portfolio_names': portfolio_names,
        'portfolio_count': len(portfolio_names),
        'abs_pnl':        abs(pnl),
        'abs_roi':        abs(roi_percent),
        'pnl':            pnl,
        'roi_percent':    roi_percent,
    }


def _symbol_rows(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate per-(portfolio, symbol) rows into one row per symbol.

    ROI is recomputed from summed P&L and summed total buy cost. We intentionally
    do not average per-portfolio ROI values because that overweights small
    positions and understates large ones.
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for item in symbol_performance:
        symbol = item['symbol']
        row = grouped.setdefault(symbol, {
            'symbol': symbol,
            'total_realized_pnl': ZERO,
            'total_buy_cost': ZERO,
            'portfolio_names': [],
            '_portfolio_ids': set(),
        })

        row['total_realized_pnl'] += Decimal(str(item['total_realized_pnl']))
        row['total_buy_cost'] += Decimal(str(item['total_buy_cost']))

        portfolio_id = item.get('portfolio_id')
        if portfolio_id not in row['_portfolio_ids']:
            row['_portfolio_ids'].add(portfolio_id)
            row['portfolio_names'].append(item['portfolio_name'])

    rows = []
    for row in grouped.values():
        roi = (
            safe_divide(row['total_realized_pnl'], row['total_buy_cost']) * Decimal('100')
            if row['total_buy_cost'] != ZERO else ZERO
        )
        rows.append({
            'symbol': row['symbol'],
            'total_realized_pnl': row['total_realized_pnl'],
            'total_buy_cost': row['total_buy_cost'],
            'roi_percent': roi,
            'portfolio_names': row['portfolio_names'],
        })
    return rows


def _symbol_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project an aggregated symbol-performance row to the final tile shape."""
    return _symbol_tile(
        name           = item['symbol'],
        portfolio_names= item['portfolio_names'],
        pnl            = float(item['total_realized_pnl']),
        roi_percent    = float(item['roi_percent'] or 0),
    )


def _symbol_others(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a tail of (portfolio, symbol) rows into 'Others'.

    ROI is recomputed from total P&L over total buy cost. Averaging ROIs
    across positions of different sizes would be misleading.
    """
    pnl = sum((Decimal(str(item['total_realized_pnl'])) for item in tail), ZERO)
    base = sum((Decimal(str(item['total_buy_cost'])) for item in tail), ZERO)
    roi = safe_divide(pnl, base) * Decimal('100') if base != ZERO else ZERO
    return _symbol_tile(
        name           = OTHERS_LABEL,
        portfolio_names= [],
        pnl            = float(pnl),
        roi_percent    = float(roi),
    )


def _symbol_treemap(symbol_performance: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort user-level symbols by |total P&L|, collapse the tail, drop zero-P&L rows."""
    symbol_rows = _symbol_rows(symbol_performance)
    tiles = _aggregate_with_others(
        symbol_rows,
        sort_key=lambda r: abs(Decimal(str(r['total_realized_pnl']))),
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
