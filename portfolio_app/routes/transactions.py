"""Transactions blueprint - Transaction and asset management routes."""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from decimal import Decimal
from sqlalchemy.exc import OperationalError
from portfolio_app import db
from portfolio_app.services import get_services, ValidationError
from portfolio_app.calculators import PortfolioCalculator
from portfolio_app.forms import (
    TransactionAddForm, TransactionEditForm, AssetAddForm, AssetDeleteForm,
    DividendAddForm, DividendEditForm,
)
from portfolio_app.utils import get_error_message, get_first_form_error, SuccessMessages, ErrorMessages, is_ajax_request, json_response
from portfolio_app.utils.constants import safe_html_id
from portfolio_app.utils.decimal_utils import ZERO
from config import Config

logger = logging.getLogger(__name__)

# Create blueprint
transactions_bp = Blueprint('transactions', __name__)


def _decimal_places(value) -> int:
    """Return the number of significant decimal places in a numeric value."""
    if value is None:
        return 0
    d = Decimal(str(value))
    s = format(d, 'f')
    if '.' not in s:
        return 0
    fractional = s.split('.', 1)[1].rstrip('0')
    return len(fractional)


def _get_transactions_page_context(portfolio_filter=''):
    """Build context data for the transactions page."""
    svc = get_services()
    portfolio_repo, transaction_repo, asset_repo = svc.portfolio_repo, svc.transaction_repo, svc.asset_repo
    portfolio_filter = (portfolio_filter or '').strip()
    portfolios = portfolio_repo.get_all()
    holdings = []

    for portfolio in portfolios:
        if portfolio_filter and portfolio.name != portfolio_filter:
            continue

        tracked_symbols = set()
        asset_by_symbol = {}

        try:
            portfolio_assets = asset_repo.get_by_portfolio_id(portfolio.id)
            for a in portfolio_assets:
                sym_norm = PortfolioCalculator.normalize_symbol(a.symbol)
                if sym_norm:
                    asset_by_symbol[sym_norm] = a
                    tracked_symbols.add(sym_norm)
        except OperationalError:
            asset_by_symbol = {}

        portfolio_transactions = transaction_repo.get_by_portfolio_id(portfolio.id)

        transactions_by_symbol = {}
        for t in portfolio_transactions:
            sym_norm = PortfolioCalculator.normalize_symbol(t.symbol)
            if not sym_norm:
                continue
            transactions_by_symbol.setdefault(sym_norm, []).append(t)
            tracked_symbols.add(sym_norm)

        for sym_norm in sorted(tracked_symbols):
            transactions = transactions_by_symbol.get(sym_norm, [])
            transactions_desc = list(reversed(transactions))

            price_decimal_places = max((_decimal_places(t.price) for t in transactions), default=0)
            price_decimal_places = max(0, min(int(price_decimal_places), 10))

            avg_cost_decimal_places = max(2, price_decimal_places)
            summary = PortfolioCalculator.get_symbol_transactions_summary_from_list(transactions)

            try:
                realized_pnl = Decimal(str(summary.get('realized_pnl', 0) or 0))
                cost_basis = Decimal(str(summary.get('realized_cost_basis', 0) or 0))

                if cost_basis != 0:
                    roi = (realized_pnl / abs(cost_basis)) * Decimal('100')
                    summary['roi_percent'] = float(roi)
                    summary['roi_percent_display'] = f"{roi:+,.2f}%"
                else:
                    summary['roi_percent'] = None
                    summary['roi_percent_display'] = '—'
            except Exception:
                summary['roi_percent'] = None
                summary['roi_percent_display'] = '—'

            html_group_id = safe_html_id(portfolio.id, sym_norm)
            asset = asset_by_symbol.get(sym_norm)
            holdings.append({
                'portfolio': portfolio,
                'symbol': sym_norm,
                'html_group_id': html_group_id,
                'transactions': transactions_desc,
                'summary': summary,
                'price_decimal_places': price_decimal_places,
                'avg_cost_decimal_places': avg_cost_decimal_places,
                'asset_id': asset.id if asset else None,
            })

    # Load dividends grouped by (portfolio_id, symbol) — single query for all portfolios
    visible_portfolio_ids = [p.id for p in portfolios if not portfolio_filter or p.name == portfolio_filter]
    dividends_by_symbol: dict = {}
    dividend_totals: dict = {}
    for div in svc.dividend_repo.get_by_portfolio_ids(visible_portfolio_ids):
        sym = (div.symbol or '').upper()
        if not sym:
            logger.debug('Dividend id=%s has no symbol, skipping display', div.id)
            continue
        key = (div.portfolio_id, sym)
        dividends_by_symbol.setdefault(key, []).append(div)
        dividend_totals[key] = dividend_totals.get(key, ZERO) + Decimal(str(div.amount))

    return {
        'holdings': holdings,
        'funds': portfolios,
        'transaction_types': Config.TRANSACTION_TYPES,
        'selected_portfolio': portfolio_filter,
        'dividends_by_symbol': dividends_by_symbol,
        'dividend_totals': dividend_totals,
    }


