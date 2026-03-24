"""Auth blueprint — login, register, logout, change password,
email verification (6-digit OTP), forgot password, and reset password.
"""

import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from portfolio_app.services import get_services
from portfolio_app.forms.auth_forms import (
    LoginForm,
    RegisterForm,
    ChangePasswordForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    VerifyCodeForm,
    UpdateEmailForm,
)
from portfolio_app.utils.tokens import generate_reset_token, verify_reset_token
from portfolio_app.utils.email import send_verification_email, send_reset_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


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
        form = LoginForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            result = svc.auth_service.authenticate(data['username'], data['password'])

            if result == 'unverified':
                # Redirect to the code entry page so the user can verify immediately
                user = svc.user_repo.get_by_username_or_email(data['username'])
                if user and user.email:
                    return redirect(url_for('auth.verify_code', email=user.email))
                form_errors['__all__'] = (
                    'Your account has not been verified yet. '
                    'Please check your email for the verification code.'
                )
                form_values = request.form
            elif result:
                remember = request.form.get('remember') == 'on'
                login_user(result, remember=remember)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard.index'))
            else:
                form_errors['__all__'] = 'Invalid username or password.'
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

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

                return redirect(url_for('auth.verify_code', email=user.email))

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
                        return redirect(url_for('auth.verify_code', email=existing.email))

                form_errors['__all__'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Registration failed')
                form_errors['__all__'] = 'Registration failed. Please try again.'
                form_values = request.form
        else:
            form_errors = form.errors
            form_values = request.form

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
                # Auto-login after successful verification
                svc2 = get_services()
                verified_user = svc2.user_repo.get_by_email(email)
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
            flash('A new verification code has been sent to your email.', 'success')
        else:
            flash('Failed to send the code. Please try again in a moment.', 'danger')
    else:
        flash('Unable to resend code. Your account may already be verified.', 'warning')

    return redirect(url_for('auth.verify_code', email=email))


# ---------------------------------------------------------------------------
# Change Password (logged-in users)
# ---------------------------------------------------------------------------

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
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
                flash('Password changed successfully.', 'success')
                return redirect(url_for('dashboard.index'))
            except ValueError as e:
                form_errors['current_password'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Password change failed')
                form_errors['__all__'] = 'An error occurred. Please try again.'
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
def update_email():
    """Update email page. Requires password confirmation, then sends a new OTP."""
    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        svc = get_services()

        form = UpdateEmailForm(
            request.form,
            check_email_taken=lambda e: svc.user_repo.get_by_email(e) is not None,
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

                # Log the user out so they must verify the new email before re-entering
                logout_user()
                return redirect(url_for('auth.verify_code', email=data['email']))

            except ValueError as e:
                form_errors['password'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Email update failed')
                form_errors['__all__'] = 'An error occurred. Please try again.'
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
        form = ForgotPasswordForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            user = svc.user_repo.get_by_email(data['email'])

            # Always redirect to the confirmation page regardless of whether
            # the email is registered, to avoid leaking account existence.
            if user:
                token = generate_reset_token(user.email)
                send_reset_email(user.email, token)

            return redirect(url_for('auth.reset_sent'))
        else:
            form_errors = form.errors
            form_values = request.form

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
        flash('The password reset link is invalid or has expired.', 'danger')
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
                flash('No account found for this reset link.', 'danger')
                return redirect(url_for('auth.forgot_password'))

            flash('Your password has been reset. You can now log in.', 'success')
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
