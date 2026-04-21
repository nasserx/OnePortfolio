"""Portfolios blueprint - Portfolio management routes."""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from portfolio_app import db
from portfolio_app.services import get_services
from portfolio_app.forms import (
    PortfolioAddForm,
    PortfolioDepositForm,
    PortfolioWithdrawForm,
    PortfolioEventEditForm,
    PortfolioEventDeleteForm,
)
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.utils.decimal_utils import ZERO
from portfolio_app.utils import get_error_message, get_first_form_error, SuccessMessages, ErrorMessages, is_ajax_request, json_response
from portfolio_app.utils.constants import safe_html_id

logger = logging.getLogger(__name__)

portfolios_bp = Blueprint('portfolios', __name__)


def _get_portfolios_page_context():
    """Build context data for the portfolios page."""
    svc = get_services()
    portfolios = svc.portfolio_repo.get_all()

    portfolio_details = []
    for portfolio in portfolios:
        events = svc.portfolio_event_repo.get_by_portfolio_id(portfolio.id)

        cash = PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id)
        tx_summary = PortfolioCalculator.get_category_transactions_summary(portfolio.id)
        cost_basis = tx_summary['cost_basis']
        book_value = cash + cost_basis

        realized_perf = PortfolioCalculator.get_realized_performance_for_portfolio(portfolio.id)
        realized_pnl = realized_perf['realized_pnl']
        realized_cost_basis = realized_perf['realized_cost_basis']

        if realized_cost_basis != ZERO:
            roi_percent = (realized_pnl / abs(realized_cost_basis)) * 100
            roi_display = f"{roi_percent:+,.2f}%"
        else:
            roi_percent = ZERO
            roi_display = '—'

        portfolio_details.append({
            'portfolio': portfolio,
            'events': events,
            'book_value': book_value,
            'realized_pnl': realized_pnl,
            'realized_cost_basis': realized_cost_basis,
            'roi_percent': roi_percent,
            'roi_display': roi_display,
        })

    return {
        'portfolios': portfolios,
        'portfolio_details': portfolio_details,
    }


@portfolios_bp.route('/')
@login_required
def portfolios_list():
    """Portfolios page."""
    ctx = _get_portfolios_page_context()
    return render_template(
        'funds.html',
        **ctx,
        form_errors={},
        form_values={},
        active_modal=None,
        modal_data=None,
    )