@transactions_bp.route('/')
@login_required
def transaction_list():
    """Transactions page."""
    portfolio_filter = request.args.get('portfolio', '')
    ctx = _get_transactions_page_context(portfolio_filter)
    return render_template(
        'transactions.html',
        **ctx,
        form_errors={},
        form_values={},
        active_modal=None,
    )


@transactions_bp.route('/add', methods=['POST'])
@login_required
def transaction_add():
    """Add new transaction."""
    try:
        svc = get_services()
        portfolios = svc.portfolio_repo.get_all()

        form = TransactionAddForm(request.form, portfolios)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_transactions_page_context()
            return render_template(
                'transactions.html',
                **ctx,
                form_errors={'transaction_add': form.errors},
                form_values={'transaction_add': request.form},
                active_modal='addTransactionModal',
            ), 400

        data = form.get_cleaned_data()
        svc.transaction_service.add_transaction(
            portfolio_id=data['portfolio_id'],
            transaction_type=data['transaction_type'],
            symbol=data['symbol'],
            price=data['price'],
            quantity=data['quantity'],
            fees=data['fees'],
            notes=data['notes'],
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.TRANSACTION_ADDED)

        flash(SuccessMessages.TRANSACTION_ADDED, 'success')
        return redirect(url_for('transactions.transaction_list'))

    except (ValueError, ValidationError) as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')
        return redirect(url_for('transactions.transaction_list'))

    except Exception:
        logger.exception('Failed to add transaction')
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/edit/<int:transaction_id>', methods=['POST'])
@login_required
def transaction_edit(transaction_id):
    """Edit existing transaction."""
    try:
        svc = get_services()

        transaction = svc.transaction_repo.get_by_id(transaction_id)
        if not transaction:
            if is_ajax_request():
                return json_response(False, error=ErrorMessages.TRANSACTION_NOT_FOUND)
            flash(ErrorMessages.TRANSACTION_NOT_FOUND, 'error')
            return redirect(url_for('transactions.transaction_list'))

        form = TransactionEditForm(request.form, transaction_id, transaction.transaction_type)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_transactions_page_context()
            return render_template(
                'transactions.html',
                **ctx,
                form_errors={'transaction_edit': form.errors},
                form_values={'transaction_edit': request.form},
                active_modal='editTransactionModal',
            ), 400

        data = form.get_cleaned_data()
        svc.transaction_service.update_transaction(
            transaction_id=data['transaction_id'],
            price=data.get('price'),
            quantity=data.get('quantity'),
            fees=data.get('fees'),
            notes=data.get('notes'),
            symbol=data.get('symbol'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.TRANSACTION_UPDATED)

        flash(SuccessMessages.TRANSACTION_UPDATED, 'success')
        return redirect(url_for('transactions.transaction_list'))

    except (ValueError, ValidationError) as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')
        return redirect(url_for('transactions.transaction_list'))

    except Exception:
        logger.exception('Failed to edit transaction %s', transaction_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/delete/<int:transaction_id>', methods=['POST'])
@login_required
def transaction_delete(transaction_id):
    """Delete transaction."""
    try:
        svc = get_services()
        svc.transaction_service.delete_transaction(transaction_id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.TRANSACTION_DELETED)
        flash(SuccessMessages.TRANSACTION_DELETED, 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete transaction %s', transaction_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/dividends/add', methods=['POST'])
@login_required
def dividend_add():
    """Add a new dividend income record."""
    try:
        svc = get_services()
        portfolios = svc.portfolio_repo.get_all()

        form = DividendAddForm(request.form, portfolios)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_transactions_page_context()
            return render_template(
                'transactions.html',
                **ctx,
                form_errors={'dividend_add': form.errors},
                form_values={'dividend_add': request.form},
                active_modal='addTransactionModal',
            ), 400

        data = form.get_cleaned_data()
        svc.transaction_service.add_dividend(
            portfolio_id=data['portfolio_id'],
            symbol=data['symbol'],
            amount=data['amount'],
            date=data['date'],
            notes=data.get('notes', ''),
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DIVIDEND_ADDED)

        flash(SuccessMessages.DIVIDEND_ADDED, 'success')
        return redirect(url_for('transactions.transaction_list'))

    except (ValueError, ValidationError) as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')
        return redirect(url_for('transactions.transaction_list'))

    except Exception:
        logger.exception('Failed to add dividend')
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/dividends/edit/<int:dividend_id>', methods=['POST'])
@login_required
def dividend_edit(dividend_id):
    """Edit an existing dividend."""
    try:
        svc = get_services()

        dividend = svc.dividend_repo.get_by_id(dividend_id)
        if not dividend:
            if is_ajax_request():
                return json_response(False, error=ErrorMessages.DIVIDEND_NOT_FOUND)
            flash(ErrorMessages.DIVIDEND_NOT_FOUND, 'error')
            return redirect(url_for('transactions.transaction_list'))

        form = DividendEditForm(request.form, dividend_id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))
            flash(get_first_form_error(form.errors), 'error')
            return redirect(url_for('transactions.transaction_list'))

        data = form.get_cleaned_data()
        svc.transaction_service.update_dividend(
            dividend_id=data['dividend_id'],
            amount=data.get('amount'),
            date=data.get('date'),
            notes=data.get('notes'),
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DIVIDEND_UPDATED)

        flash(SuccessMessages.DIVIDEND_UPDATED, 'success')
        return redirect(url_for('transactions.transaction_list'))

    except (ValueError, ValidationError) as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')
        return redirect(url_for('transactions.transaction_list'))

    except Exception:
        logger.exception('Failed to edit dividend %s', dividend_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/dividends/delete/<int:dividend_id>', methods=['POST'])
@login_required
def dividend_delete(dividend_id):
    """Delete a dividend."""
    try:
        svc = get_services()
        svc.transaction_service.delete_dividend(dividend_id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DIVIDEND_DELETED)
        flash(SuccessMessages.DIVIDEND_DELETED, 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete dividend %s', dividend_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/assets/add', methods=['POST'])
@login_required
def asset_add():
    """Add tracked asset."""
    try:
        svc = get_services()
        portfolios = svc.portfolio_repo.get_all()

        form = AssetAddForm(request.form, portfolios)
        if not form.validate():
            ctx = _get_transactions_page_context()
            return render_template(
                'transactions.html',
                **ctx,
                form_errors={'asset_add': form.errors},
                form_values={'asset_add': request.form},
                active_modal='addSymbolModal',
            ), 400

        data = form.get_cleaned_data()
        svc.transaction_service.add_asset(
            portfolio_id=data['portfolio_id'],
            symbol=data['symbol']
        )

        flash(SuccessMessages.ASSET_ADDED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to add asset')
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/assets/delete', methods=['POST'])
@login_required
def asset_delete():
    """Delete tracked asset."""
    try:
        svc = get_services()

        form = AssetDeleteForm(request.form)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=ErrorMessages.INVALID_REQUEST)
            flash(ErrorMessages.INVALID_REQUEST, 'error')
            return redirect(url_for('transactions.transaction_list'))

        data = form.get_cleaned_data()
        svc.transaction_service.delete_asset(
            portfolio_id=data['portfolio_id'],
            symbol=data['symbol']
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.ASSET_DELETED)
        flash(SuccessMessages.ASSET_DELETED, 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete asset')
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('transactions.transaction_list'))
