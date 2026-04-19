"""Funds blueprint - Portfolio management routes."""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from portfolio_app import db
from portfolio_app.services import get_services
from portfolio_app.forms import (
    FundAddForm,
    FundDepositForm,
    FundWithdrawForm,
    FundEventEditForm,
    FundEventDeleteForm
)
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.utils import get_error_message, get_first_form_error, SuccessMessages, ErrorMessages, is_ajax_request, json_response
from portfolio_app.utils.constants import safe_html_id

logger = logging.getLogger(__name__)

funds_bp = Blueprint('funds', __name__)


def _get_funds_page_context():
    """Build context data for the portfolios page."""
    svc = get_services()
    funds = svc.fund_repo.get_all()

    fund_details = []
    for fund in funds:
        events = svc.event_repo.get_by_fund_id(fund.id)

        total_funds = PortfolioCalculator.get_total_funds_for_fund(fund.id)
        cash = PortfolioCalculator.get_cash_balance_for_fund(fund.id)
        tx_summary = PortfolioCalculator.get_category_transactions_summary(fund.id)
        current_invested = tx_summary['current_invested']

        fund_details.append({
            'fund': fund,
            'events': events,
            'total_funds': total_funds,
            'cash': cash,
            'current_invested': current_invested,
        })

    return {
        'funds': funds,
        'fund_details': fund_details,
    }


@funds_bp.route('/')
@login_required
def funds_list():
    """Portfolios page."""
    ctx = _get_funds_page_context()
    return render_template(
        'funds.html',
        **ctx,
        form_errors={},
        form_values={},
        active_modal=None,
        modal_data=None,
    )


@funds_bp.route('/add', methods=['POST'])
@login_required
def funds_add():
    """Create new portfolio."""
    try:
        svc = get_services()
        existing_names = svc.fund_repo.get_existing_names()

        form = FundAddForm(request.form, existing_names)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_add': form.errors},
                form_values={'funds_add': request.form},
                active_modal='newFundModal',
            ), 400

        data = form.get_cleaned_data()
        svc.fund_service.create_fund(name=data['name'], user_id=current_user.id)

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.FUND_CREATED)

        flash(SuccessMessages.FUND_CREATED, 'success')
        return redirect(url_for('funds.funds_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        ctx = _get_funds_page_context()
        return render_template(
            'funds.html',
            **ctx,
            form_errors={'funds_add': {'__all__': str(e)}},
            form_values={'funds_add': request.form},
            active_modal='newFundModal',
        ), 400

    except Exception:
        logger.exception('Failed to add portfolio')
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        ctx = _get_funds_page_context()
        return render_template(
            'funds.html',
            **ctx,
            form_errors={'funds_add': {'__all__': ErrorMessages.OPERATION_FAILED}},
            form_values={'funds_add': request.form},
            active_modal='newFundModal',
        ), 400


@funds_bp.route('/delete/<int:fund_id>', methods=['POST'])
@login_required
def funds_delete(fund_id):
    """Delete portfolio."""
    try:
        svc = get_services()
        svc.fund_service.delete_fund(fund_id)
        flash(SuccessMessages.FUND_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete portfolio %s', fund_id)
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('funds.funds_list'))


@funds_bp.route('/deposit/<int:fund_id>', methods=['POST'])
@login_required
def funds_deposit(fund_id):
    """Deposit funds into a portfolio."""
    try:
        svc = get_services()

        form = FundDepositForm(request.form, fund_id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_deposit': form.errors},
                form_values={'funds_deposit': request.form},
                active_modal='depositFundsModal',
                modal_data={'fund_id': fund_id},
            ), 400

        data = form.get_cleaned_data()
        svc.fund_service.deposit_funds(
            fund_id=data['fund_id'],
            amount_delta=data['amount_delta'],
            notes=data.get('notes'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.DEPOSIT_COMPLETED)

        flash(SuccessMessages.DEPOSIT_COMPLETED, 'success')
        return redirect(url_for('funds.funds_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        flash(get_error_message(e), 'error')
        return redirect(url_for('funds.funds_list'))

    except Exception:
        logger.exception('Failed to deposit to portfolio %s', fund_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('funds.funds_list'))


@funds_bp.route('/withdraw/<int:fund_id>', methods=['POST'])
@login_required
def funds_withdraw(fund_id):
    """Withdraw funds from a portfolio."""
    try:
        svc = get_services()

        form = FundWithdrawForm(request.form, fund_id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_withdraw': form.errors},
                form_values={'funds_withdraw': request.form},
                active_modal='withdrawFundsModal',
                modal_data={'fund_id': fund_id},
            ), 400

        data = form.get_cleaned_data()
        svc.fund_service.withdraw_funds(
            fund_id=data['fund_id'],
            amount_delta=data['amount_delta'],
            notes=data.get('notes'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=SuccessMessages.WITHDRAWAL_COMPLETED)

        flash(SuccessMessages.WITHDRAWAL_COMPLETED, 'success')
        return redirect(url_for('funds.funds_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, error=get_error_message(e))

        flash(get_error_message(e), 'error')
        return redirect(url_for('funds.funds_list'))

    except Exception:
        logger.exception('Failed to withdraw from portfolio %s', fund_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error=ErrorMessages.OPERATION_FAILED)

        flash(ErrorMessages.OPERATION_FAILED, 'error')
        return redirect(url_for('funds.funds_list'))


@funds_bp.route('/events/edit/<int:event_id>', methods=['POST'])
@login_required
def funds_event_edit(event_id):
    """Edit fund event."""
    try:
        svc = get_services()

        event = svc.event_repo.get_by_id(event_id)
        if not event:
            flash(ErrorMessages.EVENT_NOT_FOUND, 'error')
            return redirect(url_for('funds.funds_list'))

        form = FundEventEditForm(request.form, event_id, event.event_type)
        if not form.validate():
            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'fund_event_edit': form.errors},
                form_values={'fund_event_edit': request.form},
                active_modal='editFundEventModal',
                modal_data={'event_id': event_id},
            ), 400

        data = form.get_cleaned_data()
        svc.fund_service.update_fund_event(
            event_id=data['event_id'],
            amount_delta=data['amount_delta'],
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

    return redirect(url_for('funds.funds_list'))


@funds_bp.route('/events/delete/<int:event_id>', methods=['POST'])
@login_required
def funds_event_delete(event_id):
    """Delete fund event."""
    try:
        svc = get_services()

        event = svc.event_repo.get_by_id(event_id)
        if not event:
            flash(ErrorMessages.EVENT_NOT_FOUND, 'error')
            return redirect(url_for('funds.funds_list'))

        form = FundEventDeleteForm(request.form, event_id, event.event_type)
        if not form.validate():
            flash(get_first_form_error(form.errors), 'error')
            return redirect(url_for('funds.funds_list'))

        svc.fund_service.delete_fund_event(event_id)

        flash(SuccessMessages.ENTRY_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete event %s', event_id)
        db.session.rollback()
        flash(ErrorMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('funds.funds_list'))
