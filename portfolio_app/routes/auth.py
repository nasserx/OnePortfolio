"""Passwordless authentication, email settings, and account deletion routes."""

import logging

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_limiter.util import get_remote_address
from sqlalchemy.exc import SQLAlchemyError

from portfolio_app import limiter
from portfolio_app.forms.auth_forms import LoginForm, UpdateEmailForm, VerifyCodeForm
from portfolio_app.services import get_services
from portfolio_app.services.auth_service import (
    AUTHENTICATION_PURPOSE,
    RECENT_AUTH_PURPOSE,
)
from portfolio_app.utils.auth_session import (
    establish_auth_session,
    mark_recent_auth,
    recent_auth_is_valid,
)
from portfolio_app.utils.email import (
    send_authentication_email,
    send_deletion_confirmation_email,
    send_verification_email,
)
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.utils.otp import otp_digest
from portfolio_app.utils.redirects import safe_local_redirect


logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

_AUTH_TOKEN_KEY = 'auth_challenge_token'
_AUTH_EMAIL_KEY = 'auth_challenge_email'
_AUTH_NEXT_KEY = 'auth_challenge_next'
_REAUTH_TOKEN_KEY = 'reauth_challenge_token'
_REAUTH_NEXT_KEY = 'reauth_next'

def _email_rate_limit_key(email: str) -> str:
    """Return a stable normalized-target key without exposing the address."""
    normalized = (email or '').strip().lower()
    return 'auth-email:' + otp_digest(
        '', purpose='auth-rate-limit', context=(normalized,),
    )


def _request_email_key():
    return _email_rate_limit_key(request.form.get('email', ''))


def _active_auth_email_key():
    return _email_rate_limit_key(session.get(_AUTH_EMAIL_KEY, ''))


def _current_user_email_key():
    return _email_rate_limit_key(getattr(current_user, 'email', ''))


def _render_code_page(*, recent=False, form_errors=None):
    return render_template(
        'auth/verify_code.html',
        form_errors=form_errors or {},
        verify_endpoint='auth.reauthenticate_verify' if recent else 'auth.verify_code',
        resend_endpoint='auth.reauthenticate_resend' if recent else 'auth.resend_code',
        heading='Verification code',
        submit_label='Confirm' if recent else 'Continue',
        back_url=(
            url_for('auth.settings', tab='security')
            if recent else url_for('auth.login')
        ),
    )


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(
    '10 per 15 minutes', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_AUTH_REQUEST'],
)
@limiter.limit(
    '5 per hour', methods=['POST'], key_func=_request_email_key,
    error_message=MESSAGES['RATE_LIMIT_AUTH_REQUEST'],
)
def login():
    """Begin the sole production authentication and registration flow."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form_errors = {}
    form_values = {}
    if request.method == 'POST':
        form = LoginForm(request.form)
        if form.validate():
            email = form.get_cleaned_data()['email']
            try:
                issue = get_services().auth_service.begin_authentication(email)
                send_authentication_email(issue.recipient, issue.code)
                session[_AUTH_TOKEN_KEY] = issue.token
                session[_AUTH_EMAIL_KEY] = email
                session[_AUTH_NEXT_KEY] = safe_local_redirect(request.args.get('next'))
                flash(MESSAGES['AUTH_CODE_REQUEST_RESULT'], 'info')
                return redirect(url_for('auth.verify_code'))
            except Exception:
                logger.warning('Authentication challenge creation failed')
                form_errors['__all__'] = MESSAGES['AUTH_REQUEST_FAILED']
        else:
            form_errors = form.errors
        form_values = request.form
    return render_template(
        'auth/login.html',
        form_errors=form_errors,
        form_values=form_values,
        safe_next=safe_local_redirect(request.args.get('next')),
    )


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Legacy URL alias; account creation now starts at the email entry flow."""
    next_page = safe_local_redirect(request.args.get('next'))
    return redirect(url_for('auth.login', next=next_page) if next_page else url_for('auth.login'))


