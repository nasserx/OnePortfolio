"""Dashboard blueprint - Portfolio summary and API endpoints."""

import logging
from flask import Blueprint, render_template, jsonify, request, Response
from flask_login import login_required, current_user
from decimal import Decimal
from portfolio_app.services import get_services
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.utils.messages import ErrorMessages

logger = logging.getLogger(__name__)

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__)


def _jsonify_decimals(value):
    """Convert Decimal values to float for JSON serialization."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonify_decimals(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify_decimals(v) for v in value]
    return value


@dashboard_bp.route('/')
def index() -> str:
    """Landing page for guests, dashboard for authenticated users."""
    if not current_user.is_authenticated:
        return render_template('landing.html')

    svc = get_services()
    summary, total_value = svc.portfolio_service.get_portfolio_summary()
    totals = svc.portfolio_service.get_portfolio_dashboard_totals()

    return render_template(
        'index.html',
        summary=summary,
        total_value=total_value,
        totals=totals
    )


@dashboard_bp.route('/api/portfolio-summary')
@login_required
def api_portfolio_summary() -> Response:
    """API endpoint for portfolio summary.

    Returns:
        JSON response with portfolio summary and total value
    """
    svc = get_services()
    summary, total_value = svc.portfolio_service.get_portfolio_summary()

    return jsonify(_jsonify_decimals({
        'summary': summary,
        'total_value': total_value
    }))


@dashboard_bp.route('/api/holdings')
@login_required
def api_holdings() -> Response:
    """API endpoint to get held quantity for a symbol in a fund.

    Query Parameters:
        fund_id: Fund ID
        symbol: Asset symbol

    Returns:
        JSON response with held quantity or error
    """
    try:
        # Validate fund_id
        try:
            fund_id = int(request.args.get('fund_id') or 0)
        except (ValueError, TypeError):
            return jsonify({'error': ErrorMessages.INVALID_FUND_ID}), 400

        if fund_id <= 0:
            return jsonify({'error': ErrorMessages.INVALID_FUND_ID}), 400

        # Validate symbol
        symbol = PortfolioCalculator.normalize_symbol(request.args.get('symbol', ''))
        if not symbol:
            return jsonify({'error': ErrorMessages.INVALID_SYMBOL}), 400

        # Check fund exists
        svc = get_services()
        fund = svc.fund_repo.get_by_id(fund_id)
        if not fund:
            return jsonify({'error': ErrorMessages.FUND_NOT_FOUND}), 404

        # Get held quantity
        held_qty = PortfolioCalculator.get_quantity_held_for_symbol(fund_id, symbol)

        # Format quantity string (preserve full precision)
        # Convert to string to preserve Decimal precision
        held_qty_str = str(held_qty)

        # Remove trailing zeros after decimal point, but keep precision
        if '.' in held_qty_str:
            held_qty_str = held_qty_str.rstrip('0').rstrip('.')

        # Handle edge cases
        if held_qty_str == '' or held_qty_str == '-0':
            held_qty_str = '0'

        return jsonify({
            'fund_id': fund_id,
            'symbol': symbol,
            'held_quantity': held_qty_str,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
