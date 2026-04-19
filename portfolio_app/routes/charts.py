"""Charts blueprint - Portfolio charts and visualizations."""

from flask import Blueprint, render_template
from flask_login import login_required
from portfolio_app.services import get_services

charts_bp = Blueprint('charts', __name__)


@charts_bp.route('/charts')
@login_required
def charts() -> str:
    """Charts page - Portfolio visualizations."""
    svc = get_services()
    portfolio_summary, _ = svc.portfolio_service.get_portfolio_summary()

    chart_data = {
        'categories': [item['name'] for item in portfolio_summary],
        'allocations': [float(item['allocation']) for item in portfolio_summary],
        'realized_pnl': [float(item['realized_pnl']) for item in portfolio_summary],
    }

    return render_template('charts.html', chart_data=chart_data)
