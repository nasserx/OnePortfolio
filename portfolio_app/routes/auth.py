"""Auth blueprint — login, register, logout, change password,
email verification (6-digit OTP), forgot password, reset password,
user settings, and account deletion.
"""

import logging
from collections.abc import Mapping
from functools import wraps
from urllib.parse import urlparse
from flask import Blueprint, abort, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter.util import get_remote_address
from authlib.integrations.base_client import MismatchingStateError, OAuthError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from portfolio_app import get_oauth, limiter
from portfolio_app.services import get_services
from portfolio_app.utils.constants import DEMO_USERNAME
from portfolio_app.forms.auth_forms import (
    LoginForm,
    RegisterForm,
    ChangePasswordForm,
    GoogleDisconnectForm,
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
from portfolio_app.utils.messages import MESSAGES

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)
_GOOGLE_OAUTH_NEXT_SESSION_KEY = 'google_oauth_next'
_GOOGLE_OAUTH_PROVIDER = 'google'


def _safe_local_redirect(target):
    """Return a safe local redirect path, or None for unsafe values."""
    if not target:
        return None
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or not target.startswith('/')
        or target.startswith('//')
        or target.startswith('/\\')
    ):
        return None
    return target


def _google_oauth_client_or_404():
    if not current_app.config.get('GOOGLE_OAUTH_ENABLED'):
        abort(404)
    google = get_oauth().create_client('google')
    if google is None:
        abort(404)
    return google


def _google_oauth_available():
    if not current_app.config.get('GOOGLE_OAUTH_ENABLED'):
        return False
    return get_oauth().create_client('google') is not None


def _redirect_to_login_with_google_failure(message_key='GOOGLE_SIGNIN_FAILED'):
    flash(MESSAGES[message_key], 'warning')
    return redirect(url_for('auth.login'))


def _login_google_linked_user(identity, next_page):
    user = identity.user
    if not user or not user.is_verified:
        return _redirect_to_login_with_google_failure()

    login_user(user, remember=False)
    return redirect(next_page or url_for('dashboard.index'))


def _identity_links_same_user_and_subject(identity, user_id, subject):
    return (
        identity is not None
        and identity.user_id == user_id
        and identity.provider_subject == subject
    )


def _create_google_identity_or_resolve_race(svc, user, subject):
    identity_repo = svc.oauth_identity_repo
    identity_repo.create(user.id, _GOOGLE_OAUTH_PROVIDER, subject)
    try:
        identity_repo.commit()
    except IntegrityError:
        identity_repo.db.session.rollback()
        by_subject = identity_repo.get_by_provider_subject(
            _GOOGLE_OAUTH_PROVIDER,
            subject,
        )
        by_user = identity_repo.get_for_user_and_provider(
            user.id,
            _GOOGLE_OAUTH_PROVIDER,
        )
        if (
            by_subject is not None
            and by_user is not None
            and by_subject.id == by_user.id
            and _identity_links_same_user_and_subject(by_subject, user.id, subject)
        ):
            return by_subject
        return None

    return identity_repo.get_by_provider_subject(_GOOGLE_OAUTH_PROVIDER, subject)


