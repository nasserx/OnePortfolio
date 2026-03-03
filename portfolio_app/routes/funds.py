"""Funds blueprint - Fund management routes."""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from decimal import Decimal
from portfolio_app import db
from portfolio_app.models import FundEvent
from portfolio_app.services import get_services
from portfolio_app.forms import (
    FundAddForm,
    FundDepositForm,
    FundWithdrawForm,
    FundEventEditForm,
    FundEventDeleteForm
)
from portfolio_app.calculators.portfolio_calculator import PortfolioCalculator
from portfolio_app.utils import get_error_message, get_first_form_error, SuccessMessages, is_ajax_request, json_response
from portfolio_app.utils.constants import EventType, safe_html_id
from config import Config

logger = logging.getLogger(__name__)

# Create blueprint
funds_bp = Blueprint('funds', __name__)


def _get_funds_page_context():
    """Get context data for funds page."""
    svc = get_services()
    funds = svc.fund_repo.get_all()
    available_categories = svc.fund_repo.get_available_categories(Config.ASSET_CATEGORIES)

    funds_data = []
    for fund in funds:
        events = svc.event_repo.get_by_fund_id(fund.id)

        # Legacy backfill: create an Initial event for old funds that have
        # a balance but no event history.  Skipped when amount=0 (user may
        # have intentionally deleted all events — show Deposit button instead).
        if not events and fund.amount and Decimal(str(fund.amount)) != 0:
            try:
                backfill = FundEvent(
                    fund_id=fund.id,
                    event_type=EventType.INITIAL,
                    amount_delta=Decimal(str(fund.amount)),
                    date=fund.created_at,
                    notes=None,
                )
                db.session.add(backfill)
                db.session.commit()
                events = [backfill]
            except Exception:
                logger.exception('Failed to backfill events for fund %s', fund.id)
                db.session.rollback()

        total_funds = PortfolioCalculator.get_total_funds_for_fund(fund.id)
        cash = PortfolioCalculator.get_cash_balance_for_fund(fund.id)
        tx_summary = PortfolioCalculator.get_category_transactions_summary(fund.id)
        current_invested = tx_summary['current_invested']

        group_id = safe_html_id(fund.id, fund.category)
        funds_data.append({
            'fund': fund,
            'events': events,
            'group_id': group_id,
            'total_funds': total_funds,
            'cash': cash,
            'current_invested': current_invested,
        })

    return {
        'funds': funds,
        'funds_data': funds_data,
        'available_categories': available_categories,
    }


@funds_bp.route('/')
@login_required
def funds_list():
    """Funds management page."""
    ctx = _get_funds_page_context()
    return render_template(
        'funds.html',
        **ctx,
        form_errors={},
        form_values={},
        open_modal=None,
        open_modal_payload=None,
    )


@funds_bp.route('/add', methods=['POST'])
@login_required
def funds_add():
    """Add new fund."""
    try:
        svc = get_services()
        available_categories = svc.fund_repo.get_available_categories(Config.ASSET_CATEGORIES)

        form = FundAddForm(request.form, available_categories)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_add': form.errors},
                form_values={'funds_add': request.form},
                open_modal='addFundEntryModal',
            ), 400

        data = form.get_cleaned_data()
        fund = svc.fund_service.create_fund(
            category=data['category'],
            amount=data['amount'],
            user_id=current_user.id,
            notes='Initial funding',
            date=data.get('date')
        )

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
            open_modal='addFundEntryModal',
        ), 400

    except Exception:
        logger.exception('Failed to add fund')
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error='Operation failed')

        ctx = _get_funds_page_context()
        return render_template(
            'funds.html',
            **ctx,
            form_errors={'funds_add': {'__all__': 'Operation failed'}},
            form_values={'funds_add': request.form},
            open_modal='addFundEntryModal',
        ), 400


@funds_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def funds_delete(id):
    """Delete fund."""
    try:
        svc = get_services()
        svc.fund_service.delete_fund(id)
        flash(SuccessMessages.FUND_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete fund %s', id)
        db.session.rollback()
        flash('Operation failed', 'error')

    return redirect(url_for('funds.funds_list'))


@funds_bp.route('/deposit/<int:id>', methods=['POST'])
@login_required
def funds_deposit(id):
    """Deposit funds to category."""
    try:
        svc = get_services()

        form = FundDepositForm(request.form, id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_deposit': form.errors},
                form_values={'funds_deposit': request.form},
                open_modal='depositFundModal',
                open_modal_payload={'fund_id': id},
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
        logger.exception('Failed to deposit to fund %s', id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error='Operation failed')

        flash('Operation failed', 'error')
        return redirect(url_for('funds.funds_list'))


@funds_bp.route('/withdraw/<int:id>', methods=['POST'])
@login_required
def funds_withdraw(id):
    """Withdraw funds from category."""
    try:
        svc = get_services()

        form = FundWithdrawForm(request.form, id)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, error=get_first_form_error(form.errors))

            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'funds_withdraw': form.errors},
                form_values={'funds_withdraw': request.form},
                open_modal='withdrawFundModal',
                open_modal_payload={'fund_id': id},
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
        logger.exception('Failed to withdraw from fund %s', id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, error='Operation failed')

        flash('Operation failed', 'error')
        return redirect(url_for('funds.funds_list'))


@funds_bp.route('/events/edit/<int:event_id>', methods=['POST'])
@login_required
def funds_event_edit(event_id):
    """Edit fund event."""
    try:
        svc = get_services()

        event = svc.event_repo.get_by_id(event_id)
        if not event:
            flash('Event not found', 'error')
            return redirect(url_for('funds.funds_list'))

        form = FundEventEditForm(request.form, event_id, event.event_type)
        if not form.validate():
            ctx = _get_funds_page_context()
            return render_template(
                'funds.html',
                **ctx,
                form_errors={'fund_event_edit': form.errors},
                form_values={'fund_event_edit': request.form},
                open_modal='editFundEventModal',
                open_modal_payload={'event_id': event_id},
            ), 400

        data = form.get_cleaned_data()
        svc.fund_service.update_fund_event(
            event_id=data['event_id'],
            amount_delta=data['amount_delta'],
            notes=data.get('notes'),
            date=data.get('date')
        )

        flash(SuccessMessages.EVENT_UPDATED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to edit event %s', event_id)
        db.session.rollback()
        flash('Operation failed', 'error')

    return redirect(url_for('funds.funds_list'))


@funds_bp.route('/events/delete/<int:event_id>', methods=['POST'])
@login_required
def funds_event_delete(event_id):
    """Delete fund event."""
    try:
        svc = get_services()

        event = svc.event_repo.get_by_id(event_id)
        if not event:
            flash('Event not found', 'error')
            return redirect(url_for('funds.funds_list'))

        form = FundEventDeleteForm(request.form, event_id, event.event_type)
        if not form.validate():
            flash(get_first_form_error(form.errors), 'error')
            return redirect(url_for('funds.funds_list'))

        svc.fund_service.delete_fund_event(event_id)

        flash(SuccessMessages.EVENT_DELETED, 'success')

    except ValueError as e:
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete event %s', event_id)
        db.session.rollback()
        flash('Operation failed', 'error')

    return redirect(url_for('funds.funds_list'))