@auth_bp.route('/verify-code', methods=['GET', 'POST'])
@limiter.limit(
    '10 per 15 minutes', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
@limiter.limit(
    '5 per 15 minutes', methods=['POST'], key_func=_active_auth_email_key,
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
def verify_code():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    token = session.get(_AUTH_TOKEN_KEY)
    if not token or not session.get(_AUTH_EMAIL_KEY):
        return redirect(url_for('auth.login'))
    errors = {}
    if request.method == 'POST':
        form = VerifyCodeForm(request.form)
        if form.validate():
            user = get_services().auth_service.verify_challenge(
                token,
                form.get_cleaned_data()['code'],
                AUTHENTICATION_PURPOSE,
            )
            if user is not None:
                next_page = safe_local_redirect(session.get(_AUTH_NEXT_KEY))
                session.clear()
                login_user(user, remember=False, fresh=True)
                session.permanent = True
                establish_auth_session(session)
                return redirect(next_page or url_for('dashboard.index'))
            errors['code'] = MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED']
        else:
            errors = form.errors
    return _render_code_page(form_errors=errors)


@auth_bp.route('/resend-code', methods=['POST'])
@limiter.limit(
    '10 per hour', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
@limiter.limit(
    '3 per hour', methods=['POST'], key_func=_active_auth_email_key,
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
def resend_code():
    token = session.get(_AUTH_TOKEN_KEY)
    if token:
        issue = get_services().auth_service.resend_challenge(
            token, AUTHENTICATION_PURPOSE,
        )
        if issue:
            send_authentication_email(issue.recipient, issue.code)
    flash(MESSAGES['AUTH_CODE_REQUEST_RESULT'], 'info')
    return redirect(url_for('auth.verify_code') if token else url_for('auth.login'))


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    session['_remember'] = 'clear'
    return redirect(url_for('auth.login'))


@auth_bp.route('/reauthenticate', methods=['GET', 'POST'])
@login_required
@limiter.limit(
    '10 per 15 minutes', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_AUTH_REQUEST'],
)
@limiter.limit(
    '5 per hour', methods=['POST'], key_func=_current_user_email_key,
    error_message=MESSAGES['RATE_LIMIT_AUTH_REQUEST'],
)
def reauthenticate():
    if recent_auth_is_valid(session):
        return redirect(safe_local_redirect(request.args.get('next')) or url_for('auth.settings'))
    next_page = safe_local_redirect(request.args.get('next'))
    if next_page:
        session[_REAUTH_NEXT_KEY] = next_page
    if request.method == 'POST':
        try:
            issue = get_services().auth_service.begin_recent_authentication(current_user)
            send_authentication_email(issue.recipient, issue.code)
            session[_REAUTH_TOKEN_KEY] = issue.token
            flash(MESSAGES['AUTH_CODE_REQUEST_RESULT'], 'info')
            return redirect(url_for('auth.reauthenticate_verify'))
        except Exception:
            logger.warning('Recent-auth challenge creation failed')
            flash(MESSAGES['AUTH_REQUEST_FAILED'], 'warning')
    return render_template('auth/reauthenticate.html')


@auth_bp.route('/reauthenticate/verify', methods=['GET', 'POST'])
@login_required
@limiter.limit(
    '10 per 15 minutes', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
@limiter.limit(
    '5 per 15 minutes', methods=['POST'], key_func=_current_user_email_key,
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
def reauthenticate_verify():
    token = session.get(_REAUTH_TOKEN_KEY)
    if not token:
        return redirect(url_for('auth.reauthenticate'))
    errors = {}
    if request.method == 'POST':
        form = VerifyCodeForm(request.form)
        if form.validate():
            user = get_services().auth_service.verify_challenge(
                token,
                form.get_cleaned_data()['code'],
                RECENT_AUTH_PURPOSE,
            )
            if user is not None and user.id == current_user.id:
                session.pop(_REAUTH_TOKEN_KEY, None)
                mark_recent_auth(session)
                return redirect(
                    safe_local_redirect(session.pop(_REAUTH_NEXT_KEY, None))
                    or url_for('auth.settings', tab='security')
                )
            errors['code'] = MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED']
        else:
            errors = form.errors
    return _render_code_page(recent=True, form_errors=errors)


@auth_bp.route('/reauthenticate/resend', methods=['POST'])
@login_required
@limiter.limit(
    '10 per hour', methods=['POST'], key_func=get_remote_address,
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
@limiter.limit(
    '3 per hour', methods=['POST'], key_func=_current_user_email_key,
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
def reauthenticate_resend():
    token = session.get(_REAUTH_TOKEN_KEY)
    if token:
        issue = get_services().auth_service.resend_challenge(token, RECENT_AUTH_PURPOSE)
        if issue:
            send_authentication_email(issue.recipient, issue.code)
    flash(MESSAGES['AUTH_CODE_REQUEST_RESULT'], 'info')
    return redirect(url_for('auth.reauthenticate_verify'))


@auth_bp.route('/settings')
@login_required
def settings():
    return render_template('auth/settings.html')


@auth_bp.route('/update-email', methods=['GET', 'POST'])
@login_required
def update_email():
    if not recent_auth_is_valid(session):
        return redirect(url_for('auth.reauthenticate', next=url_for('auth.update_email')))
    errors = {}
    values = {}
    if request.method == 'POST':
        form = UpdateEmailForm(request.form)
        if form.validate():
            try:
                new_email = form.get_cleaned_data()['email']
                code = get_services().auth_service.stage_email_change(current_user, new_email)
                send_verification_email(new_email, code)
                return redirect(url_for('auth.verify_email_change'))
            except ValueError as exc:
                errors['email'] = str(exc)
            except Exception:
                logger.warning('Email update initiation failed')
                errors['__all__'] = MESSAGES['EMAIL_UPDATE_FAILED']
        else:
            errors = form.errors
        values = request.form
    return render_template(
        'auth/update_email.html', form_errors=errors, form_values=values,
        current_email=current_user.email,
    )


@auth_bp.route('/settings/email/verify', methods=['GET', 'POST'])
@login_required
@limiter.limit(
    '5 per 15 minutes', methods=['POST'], key_func=_current_user_email_key,
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
def verify_email_change():
    if not recent_auth_is_valid(session):
        return redirect(url_for(
            'auth.reauthenticate', next=url_for('auth.verify_email_change'),
        ))
    if not current_user.pending_email:
        return redirect(url_for('auth.settings', tab='security'))
    errors = {}
    if request.method == 'POST':
        form = VerifyCodeForm(request.form)
        if form.validate():
            success, message = get_services().auth_service.verify_email_change(
                current_user, form.get_cleaned_data()['code'],
            )
            if success:
                flash(MESSAGES['EMAIL_UPDATED'], 'success')
                return redirect(url_for('auth.settings', tab='security'))
            errors['code'] = message
        else:
            errors = form.errors
    return render_template(
        'auth/verify_code.html',
        form_errors=errors,
        verify_endpoint='auth.verify_email_change',
        resend_endpoint='auth.resend_email_change',
        heading='Verification code',
        submit_label='Update email',
        back_url=url_for('auth.settings', tab='security'),
    )


@auth_bp.route('/settings/email/resend', methods=['POST'])
@login_required
@limiter.limit(
    '3 per hour', methods=['POST'], key_func=_current_user_email_key,
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
def resend_email_change():
    if not recent_auth_is_valid(session):
        return redirect(url_for(
            'auth.reauthenticate', next=url_for('auth.verify_email_change'),
        ))
    code = get_services().auth_service.resend_email_change(current_user)
    if code and current_user.pending_email:
        send_verification_email(current_user.pending_email, code)
    flash(MESSAGES['VERIFICATION_CODE_RESEND_RESULT'], 'info')
    return redirect(url_for('auth.verify_email_change'))


@auth_bp.route('/settings/delete/request', methods=['POST'])
@login_required
def delete_account_request():
    try:
        code = get_services().auth_service.request_account_deletion(current_user)
        sent = send_deletion_confirmation_email(current_user.email, code)
        if sent:
            return redirect(url_for('auth.settings', tab='account', deletion_sent='1'))
    except Exception:
        logger.warning('Account deletion challenge failed')
    return redirect(url_for(
        'auth.settings', tab='account',
        deletion_error=MESSAGES['DELETION_CODE_SEND_FAILED'],
    ))


@auth_bp.route('/settings/delete/cancel', methods=['POST'])
@login_required
def delete_account_cancel():
    get_services().auth_service.cancel_account_deletion(current_user)
    return redirect(url_for('auth.settings', tab='account'))


@auth_bp.route('/settings/delete/verify', methods=['POST'])
@login_required
@limiter.limit(
    '5 per 15 minutes', key_func=lambda: f'deletion:{current_user.get_id() or ""}',
    error_message=MESSAGES['RATE_LIMIT_AUTH_VERIFY'],
)
def delete_account_verify():
    form = VerifyCodeForm(request.form)
    fallback = url_for('auth.settings', tab='account', deletion_sent='1')
    if not form.validate():
        return redirect(url_for(
            'auth.settings', tab='account', deletion_sent='1',
            deletion_error=MESSAGES['DELETION_INVALID_CODE'],
        ))
    try:
        success, message = get_services().auth_service.confirm_account_deletion(
            current_user, form.get_cleaned_data()['code'],
        )
    except SQLAlchemyError:
        get_services().user_repo.db.session.rollback()
        logger.warning('Account deletion failed')
        success, message = False, MESSAGES['OPERATION_FAILED']
    if success:
        logout_user()
        session.clear()
        session['_remember'] = 'clear'
        flash(MESSAGES['DELETION_CONFIRMED'], 'success')
        return redirect(url_for('auth.login'))
    flash(message or MESSAGES['DELETION_INVALID_CODE'], 'warning')
    return redirect(fallback)