def demo_restricted(f):
    """Block demo account from mutating credentials; redirect to settings with a warning."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and current_user.username == DEMO_USERNAME:
            flash(MESSAGES['DEMO_ACTION_DISABLED'], 'warning')
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
@limiter.limit(
    "10 per 5 minutes",
    methods=['POST'],
    key_func=get_remote_address,
    error_message=MESSAGES['ACCOUNT_LOCKED'],
)
def login():
    """Login page. Blocks unverified accounts.

    The per-IP rate limit raises the cost of brute-force sweeps and
    blunts the lockout-DoS pattern (where any IP that knows a username
    could trip the per-account lockout in five POSTs). The per-account
    lockout still applies on top, so a distributed attacker is still
    rejected — they just can't bring the lockout down on a single user
    from a single host.
    """
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

            if result == 'locked':
                form_errors['__all__'] = MESSAGES['ACCOUNT_LOCKED']
                form_values = request.form
            elif result == 'pending':
                # The identifier matches a staged sign-up that was never
                # confirmed. The previous behaviour redirected to
                # /verify-code?email=..., which leaked that the email
                # exists in pending state — a clean enumeration oracle.
                # Collapse this into the same generic invalid-credentials
                # response; the legitimate user already received the OTP
                # by email when they signed up and can navigate there.
                form_errors['__all__'] = MESSAGES['INVALID_CREDENTIALS']
                form_values = request.form
            elif isinstance(result, str):
                # Defensive: any other sentinel string is treated as a soft block.
                form_errors['__all__'] = MESSAGES['INVALID_CREDENTIALS']
                form_values = request.form
            elif result:
                remember = request.form.get('remember') == 'on'
                login_user(result, remember=remember)
                # Open-redirect / dangerous-scheme defence. Accept ONLY a
                # plain relative path: starts with '/', is not protocol-
                # relative ('//evil.com'), is not backslash-prefixed
                # ('/\\evil.com' — Windows quirk), and the parsed URL has
                # no scheme/netloc. The previous netloc-only check let
                # 'javascript:alert(1)' through (empty netloc) — Safari
                # historically followed that as a Location header.
                next_page = _safe_local_redirect(request.args.get('next'))
                redirect_url = next_page or url_for('dashboard.index')
                if from_modal:
                    return jsonify({'ok': True, 'redirect': redirect_url})
                return redirect(redirect_url)
            else:
                form_errors['__all__'] = MESSAGES['INVALID_CREDENTIALS']
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
        google_oauth_available=_google_oauth_available(),
        safe_next=_safe_local_redirect(request.args.get('next')),
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
@limiter.limit("5 per hour", methods=['POST'], error_message=MESSAGES['RATE_LIMIT_SIGNUP'])
def register():
    """Register new account. Sends a 6-digit verification code on success.

    Rate-limited to 5 sign-up attempts per IP per hour. Sign-ups stage in
    the ``pending_registration`` table; the user record is only created
    after the OTP is confirmed.
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        from_modal = bool(request.form.get('_modal'))
        svc = get_services()

        def _email_taken(e: str) -> bool:
            return svc.user_repo.get_by_email(e) is not None

        form = RegisterForm(
            request.form,
            check_email_taken=_email_taken,
        )

        if form.validate():
            data = form.get_cleaned_data()
            try:
                pending, code = svc.auth_service.register(
                    data['email'],
                    data['password'],
                )

                email_sent = send_verification_email(pending.email, code)
                if not email_sent:
                    logger.error('Verification email failed for %s', pending.email)

                verify_url = url_for('auth.verify_code', email=pending.email)
                if from_modal:
                    return jsonify({'ok': True, 'redirect': verify_url})
                return redirect(verify_url)

            except ValueError as e:
                form_errors['__all__'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Registration failed')
                form_errors['__all__'] = MESSAGES['REGISTRATION_FAILED']
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


@auth_bp.route('/auth/google')
@limiter.limit("10 per 5 minutes", key_func=get_remote_address, error_message=MESSAGES['ACCOUNT_LOCKED'])
def google_signin():
    """Begin Google OAuth sign-in for existing accounts only."""
    google = _google_oauth_client_or_404()
    next_page = _safe_local_redirect(request.args.get('next'))
    if next_page:
        session[_GOOGLE_OAUTH_NEXT_SESSION_KEY] = next_page
    else:
        session.pop(_GOOGLE_OAUTH_NEXT_SESSION_KEY, None)

    redirect_uri = current_app.config['GOOGLE_REDIRECT_URI']
    return google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def google_callback():
    """Complete Google OAuth sign-in for an existing verified local account."""
    google = _google_oauth_client_or_404()
    next_page = _safe_local_redirect(
        session.pop(_GOOGLE_OAUTH_NEXT_SESSION_KEY, None)
    )

    try:
        token = google.authorize_access_token()
        if not isinstance(token, Mapping):
            return _redirect_to_login_with_google_failure()
        identity = token.get('userinfo')
    except (OAuthError, MismatchingStateError, TypeError, ValueError) as exc:
        logger.info(
            'Google OAuth authorization failed: %s',
            type(exc).__name__,
        )
        return _redirect_to_login_with_google_failure()

    if not isinstance(identity, Mapping):
        return _redirect_to_login_with_google_failure()

    subject = identity.get('sub')
    if not isinstance(subject, str) or not subject:
        return _redirect_to_login_with_google_failure()

    email = (identity.get('email') or '').strip().lower()
    if not email or identity.get('email_verified') is not True:
        return _redirect_to_login_with_google_failure()

    svc = get_services()
    identity_link = svc.oauth_identity_repo.get_by_provider_subject(
        _GOOGLE_OAUTH_PROVIDER,
        subject,
    )
    if identity_link is not None:
        return _login_google_linked_user(identity_link, next_page)

    user = svc.user_repo.get_by_email(email)
    if not user or not user.is_verified:
        return _redirect_to_login_with_google_failure('GOOGLE_SIGNIN_NO_ACCOUNT')

    existing_user_link = svc.oauth_identity_repo.get_for_user_and_provider(
        user.id,
        _GOOGLE_OAUTH_PROVIDER,
    )
    if existing_user_link is not None:
        if existing_user_link.provider_subject == subject:
            return _login_google_linked_user(existing_user_link, next_page)
        return _redirect_to_login_with_google_failure()

    identity_link = _create_google_identity_or_resolve_race(svc, user, subject)
    if not _identity_links_same_user_and_subject(identity_link, user.id, subject):
        return _redirect_to_login_with_google_failure()

    login_user(user, remember=False)
    return redirect(next_page or url_for('dashboard.index'))


@auth_bp.route('/verify-code', methods=['GET', 'POST'])
@limiter.limit(
    "5 per 15 minutes",
    methods=['POST'],
    key_func=lambda: (request.args.get('email', '') or request.form.get('email', '') or '').lower(),
    error_message=MESSAGES['ACCOUNT_LOCKED'],
)
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
                    flash(MESSAGES['EMAIL_UPDATED'], 'success')
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
@limiter.limit(
    "3 per hour",
    key_func=lambda: (request.args.get('email', '') or '').lower(),
    error_message=MESSAGES['RATE_LIMIT_RESEND'],
)
def resend_code():
    """Resend a fresh 6-digit verification code to the user's email.

    Rate-limited to 3 requests per email per hour.
    """
    email = request.args.get('email', '')

    if not email:
        return redirect(url_for('auth.register'))

    svc = get_services()
    new_code = svc.auth_service.resend_verification_code(email)

    if new_code:
        email_sent = send_verification_email(email, new_code)
        if email_sent:
            flash(MESSAGES['VERIFICATION_CODE_SENT'], 'success')
        else:
            flash(MESSAGES['VERIFICATION_CODE_SEND_FAILED'], 'danger')
    else:
        flash(MESSAGES['VERIFICATION_CODE_RESEND_UNAVAILABLE'], 'warning')

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
                # Rotate the session: invalidate the current cookie and
                # require the user to sign in again with the new password.
                # Without this, a stolen session cookie would survive a
                # password change — which is exactly the recovery action.
                logout_user()
                flash(MESSAGES['PASSWORD_CHANGED'], 'success')
                return redirect(url_for('auth.login'))
            except ValueError as e:
                form_errors['current_password'] = str(e)
                form_values = request.form
            except Exception:
                logger.exception('Password change failed')
                form_errors['__all__'] = MESSAGES['PASSWORD_CHANGE_FAILED']
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
                form_errors['__all__'] = MESSAGES['EMAIL_UPDATE_FAILED']
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
            # registered, to avoid leaking account existence. We also burn
            # equivalent CPU work for unknown emails (token generation runs
            # either way) so simple wall-clock probes can't tell the
            # difference. The SMTP send is still skipped for non-users —
            # use a Redis-backed async queue if perfect timing parity is
            # needed.
            generated_token = generate_reset_token(data['email'])
            if user:
                # Stamp a single-use jti on the user, embed it in the
                # signed link, and email it out. Any prior reset link
                # for this account is invalidated by the overwrite.
                jti = svc.auth_service.begin_password_reset(user)
                token = generate_reset_token(user.email, jti)
                send_reset_email(user.email, token)
            del generated_token

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

    # Validate the token up front so expired/tampered links show an error
    # immediately. We don't pre-check the jti against the user here — the
    # service does that under a single transaction so an attacker can't
    # race two redemptions of the same link.
    payload = verify_reset_token(token)
    if not payload:
        flash(MESSAGES['PASSWORD_RESET_LINK_INVALID'], 'danger')
        return redirect(url_for('auth.forgot_password'))
    email, jti = payload

    form_errors = {}
    form_values = {}

    if request.method == 'POST':
        form = ResetPasswordForm(request.form)
        if form.validate():
            data = form.get_cleaned_data()
            svc = get_services()
            user = svc.auth_service.reset_password_with_token(
                email, jti, data['password']
            )

            if not user:
                # Either the user is gone or the jti has already been
                # consumed (or never matched). Either way: same generic
                # invalid-link message — no oracle.
                flash(MESSAGES['PASSWORD_RESET_LINK_INVALID'], 'danger')
                return redirect(url_for('auth.forgot_password'))

            flash(MESSAGES['PASSWORD_RESET_SUCCESS'], 'success')
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
    svc = get_services()
    google_identity_linked = (
        svc.oauth_identity_repo.get_for_user_and_provider(
            current_user.id,
            _GOOGLE_OAUTH_PROVIDER,
        ) is not None
    )
    return render_template(
        'auth/settings.html',
        google_identity_linked=google_identity_linked,
        google_disconnect_form=GoogleDisconnectForm({}),
    )


@auth_bp.route('/settings/google/disconnect', methods=['POST'])
@login_required
@demo_restricted
def google_disconnect():
    """Disconnect the authenticated user's local Google identity link."""
    form = GoogleDisconnectForm(request.form)
    if not form.validate():
        first_error = next(iter(form.errors.values()), MESSAGES['INVALID_INPUT'])
        flash(first_error, 'warning')
        return redirect(url_for('auth.settings', tab='security'))

    data = form.get_cleaned_data()
    if not current_user.password_hash or not current_user.check_password(data['current_password']):
        flash(MESSAGES['CURRENT_PASSWORD_INCORRECT'], 'warning')
        return redirect(url_for('auth.settings', tab='security'))

    svc = get_services()
    identity = svc.oauth_identity_repo.get_for_user_and_provider(
        current_user.id,
        _GOOGLE_OAUTH_PROVIDER,
    )
    if identity is None:
        flash(MESSAGES['GOOGLE_DISCONNECT_NOT_CONNECTED'], 'info')
        return redirect(url_for('auth.settings', tab='security'))

    try:
        svc.oauth_identity_repo.delete(identity)
        svc.oauth_identity_repo.commit()
    except SQLAlchemyError as exc:
        svc.oauth_identity_repo.db.session.rollback()
        logger.warning(
            'Google OAuth disconnect failed: %s',
            type(exc).__name__,
        )
        flash(MESSAGES['GOOGLE_DISCONNECT_FAILED'], 'warning')
        return redirect(url_for('auth.settings', tab='security'))

    flash(MESSAGES['GOOGLE_DISCONNECT_SUCCESS'], 'success')
    return redirect(url_for('auth.settings', tab='security'))


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
                                deletion_error=MESSAGES['DELETION_NO_EMAIL']))

    svc = get_services()
    try:
        code = svc.auth_service.request_account_deletion(current_user)
        sent = send_deletion_confirmation_email(current_user.email, code)

        if sent:
            return redirect(url_for('auth.settings', tab='account', deletion_sent='1'))
        return redirect(url_for('auth.settings', tab='account',
                                deletion_error=MESSAGES['DELETION_CODE_SEND_FAILED']))
    except Exception:
        logger.exception('Failed to request account deletion for user %s', current_user.id)
        return redirect(url_for('auth.settings', tab='account',
                                deletion_error=MESSAGES['DELETION_CODE_SEND_FAILED']))


