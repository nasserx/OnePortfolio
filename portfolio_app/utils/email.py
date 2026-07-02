"""Email utilities for sending verification codes and password reset emails.

All email content is written in English as required.
Each email clearly states its purpose, the required action,
and ends with a disclaimer for unintended recipients.
"""

import logging
from flask import current_app
from flask_mail import Message
from portfolio_app import mail

logger = logging.getLogger(__name__)


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

def send_verification_email(recipient_email: str, code: str) -> bool:
    """Send a 6-digit verification code to the given email address.

    Args:
        recipient_email: The user's email address.
        code: The 6-digit OTP code to include in the email.

    Returns:
        True if sent successfully, False otherwise.
    """
    msg = Message(
        subject="OnePortfolio - Email Verification Code",
        recipients=[recipient_email],
        body=_build_verification_body(code),
    )
    try:
        mail.send(msg)
        logger.info("Verification code sent to %s", recipient_email)
        return True
    except Exception:
        logger.exception("Failed to send verification code to %s", recipient_email)
        return False


def send_deletion_confirmation_email(recipient_email: str, code: str) -> bool:
    """Send a 6-digit account deletion confirmation code.

    Args:
        recipient_email: The user's email address.
        code: The 6-digit OTP code to include in the email.

    Returns:
        True if sent successfully, False otherwise.
    """
    body = (
        "Account deletion was requested for your OnePortfolio account.\n\n"
        f"Confirmation code:  {code}\n\n"
        "Expires in 10 minutes. If you did not request this, ignore this email."
    )
    msg = Message(
        subject="OnePortfolio - Account Deletion Confirmation",
        recipients=[recipient_email],
        body=body,
    )
    try:
        mail.send(msg)
        logger.info("Deletion confirmation code sent to %s", recipient_email)
        return True
    except Exception:
        logger.exception("Failed to send deletion confirmation code to %s", recipient_email)
        return False


def send_reset_email(recipient_email: str, token: str) -> bool:
    """Send a password reset link to the given email address.

    Args:
        recipient_email: The user's email address.
        token: The signed password reset token.

    Returns:
        True if sent successfully, False otherwise.
    """
    base_url = current_app.config.get('APP_BASE_URL', '')
    reset_url = f"{base_url}/reset-password/{token}"

    msg = Message(
        subject="OnePortfolio - Password Reset",
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
