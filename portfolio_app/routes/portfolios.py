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
from portfolio_app.utils import (
    get_error_message, get_first_form_error, MESSAGES,
    is_ajax_request, json_response, field_error_response,
)

logger = logging.getLogger(__name__)

portfolios_bp = Blueprint('portfolios', __name__)


def _get_portfolios_page_context():
    """Build context data for the portfolios page."""
    svc = get_services()
    portfolios = svc.portfolio_repo.get_all()
    uid = svc.portfolio_repo.user_id

    portfolio_details = []
    for portfolio in portfolios:
        events = svc.portfolio_event_repo.get_by_portfolio_id(portfolio.id)

        cash = PortfolioCalculator.get_available_cash_for_portfolio(portfolio.id, user_id=uid)
        tx_summary = PortfolioCalculator.get_portfolio_transactions_summary(portfolio.id, user_id=uid)
        cost_basis = tx_summary['cost_basis']
        book_value = cash + cost_basis

        total_contributed = PortfolioCalculator.get_total_deposits_for_portfolio(portfolio.id, user_id=uid)

        realized_perf = PortfolioCalculator.get_realized_performance_for_portfolio(portfolio.id, user_id=uid)
        realized_pnl = realized_perf['realized_pnl']
        if total_contributed != ZERO:
            roi_percent = (realized_pnl / total_contributed) * 100
            roi_display = f"{roi_percent:+,.2f}%"
        else:
            roi_percent = ZERO
            roi_display = '—'

        portfolio_details.append({
            'portfolio': portfolio,
            'events': events,
            'total_contributed': total_contributed,
            'book_value': book_value,
            'realized_pnl': realized_pnl,
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
        'portfolios.html',
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
                return json_response(False, errors=form.errors)

            ctx = _get_portfolios_page_context()
            return render_template(
                'portfolios.html',
                **ctx,
                form_errors={'portfolios_add': form.errors},
                form_values={'portfolios_add': request.form},
                active_modal='newPortfolioModal',
            ), 400

        data = form.get_cleaned_data()
        svc.portfolio_service.create_portfolio(name=data['name'], user_id=current_user.id)

        if is_ajax_request():
            return json_response(True, message=MESSAGES['PORTFOLIO_CREATED'])

        flash(MESSAGES['PORTFOLIO_CREATED'], 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, errors={'__all__': get_error_message(e)})

        ctx = _get_portfolios_page_context()
        return render_template(
            'portfolios.html',
            **ctx,
            form_errors={'portfolios_add': {'__all__': str(e)}},
            form_values={'portfolios_add': request.form},
            active_modal='newPortfolioModal',
        ), 400

    except Exception:
        logger.exception('Failed to add portfolio')
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, errors={'__all__': MESSAGES['PORTFOLIO_ADD_FAILED']})

        ctx = _get_portfolios_page_context()
        return render_template(
            'portfolios.html',
            **ctx,
            form_errors={'portfolios_add': {'__all__': MESSAGES['PORTFOLIO_ADD_FAILED']}},
            form_values={'portfolios_add': request.form},
            active_modal='newPortfolioModal',
        ), 400


@portfolios_bp.route('/delete/<int:portfolio_id>', methods=['POST'])
@login_required
def portfolios_delete(portfolio_id):
    """Delete portfolio. Returns JSON for AJAX so the Confirm Remove
    modal can surface failures inline (matching the behaviour of every
    other delete dialog in the app)."""
    try:
        svc = get_services()
        svc.portfolio_service.delete_portfolio(portfolio_id)
        if is_ajax_request():
            return json_response(True, message=MESSAGES['PORTFOLIO_REMOVED'])
        flash(MESSAGES['PORTFOLIO_REMOVED'], 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, errors={'__all__': get_error_message(e)})
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete portfolio %s', portfolio_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(
                False, errors={'__all__': MESSAGES['PORTFOLIO_DELETE_FAILED']},
            )
        flash(MESSAGES['PORTFOLIO_DELETE_FAILED'], 'error')

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
                return json_response(False, errors=form.errors)

            ctx = _get_portfolios_page_context()
            return render_template(
                'portfolios.html',
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
            return json_response(True, message=MESSAGES['DEPOSIT_SUCCESSFUL'])

        flash(MESSAGES['DEPOSIT_SUCCESSFUL'], 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, errors={'__all__': get_error_message(e)})

        flash(get_error_message(e), 'error')
        return redirect(url_for('portfolios.portfolios_list'))

    except Exception:
        logger.exception('Failed to deposit to portfolio %s', portfolio_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, errors={'__all__': MESSAGES['DEPOSIT_FAILED']})

        flash(MESSAGES['DEPOSIT_FAILED'], 'error')
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
                return json_response(False, errors=form.errors)

            ctx = _get_portfolios_page_context()
            return render_template(
                'portfolios.html',
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
            return json_response(True, message=MESSAGES['WITHDRAWAL_SUCCESSFUL'])

        flash(MESSAGES['WITHDRAWAL_SUCCESSFUL'], 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            # "Insufficient amount." comes from the service when the
            # withdrawal exceeds available cash — surface it under the
            # amount input rather than as a modal banner.
            return field_error_response(
                get_error_message(e),
                {
                    MESSAGES['INSUFFICIENT_AMOUNT']: 'amount_delta',
                    MESSAGES['CASH_ALREADY_SPENT']:  'amount_delta',
                },
            )

        flash(get_error_message(e), 'error')
        return redirect(url_for('portfolios.portfolios_list'))

    except Exception:
        logger.exception('Failed to withdraw from portfolio %s', portfolio_id)
        db.session.rollback()

        if is_ajax_request():
            return json_response(False, errors={'__all__': MESSAGES['WITHDRAWAL_FAILED']})

        flash(MESSAGES['WITHDRAWAL_FAILED'], 'error')
        return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/events/edit/<int:event_id>', methods=['POST'])
@login_required
def portfolios_event_edit(event_id):
    """Edit portfolio event."""
    try:
        svc = get_services()

        event = svc.portfolio_event_repo.get_by_id(event_id)
        if not event:
            if is_ajax_request():
                return json_response(
                    False, errors={'__all__': MESSAGES['CASH_EVENT_NOT_FOUND']},
                )
            flash(MESSAGES['CASH_EVENT_NOT_FOUND'], 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        form = PortfolioEventEditForm(request.form, event_id, event.event_type)
        if not form.validate():
            if is_ajax_request():
                return json_response(False, errors=form.errors)

            ctx = _get_portfolios_page_context()
            return render_template(
                'portfolios.html',
                **ctx,
                form_errors={'portfolio_event_edit': form.errors},
                form_values={'portfolio_event_edit': request.form},
                active_modal='editPortfolioEventModal',
                modal_data={'event_id': event_id},
            ), 400

        data = form.get_cleaned_data()
        amount = data['amount_delta']
        event_type = event.event_type
        if event_type == 'Withdrawal':
            amount = -amount
        svc.portfolio_service.update_portfolio_event(
            event_id=data['event_id'],
            amount_delta=amount,
            notes=data.get('notes'),
            date=data.get('date')
        )

        if is_ajax_request():
            return json_response(True, message=MESSAGES['TRANSACTION_UPDATED'])

        flash(MESSAGES['TRANSACTION_UPDATED'], 'success')
        return redirect(url_for('portfolios.portfolios_list'))

    except ValueError as e:
        if is_ajax_request():
            # Event-edit's input is named ``edit_cash_event_amount`` —
            # surface insufficient/clawback messages under it.
            return field_error_response(
                get_error_message(e),
                {
                    MESSAGES['INSUFFICIENT_AMOUNT']: 'edit_cash_event_amount',
                    MESSAGES['CASH_ALREADY_SPENT']:  'edit_cash_event_amount',
                },
            )
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to edit event %s', event_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(False, errors={'__all__': MESSAGES['CASH_EVENT_UPDATE_FAILED']})
        flash(MESSAGES['CASH_EVENT_UPDATE_FAILED'], 'error')

    return redirect(url_for('portfolios.portfolios_list'))


@portfolios_bp.route('/events/delete/<int:event_id>', methods=['POST'])
@login_required
def portfolios_event_delete(event_id):
    """Delete portfolio event.

    Returns JSON for AJAX modal submissions so the confirm-remove dialog
    can surface ``CASH_ALREADY_SPENT`` (and other ValueError messages)
    inline as a banner — without this branch the user got a full-page
    redirect with a flash message instead, hiding the reason behind a
    page reload.
    """
    try:
        svc = get_services()

        event = svc.portfolio_event_repo.get_by_id(event_id)
        if not event:
            if is_ajax_request():
                return json_response(
                    False, errors={'__all__': MESSAGES['CASH_EVENT_NOT_FOUND']},
                )
            flash(MESSAGES['CASH_EVENT_NOT_FOUND'], 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        event_type = event.event_type
        form = PortfolioEventDeleteForm(request.form, event_id, event_type)
        if not form.validate():
            first_err = get_first_form_error(form.errors)
            if is_ajax_request():
                return json_response(False, errors={'__all__': first_err})
            flash(first_err, 'error')
            return redirect(url_for('portfolios.portfolios_list'))

        svc.portfolio_service.delete_portfolio_event(event_id)

        if is_ajax_request():
            return json_response(True, message=MESSAGES['TRANSACTION_REMOVED'])
        flash(MESSAGES['TRANSACTION_REMOVED'], 'success')

    except ValueError as e:
        if is_ajax_request():
            return json_response(False, errors={'__all__': get_error_message(e)})
        flash(get_error_message(e), 'error')

    except Exception:
        logger.exception('Failed to delete event %s', event_id)
        db.session.rollback()
        if is_ajax_request():
            return json_response(
                False, errors={'__all__': MESSAGES['CASH_EVENT_DELETE_FAILED']},
            )
        flash(MESSAGES['CASH_EVENT_DELETE_FAILED'], 'error')

    return redirect(url_for('portfolios.portfolios_list'))