@auth_bp.route('/settings/delete/cancel', methods=['POST'])
@login_required
def delete_account_cancel():
    """Cancel the in-progress account deletion flow."""
    return redirect(url_for('auth.settings', tab='account'))


@auth_bp.route('/settings/delete/verify', methods=['POST'])
@login_required
@demo_restricted
@limiter.limit(
    "5 per 15 minutes",
    key_func=lambda: f"deletion:{current_user.get_id() or ''}",
    error_message=MESSAGES['ACCOUNT_LOCKED'],
)
def delete_account_verify():
    """Delete the authenticated account after a valid deletion OTP."""
    form = VerifyCodeForm(request.form)

    def _verify_error(msg: str):
        return redirect(url_for('auth.settings', tab='account', deletion_sent='1',
                                deletion_error=msg))

    if not form.validate():
        first_error = next(iter(form.errors.values()), MESSAGES['DELETION_INVALID_CODE'])
        return _verify_error(first_error)

    svc = get_services()
    user = svc.user_repo.get_by_id(current_user.id)
    if not user:
        return _verify_error(MESSAGES['DELETION_INVALID_CODE'])

    data = form.get_cleaned_data()
    try:
        success, error_msg = svc.auth_service.confirm_account_deletion(user, data['code'])
    except SQLAlchemyError:
        svc.user_repo.db.session.rollback()
        logger.exception('Failed to delete account for user %s', current_user.id)
        return _verify_error(MESSAGES['OPERATION_FAILED'])

    if success:
        logout_user()
        flash(MESSAGES['DELETION_CONFIRMED'], 'success')
        return redirect(url_for('auth.login'))

    return _verify_error(error_msg or MESSAGES['DELETION_INVALID_CODE'])
