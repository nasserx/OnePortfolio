"""Email utilities for sending verification and password reset emails.

All email content is written in English as required.
Each email clearly states its purpose, the required action,
and ends with a disclaimer for unintended recipients.
"""

import logging
from flask import current_app
from flask_mail import Message
from portfolio_app import mail

logger = logging.getLogger(__name__)


def _build_verification_body(verification_url: str) -> str:
    """Build the plain-text body for an account verification email."""
    return (
        "This email was sent to verify your OnePortfolio account.\n\n"
        "Please click the link below to activate your account:\n"
        f"{verification_url}\n\n"
        "This link will expire in 24 hours.\n\n"
        "If you did not request this, please ignore this email."
    )


def _build_reset_body(reset_url: str) -> str:
    """Build the plain-text body for a password reset email."""
    return (
        "This email was sent because a password reset was requested for your OnePortfolio account.\n\n"
        "Please click the link below to set a new password:\n"
        f"{reset_url}\n\n"
        "This link will expire in 1 hour.\n\n"
        "If you did not request this, please ignore this email."
    )


def send_verification_email(recipient_email: str, token: str) -> bool:
    """Send an account verification email containing a signed token link.

    Args:
        recipient_email: The user's email address.
        token: The signed verification token.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    base_url = current_app.config.get('APP_BASE_URL', '')
    verification_url = f"{base_url}/verify/{token}"

    msg = Message(
        subject="Verify your OnePortfolio account",
        recipients=[recipient_email],
        body=_build_verification_body(verification_url),
    )

    try:
        mail.send(msg)
        logger.info("Verification email sent to %s", recipient_email)
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", recipient_email)
        return False


def send_reset_email(recipient_email: str, token: str) -> bool:
    """Send a password reset email containing a signed token link.

    Args:
        recipient_email: The user's email address.
        token: The signed password reset token.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    base_url = current_app.config.get('APP_BASE_URL', '')
    reset_url = f"{base_url}/reset-password/{token}"

    msg = Message(
        subject="Reset your OnePortfolio password",
        recipients=[recipient_email],
        body=_build_reset_body(reset_url),
    )

    try:
        mail.send(msg)
        logger.info("Password reset email sent to %s", recipient_email)
        return True
    except Exception:
        logger.exception("Failed to send password reset email to %s", recipient_email)
        return False