@portfolios_bp.route('/add', methods=['POST'])
@login_required
def portfolios_add():
    """Create new portfolio."""
    try:
        svc = get_services()
        existing_names = svc.portfolio_repo.get_existing_names()

        form = PortfolioAddForm(request.form, existing_names)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_portfolios_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'portfolios_add': form.errors},
                form_values={'portfolios_add': request.form},
                active_modal='newPortfolioModal',
            ), 400

        data = form.get_cleaned_data()
        svc.portfolio_service.create_portfolio(name=data['name'], user_id=current_user.id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.PORTFOLIO_CREATED)

        flash(SuccessMessages.PORTFOLIO_CREATED, 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        ctx = _get_portfolios_page_context()
        return render_template(
            'funds.html',
            **ctx,
            form_errors={'portfolios_add': {'__all__': str(e)}},
            form_values={'portfolios_add': request.form},
            active_modal='newPortfolioModal',
        ), 400

    except Exception:
        logger.exception('Failed to add portfolio')
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        ctx = _get_portfolios_page_context()
        return render_template(
            'funds.html',
            **ctx,
            form_errors={'portfolios_add': {'__all__': ErrorMessages.OPERATION_FAILED}},
            form_values={'portfolios_add': request.form},
            active_modal='newPortfolioModal',
        ), 400


@portfolios_bp.route('/delete/<int:portfolio_id>', methods=['POST'])
@login_required
def portfolios_delete(portfolio_id):
    """Delete portfolio."""
    try:
        svc = get_services()
        svc.portfolio_service.delete_portfolio(portfolio_id)
        flash(SuccessMessages.PORTFOLIO_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete portfolio %s', portfolio_id)
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/deposit/<int:portfolio_id>', methods=['POST'])
@login_required
def portfolios_deposit(portfolio_id):
    """Deposit funds into a portfolio."""
    try:
        svc = get_services()

        form = PortfolioDepositForm(request.form, portfolio_id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_portfolios_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'portfolios_deposit': form.errors},
                form_values={'portfolios_deposit': request.form},
                active_modal='depositFundsModal',
                modal_data={'portfolio_id': portfolio_id},
            ), 400

        data = form.get_cleaned_data()
        svc.portfolio_service.deposit_funds(
            portfolio_id=data['portfolio_id'],
            amount_delta=data['amount_delta'],
            notes=data.get('notes'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DEPOSIT_COMPLETED)

        flash(SuccessMessages.DEPOSIT_COMPLETED, 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        flash(get_error_message(e), 'error')
        return redirect(url_for('portfolios.portfolios_list'))

    except Exception:
        logger.exception('Failed to deposit to portfolio %s', portfolio_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/withdraw/<int:portfolio_id>', methods=['POST'])
@login_required
def portfolios_withdraw(portfolio_id):
    """Withdraw funds from a portfolio."""
    try:
        svc = get_services()

        form = PortfolioWithdrawForm(request.form, portfolio_id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_portfolios_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'portfolios_withdraw': form.errors},
                form_values={'portfolios_withdraw': request.form},
                active_modal='withdrawFundsModal',
                modal_data={'portfolio_id': portfolio_id},
            ), 400

        data = form.get_cleaned_data()
        svc.portfolio_service.withdraw_funds(
            portfolio_id=data['portfolio_id'],
            amount_delta=data['amount_delta'],
            notes=data.get('notes'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.WITHDRAWAL_COMPLETED)

        flash(SuccessMessages.WITHDRAWAL_COMPLETED, 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        flash(get_error_message(e), 'error')
        return redirect(url_for('portfolios.portfolios_list'))

    except Exception:
        logger.exception('Failed to withdraw from portfolio %s', portfolio_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/events/edit/<int:event_id>', methods=['POST'])
@login_required
def portfolios_event_edit(event_id):
    """Edit portfolio event."""
    try:
        svc = get_services()

        event = svc.portfolio_event_repo.get_by_id(event_id)
        if not event:
            flash(ErrorMessages.EVENT_NOT_FOUND, 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        form = PortfolioEventEditForm(request.form, event_id, event.event_type)
        if not form.validate():
            ctx = _get_portfolios_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'portfolio_event_edit': form.errors},
                form_values={'portfolio_event_edit': request.form},
                active_modal='editPortfolioEventModal',
                modal_data={'event_id': event_id},
            ), 400

        data = form.get_cleaned_data()
        amount = data['amount_delta']
        if event.event_type == 'Withdrawal':
            amount = -amount
        svc.portfolio_service.update_portfolio_event(
            event_id=data['event_id'],
            amount_delta=amount,
            notes=data.get('notes'),
            date=data.get('date')
        )

        flash(SuccessMessages.ENTRY_UPDATED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to edit event %s', event_id)
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/events/delete/<int:event_id>', methods=['POST'])
@login_required
def portfolios_event_delete(event_id):
    """Delete portfolio event."""
    try:
        svc = get_services()

        event = svc.portfolio_event_repo.get_by_id(event_id)
        if not event:
            flash(ErrorMessages.EVENT_NOT_FOUND, 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        form = PortfolioEventDeleteForm(request.form, event_id, event.event_type)
        if not form.validate():
            flash(get_first_form_error(form.errors), 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        svc.portfolio_service.delete_portfolio_event(event_id)

        flash(SuccessMessages.ENTRY_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete event %s', event_id)
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('portfolios.portfolios_list'))
