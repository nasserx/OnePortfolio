"""Admin blueprint — user management for admins."""

import logging
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from portfolio_app.services import get_services
from portfolio_app.utils.tokens import generate_reset_token
from portfolio_app.utils.email import send_reset_email
from portfolio_app.utils.messages import AdminMessages

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Decorator: allow access only to admin users."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Admin user list page."""
    svc = get_services()
    all_users = svc.user_repo.get_all()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/users/<int:user_id>/send-reset-email', methods=['POST'])
@login_required
@admin_required
def send_reset(user_id):
    """Send a password reset email to the user on behalf of the admin."""
    svc = get_services()
    try:
        user = svc.user_repo.get_by_id(user_id)
        if not user:
            flash(AdminMessages.USER_NOT_FOUND, 'error')
            return redirect(url_for('admin.users'))

        if not user.email:
            flash(AdminMessages.NO_EMAIL_ON_FILE.format(username=user.username), 'warning')
            return redirect(url_for('admin.users'))

        token = generate_reset_token(user.email)
        email_sent = send_reset_email(user.email, token)

        if email_sent:
            flash(AdminMessages.RESET_EMAIL_SENT.format(username=user.username, email=user.email), 'success')
        else:
            flash(AdminMessages.EMAIL_SEND_FAILED, 'danger')

    except Exception:
        logger.exception('Admin send reset email failed for user %s', user_id)
        flash(AdminMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    """Toggle admin status for a user."""
    svc = get_services()
    try:
        user = svc.auth_service.toggle_admin(user_id, current_user)
        msg = AdminMessages.ADMIN_ACCESS_GRANTED if user.is_admin else AdminMessages.ADMIN_ACCESS_REVOKED
        flash(msg.format(username=user.username), 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Toggle admin failed for user %s', user_id)
        flash(AdminMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user account."""
    svc = get_services()
    try:
        svc.auth_service.delete_user(user_id, current_user)
        flash(AdminMessages.USER_DELETED, 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception:
        logger.exception('Admin delete user failed for user %s', user_id)
        flash(AdminMessages.OPERATION_FAILED, 'error')

    return redirect(url_for('admin.users'))


@admin_bp.errorhandler(403)
def forbidden(e):
    return render_template('auth/login.html',
                           form_errors={'__all__': AdminMessages.ACCESS_DENIED},
                           form_values={}), 403
