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
from config import Config

logger = logging.getLogger(__name__)

# Create blueprint
transactions_bp = Blueprint('transactions', __name__)


def _get_transactions_page_context(category_filter=''):
    """Build context data for the transactions page.

    Args:
        category_filter: Optional asset class name to filter the view.
    """
    svc = get_services()
    fund_repo, transaction_repo, asset_repo = svc.fund_repo, svc.transaction_repo, svc.asset_repo
    category_filter = (category_filter or '').strip()
    funds = fund_repo.get_all()
    holdings = []

    def _decimal_places(value) -> int:
        if value is None:
            return 0
        d = Decimal(str(value))
        s = format(d, 'f')
        if '.' not in s:
            return 0
        fractional = s.split('.', 1)[1].rstrip('0')
        return len(fractional)

    for fund in funds:
        if category_filter and fund.asset_class != category_filter:
            continue

        tracked_symbols = set()
        asset_by_symbol = {}

        try:
            fund_assets = asset_repo.get_by_fund_id(fund.id)
            for a in fund_assets:
                sym_norm = PortfolioCalculator.normalize_symbol(a.symbol)
                if sym_norm:
                    asset_by_symbol[sym_norm] = a
                    tracked_symbols.add(sym_norm)
        except OperationalError:
            asset_by_symbol = {}

        fund_transactions = transaction_repo.get_by_fund_id(fund.id)

        transactions_by_symbol = {}
        for t in fund_transactions:
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

            # Per-symbol ROI: realized P&L vs cost basis of sold shares
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

            html_group_id = safe_html_id(fund.id, sym_norm)
            asset = asset_by_symbol.get(sym_norm)
            holdings.append({
                'fund': fund,
                'symbol': sym_norm,
                'html_group_id': html_group_id,
                'transactions': transactions_desc,
                'summary': summary,
                'price_decimal_places': price_decimal_places,
                'avg_cost_decimal_places': avg_cost_decimal_places,
                'asset_id': asset.id if asset else None,
            })

    # Load dividends grouped by (fund_id, symbol) — single query for all funds
    visible_fund_ids = [f.id for f in funds if not category_filter or f.asset_class == category_filter]
    dividends_by_symbol: dict = {}
    dividend_totals: dict = {}
    ZERO = Decimal('0')
    for div in svc.dividend_repo.get_by_fund_ids(visible_fund_ids):
        sym = (div.symbol or '').upper()
        if not sym:
            logger.debug('Dividend id=%s has no symbol, skipping display', div.id)
            continue
        key = (div.fund_id, sym)
        dividends_by_symbol.setdefault(key, []).append(div)
        dividend_totals[key] = dividend_totals.get(key, ZERO) + Decimal(str(div.amount))

    return {
        'holdings': holdings,
        'funds': funds,
        'transaction_types': Config.TRANSACTION_TYPES,
        'selected_category': category_filter,
        'dividends_by_symbol': dividends_by_symbol,
        'dividend_totals': dividend_totals,
    }


@transactions_bp.route('/')
@login_required
def transaction_list():
    """Transactions page."""
    category_filter = request.args.get('category', '')
    ctx = _get_transactions_page_context(category_filter)
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
        funds = svc.fund_repo.get_all()

        form = TransactionAddForm(request.form, funds)
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
            fund_id=data['fund_id'],
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


@transactions_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
def transaction_edit(id):
    """Edit existing transaction."""
    try:
        svc = get_services()

        transaction = svc.transaction_repo.get_by_id(id)
        if not transaction:
            if is_ajax_request():
                return json_response(False, error=ErrorMessages.TRANSACTION_NOT_FOUND)
            flash(ErrorMessages.TRANSACTION_NOT_FOUND, 'error')
            return redirect(url_for('transactions.transaction_list'))

        form = TransactionEditForm(request.form, id, transaction.transaction_type)
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
        logger.exception('Failed to edit transaction %s', id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def transaction_delete(id):
    """Delete transaction."""
    try:
        svc = get_services()
        svc.transaction_service.delete_transaction(id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.TRANSACTION_DELETED)
        flash(SuccessMessages.TRANSACTION_DELETED, 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete transaction %s', id)
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
        funds = svc.fund_repo.get_all()

        form = DividendAddForm(request.form, funds)
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
            fund_id=data['fund_id'],
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


@transactions_bp.route('/dividends/edit/<int:id>', methods=['POST'])
@login_required
def dividend_edit(id):
    """Edit an existing dividend."""
    try:
        svc = get_services()

        dividend = svc.dividend_repo.get_by_id(id)
        if not dividend:
            if is_ajax_request():
                return json_response(False, error=ErrorMessages.DIVIDEND_NOT_FOUND)
            flash(ErrorMessages.DIVIDEND_NOT_FOUND, 'error')
            return redirect(url_for('transactions.transaction_list'))

        form = DividendEditForm(request.form, id)
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
        logger.exception('Failed to edit dividend %s', id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)
        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('transactions.transaction_list'))


@transactions_bp.route('/dividends/delete/<int:id>', methods=['POST'])
@login_required
def dividend_delete(id):
    """Delete a dividend."""
    try:
        svc = get_services()
        svc.transaction_service.delete_dividend(id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DIVIDEND_DELETED)
        flash(SuccessMessages.DIVIDEND_DELETED, 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete dividend %s', id)
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
        funds = svc.fund_repo.get_all()

        form = AssetAddForm(request.form, funds)
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
            fund_id=data['fund_id'],
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
            fund_id=data['fund_id'],
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
