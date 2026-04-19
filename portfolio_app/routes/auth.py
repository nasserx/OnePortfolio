"""Auth blueprint — login, register, logout, change password,
email verification (6-digit OTP), forgot password, reset password,
user settings, and account deletion.
"""

import logging
from functools import wraps
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from portfolio_app.services import get_services
from portfolio_app.utils.constants import DEMO_USERNAME
from portfolio_app.forms.auth_forms import (
    LoginForm,
    RegisterForm,
    ChangePasswordForm,
    ConfirmDeletionForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    VerifyCodeForm,
    UpdateEmailForm,
)
from portfolio_app.utils.tokens import generate_reset_token, verify_reset_token
from portfolio_app.utils.email import (
    send_deletion_confirmation_email,
    send_verification_email,
    send_reset_email,
)
from portfolio_app.utils.messages import AccountMessages, AuthMessages

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


def demo_restricted(f):
    """Block demo account from mutating credentials; redirect to settings with a warning."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and current_user.username == DEMO_USERNAME:
            flash(AccountMessages.DEMO_ACTION_DISABLED, 'warning')
            return redirect(url_for('auth.settings'))
        return f(*args, **kwargs)
    return decorated


@auth_bp.app_context_processor
def inject_demo_flag():
    """Expose ``is_demo_account`` to all templates rendered by this blueprint."""
    return {
        'is_demo_account': (
            current_user.is_authenticated and current_user.username == DEMO_USERNAME
        )
    }


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page. Blocks unverified accounts."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        from_modal = bool(request.form.get('_modal'))
        form = LoginForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            result = svc.auth_service.authenticate(data['username'], data['password'])

            if result == 'unverified':
                # Redirect to the code entry page so the user can verify immediately
                user = svc.user_repo.get_by_username_or_email(data['username'])
                if user and user.email:
                    verify_url = url_for('auth.verify_code', email=user.email)
                    if from_modal:
                        return jsonify({'ok': True, 'redirect': verify_url})
                    return redirect(verify_url)
                form_errors['__all__'] = AuthMessages.ACCOUNT_UNVERIFIED
                form_values = request.form
            elif result:
                remember = request.form.get('remember') == 'on'
                login_user(result, remember=remember)
                next_page = request.args.get('next')
                if next_page and urlparse(next_page).netloc:
                    next_page = None  # reject absolute URLs — open redirect prevention
                redirect_url = next_page or url_for('dashboard.index')
                if from_modal:
                    return jsonify({'ok': True, 'redirect': redirect_url})
                return redirect(redirect_url)
            else:
                form_errors['__all__'] = AuthMessages.INVALID_CREDENTIALS
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

        if from_modal:
            return jsonify({'ok': False, 'errors': form_errors}), 422

    return render_template(
        'auth/login.html',
        form_errors=form_errors,
        form_values=form_values,
    )


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Logout (CSRF-protected POST)."""
    logout_user()
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Register + Email Verification (6-digit OTP)
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Register new account. Sends a 6-digit verification code on success."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        from_modal = bool(request.form.get('_modal'))
        svc = get_services()

        form = RegisterForm(
            request.form,
            check_username_taken=lambda u: svc.user_repo.get_by_username(u) is not None,
            check_email_taken=lambda e: svc.user_repo.get_by_email(e) is not None,
        )

        if form.validate():
            data = form.get_cleaned_data()
            try:
                user, code = svc.auth_service.register(
                    data['username'],
                    data['email'],
                    data['password'],
                )

                email_sent = send_verification_email(user.email, code)
                if not email_sent:
                    logger.error('Verification email failed for %s', user.email)

                verify_url = url_for('auth.verify_code', email=user.email)
                if from_modal:
                    return jsonify({'ok': True, 'redirect': verify_url})
                return redirect(verify_url)

            except ValueError as e:
                # If the email belongs to an unverified account, resend a fresh code
                # instead of blocking the user with an "already taken" error.
                email = data.get('email', '')
                if email:
                    existing = svc.user_repo.get_by_email(email)
                    if existing and not existing.is_verified:
                        new_code = svc.auth_service.resend_verification_code(existing.email)
                        if new_code:
                            send_verification_email(existing.email, new_code)
                        verify_url = url_for('auth.verify_code', email=existing.email)
                        if from_modal:
                            return jsonify({'ok': True, 'redirect': verify_url})
                        return redirect(verify_url)

                form_errors['__all__'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Registration failed')
                form_errors['__all__'] = AuthMessages.REGISTRATION_FAILED
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

        if from_modal:
            return jsonify({'ok': False, 'errors': form_errors}), 422

    return render_template(
        'auth/register.html',
        form_errors=form_errors,
        form_values=form_values,
    )


@auth_bp.route('/verify-code', methods=['GET', 'POST'])
def verify_code():
    """Page where the user enters the 6-digit verification code."""
    email = request.args.get('email', '')

    if not email:
        return redirect(url_for('auth.register'))

    form_errors = {}

    if request.method == 'POST':
        form = VerifyCodeForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            success, error_msg = svc.auth_service.verify_user(email, data['code'])

            if success:
                # If the user is already logged in this was a pending email update —
                # the email has been applied; send them back to settings.
                if current_user.is_authenticated:
                    flash(AuthMessages.EMAIL_UPDATED, 'success')
                    return redirect(url_for('auth.settings', tab='security'))

                # Otherwise this was a registration verification — auto-login.
                verified_user = svc.user_repo.get_by_email(email)
                if verified_user:
                    login_user(verified_user)
                    return redirect(url_for('dashboard.index'))
            else:
                form_errors['code'] = error_msg
        else:
            form_errors = form.errors

    return render_template(
        'auth/verify_code.html',
        email=email,
        form_errors=form_errors,
    )


@auth_bp.route('/resend-code')
def resend_code():
    """Resend a fresh 6-digit verification code to the user's email."""
    email = request.args.get('email', '')

    if not email:
        return redirect(url_for('auth.register'))

    svc = get_services()
    new_code = svc.auth_service.resend_verification_code(email)

    if new_code:
        email_sent = send_verification_email(email, new_code)
        if email_sent:
            flash(AuthMessages.VERIFICATION_CODE_SENT, 'success')
        else:
            flash(AuthMessages.CODE_SEND_FAILED, 'danger')
    else:
        flash(AuthMessages.RESEND_UNAVAILABLE, 'warning')

    return redirect(url_for('auth.verify_code', email=email))


# ---------------------------------------------------------------------------
# Change Password (logged-in users)
# ---------------------------------------------------------------------------

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@demo_restricted
def change_password():
    """Change password page."""
    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        form = ChangePasswordForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            try:
                svc.auth_service.change_password(
                    current_user,
                    data['current_password'],
                    data['new_password'],
                )
                flash(AuthMessages.PASSWORD_CHANGED, 'success')
                return redirect(url_for('dashboard.index'))
            except ValueError as e:
                form_errors['current_password'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Password change failed')
                form_errors['__all__'] = AuthMessages.ERROR_OCCURRED
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

    return render_template(
        'auth/change_password.html',
        form_errors=form_errors,
        form_values=form_values,
    )


# ---------------------------------------------------------------------------
# Update Email
# ---------------------------------------------------------------------------

@auth_bp.route('/update-email', methods=['GET', 'POST'])
@login_required
@demo_restricted
def update_email():
    """Stage a new email address and send an OTP to verify it.

    The current email is not changed until the user confirms the OTP on the
    verify-code page. The user stays logged in throughout the flow.
    """
    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        svc = get_services()

        form = UpdateEmailForm(
            request.form,
            check_email_taken=lambda e: (
                svc.user_repo.get_by_email(e) is not None or
                svc.user_repo.get_by_pending_email(e) is not None
            ),
        )

        if form.validate():
            data = form.get_cleaned_data()
            try:
                code = svc.auth_service.update_email(
                    current_user,
                    data['email'],
                    data['password'],
                )
                send_verification_email(data['email'], code)

                # Stay logged in — email is only applied after OTP confirmation
                return redirect(url_for('auth.verify_code', email=data['email']))

            except ValueError as e:
                form_errors['password'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Email update failed')
                form_errors['__all__'] = AuthMessages.ERROR_OCCURRED
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

    return render_template(
        'auth/update_email.html',
        form_errors=form_errors,
        form_values=form_values,
        current_email=current_user.email,
    )


# ---------------------------------------------------------------------------
# Forgot Password / Reset Password
# ---------------------------------------------------------------------------

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page. Sends a reset link to the user's email."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        from_modal = bool(request.form.get('_modal'))
        form = ForgotPasswordForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            user = svc.user_repo.get_by_email(data['email'])

            # Always respond the same way regardless of whether the email is
            # registered, to avoid leaking account existence.
            if user:
                token = generate_reset_token(user.email)
                send_reset_email(user.email, token)

            if from_modal:
                return jsonify({'ok': True})
            return redirect(url_for('auth.reset_sent'))
        else:
            form_errors = form.errors
            form_values = request.form

        if from_modal:
            return jsonify({'ok': False, 'errors': form_errors}), 422

    return render_template(
        'auth/forgot_password.html',
        form_errors=form_errors,
        form_values=form_values,
    )


@auth_bp.route('/reset-sent')
def reset_sent():
    """Confirmation page shown after a password reset email has been sent."""
    return render_template('auth/reset_sent.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password page. Validates the token then allows setting a new password."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    # Validate the token up front so expired links show an error immediately
    email = verify_reset_token(token)
    if not email:
        flash(AuthMessages.RESET_LINK_INVALID, 'danger')
        return redirect(url_for('auth.forgot_password'))

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        form = ResetPasswordForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            user = svc.auth_service.reset_password_with_token(email, data['password'])

            if not user:
                flash(AuthMessages.RESET_ACCOUNT_NOT_FOUND, 'danger')
                return redirect(url_for('auth.forgot_password'))

            flash(AuthMessages.PASSWORD_RESET_SUCCESS, 'success')
            return redirect(url_for('auth.login'))
        else:
            form_errors = form.errors
            form_values = request.form

    return render_template(
        'auth/reset_password.html',
        token=token,
        form_errors=form_errors,
        form_values=form_values,
    )


# ---------------------------------------------------------------------------
# User Settings
# ---------------------------------------------------------------------------

@auth_bp.route('/settings')
@login_required
def settings():
    """User settings page with profile, security, and account tabs."""
    return render_template('auth/settings.html')


# ---------------------------------------------------------------------------
# Account Deletion (OTP-confirmed)
# ---------------------------------------------------------------------------

@auth_bp.route('/settings/delete/request', methods=['POST'])
@login_required
@demo_restricted
def delete_account_request():
    """Send a 6-digit OTP to the user's email to confirm account deletion."""
    if not current_user.email:
        return redirect(url_for('auth.settings', tab='account',
                                deletion_error=AccountMessages.DELETION_NO_EMAIL))

    svc = get_services()
    try:
        code = svc.auth_service.request_account_deletion(current_user)
        sent = send_deletion_confirmation_email(current_user.email, code)

        if sent:
            return redirect(url_for('auth.settings', tab='account', deletion_sent='1'))
        return redirect(url_for('auth.settings', tab='account',
                                deletion_error=AccountMessages.DELETION_CODE_SEND_FAILED))
    except Exception:
        logger.exception('Failed to request account deletion for user %s', current_user.id)
        return redirect(url_for('auth.settings', tab='account',
                                deletion_error=AccountMessages.DELETION_CODE_SEND_FAILED))


@auth_bp.route('/settings/delete/confirm', methods=['POST'])
@login_required
@demo_restricted
def delete_account_confirm():
    """Verify the OTP and permanently delete the authenticated user's account."""
    form = ConfirmDeletionForm(request.form)

    def _deletion_error(msg: str):
        return redirect(url_for('auth.settings', tab='account', deletion_error=msg))

    if not form.validate():
        first_error = next(iter(form.errors.values()), AccountMessages.DELETION_INVALID_CODE)
        return _deletion_error(first_error)

    data = form.get_cleaned_data()
    svc = get_services()

    # Fetch a fresh copy of the user before deletion so the OTP fields are current
    user = svc.user_repo.get_by_id(current_user.id)
    if not user:
        return _deletion_error(AccountMessages.DELETION_INVALID_CODE)

    success, error_msg = svc.auth_service.confirm_account_deletion(user, data['code'])

    if success:
        logout_user()
        flash(AccountMessages.DELETION_CONFIRMED, 'success')
        return redirect(url_for('auth.login'))

    return _deletion_error(error_msg or AccountMessages.DELETION_INVALID_CODE)
