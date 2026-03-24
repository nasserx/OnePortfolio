"""Email utilities for sending verification codes and password reset emails.

All email content is written in English as required.
Each email clearly states its purpose, the required action,
and ends with a disclaimer for unintended recipients.

Emails are sent asynchronously in a background thread so the HTTP request
returns immediately and the user is not left waiting.
"""

import logging
import threading
from flask import current_app
from flask_mail import Message
from portfolio_app import mail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async sending helper
# ---------------------------------------------------------------------------

def _send_async(app, msg: Message) -> None:
    """Send a mail message inside a new app context (runs in a background thread).

    Args:
        app: The Flask application object (not current_app proxy).
        msg: The Message instance to send.
    """
    with app.app_context():
        try:
            mail.send(msg)
            logger.info("Email sent to %s — subject: %s", msg.recipients, msg.subject)
        except Exception:
            logger.exception(
                "Failed to send email to %s — subject: %s",
                msg.recipients, msg.subject,
            )


def _dispatch(msg: Message) -> None:
    """Dispatch a message in a daemon background thread.

    Args:
        msg: The Message instance to send.
    """
    # Capture the real app object; current_app is a proxy and cannot be passed to threads.
    app = current_app._get_current_object()
    thread = threading.Thread(target=_send_async, args=(app, msg), daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Email body builders
# ---------------------------------------------------------------------------

def _build_verification_body(code: str) -> str:
    """Build the plain-text body for a verification code email."""
    return (
        "This email was sent to verify your OnePortfolio account.\n\n"
        "Your verification code is:\n\n"
        f"  {code}\n\n"
        "This code will expire in 10 minutes.\n\n"
        "If you did not create an account, please ignore this email."
    )


def _build_reset_body(reset_url: str) -> str:
    """Build the plain-text body for a password reset email."""
    return (
        "This email was sent because a password reset was requested "
        "for your OnePortfolio account.\n\n"
        "Please click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        "This link will expire in 1 hour.\n\n"
        "If you did not request this, please ignore this email."
    )


# ---------------------------------------------------------------------------
# Public send functions
# ---------------------------------------------------------------------------

def send_verification_email(recipient_email: str, code: str) -> None:
    """Send a 6-digit verification code to the given email address.

    The email is dispatched asynchronously; this function returns immediately.

    Args:
        recipient_email: The user's email address.
        code: The 6-digit OTP code to include in the email.
    """
    msg = Message(
        subject="OnePortfolio - Email Verification Code",
        recipients=[recipient_email],
        body=_build_verification_body(code),
    )
    _dispatch(msg)
    logger.info("Verification code email dispatched to %s", recipient_email)


def send_reset_email(recipient_email: str, token: str) -> None:
    """Send a password reset link to the given email address.

    The email is dispatched asynchronously; this function returns immediately.

    Args:
        recipient_email: The user's email address.
        token: The signed password reset token.
    """
    base_url = current_app.config.get('APP_BASE_URL', '')
    reset_url = f"{base_url}/reset-password/{token}"

    msg = Message(
        subject="OnePortfolio - Password Reset",
        recipients=[recipient_email],
        body=_build_reset_body(reset_url),
    )
    _dispatch(msg)
    logger.info("Password reset email dispatched to %s", recipient_email)
