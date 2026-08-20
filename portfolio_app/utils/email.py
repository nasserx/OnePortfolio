"""Secret-free email delivery helpers for OnePortfolio OTP workflows."""

import logging

from flask_mail import Message

from portfolio_app import mail


logger = logging.getLogger(__name__)


def send_authentication_email(recipient_email: str, code: str) -> bool:
    body = (
        "Use this code to continue to OnePortfolio:\n\n"
        f"  {code}\n\n"
        "This code expires in 10 minutes and can be used once. "
        "If you did not request it, ignore this email."
    )
    return _send_code_message(
        recipient_email,
        "OnePortfolio - Your verification code",
        body,
        'Authentication code delivery failed',
    )


def send_verification_email(recipient_email: str, code: str) -> bool:
    body = (
        "Use this code to verify your new OnePortfolio email address:\n\n"
        f"  {code}\n\n"
        "This code expires in 10 minutes. "
        "If you did not request this change, ignore this email."
    )
    return _send_code_message(
        recipient_email,
        "OnePortfolio - Verify your email",
        body,
        'Email verification delivery failed',
    )


def send_deletion_confirmation_email(recipient_email: str, code: str) -> bool:
    body = (
        "Account deletion was requested for your OnePortfolio account.\n\n"
        f"Confirmation code:  {code}\n\n"
        "This code expires in 10 minutes. "
        "If you did not request this, ignore this email."
    )
    return _send_code_message(
        recipient_email,
        "OnePortfolio - Account deletion confirmation",
        body,
        'Account deletion code delivery failed',
    )


def _send_code_message(recipient: str, subject: str, body: str,
                       failure_message: str) -> bool:
    try:
        mail.send(Message(subject=subject, recipients=[recipient], body=body))
        return True
    except Exception:
        # Recipient, code, provider exception text, and provider details are
        # intentionally excluded from application logs.
        logger.warning(failure_message)
        return False
