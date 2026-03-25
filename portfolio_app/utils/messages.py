"""Concise user-facing messages for the application.

All user-facing strings used in routes, forms, and templates must come from
one of the classes below — no hardcoded strings elsewhere.
"""


class ErrorMessages:
    """Concise error messages."""

    INVALID_QUANTITY = "Invalid quantity"
    INVALID_PRICE = "Invalid price"
    INVALID_AMOUNT = "Invalid amount"
    INVALID_DATE = "Invalid date"
    TRANSACTION_NOT_FOUND = "Transaction not found"
    FUND_NOT_FOUND = "Fund not found"
    INVALID_INPUT = "Invalid input"
    INVALID_SYMBOL = "Invalid symbol"
    OPERATION_FAILED = "Operation failed"
    EVENT_NOT_FOUND = "Event not found"
    INVALID_REQUEST = "Invalid request"
    INVALID_FUND_ID = "Invalid fund_id"
    USER_NOT_FOUND = "User not found"


class SuccessMessages:
    """Concise success messages."""

    # Transaction / operation messages (buy, sell, dividend, fund events)
    TRANSACTION_ADDED = "Transaction added"
    TRANSACTION_UPDATED = "Transaction updated"
    TRANSACTION_DELETED = "Transaction deleted"

    # Symbol messages
    ASSET_ADDED = "Symbol added"
    ASSET_DELETED = "Symbol deleted"

    # Fund messages
    FUND_CREATED = "Fund created"
    FUND_DELETED = "Fund deleted"
    DEPOSIT_COMPLETED = "Deposit completed"
    WITHDRAWAL_COMPLETED = "Withdrawal completed"


class ConfirmMessages:
    """Confirmation messages shown in delete dialogs."""

    DELETE_TRANSACTION = "Delete this transaction?"


class ValidationMessages:
    """Form and input validation error messages."""

    # Generic
    REQUIRED = "Required."
    INVALID_NUMBER = "Invalid number."
    VALUE_POSITIVE = "Value must be greater than 0."
    VALUE_NON_NEGATIVE = "Non-negative number required."

    # Field-specific
    PRICE_POSITIVE = "Price must be greater than 0."
    QUANTITY_POSITIVE = "Quantity must be greater than 0."
    AMOUNT_POSITIVE = "Amount must be greater than 0."

    # Date
    INVALID_DATE_FORMAT = "Invalid date format. Use YYYY-MM-DD."

    # Category / fund
    SELECT_CATEGORY = "Select a category."
    CATEGORY_NOT_FOUND = "Category not found."
    INVALID_CATEGORY = "Invalid category."
    INVALID_FUND_ID = "Invalid fund ID."
    SELECT_TRANSACTION_TYPE = "Select a transaction type."

    # Symbol
    SYMBOL_REQUIRED = "Symbol is required."

    # Username
    USERNAME_REQUIRED = "Username is required."
    USERNAME_TOO_SHORT = "Username must be at least 3 characters."
    USERNAME_TOO_LONG = "Username cannot exceed 80 characters."
    USERNAME_INVALID_CHARS = "Only letters and underscores are allowed."
    USERNAME_TAKEN = "This username is already taken."

    # Email
    EMAIL_REQUIRED = "Email address is required."
    EMAIL_INVALID = "Please enter a valid email address."
    EMAIL_TOO_LONG = "Email address is too long."
    EMAIL_TAKEN = "An account with this email already exists."
    EMAIL_IN_USE = "This email address is already in use."

    # Password
    PASSWORD_REQUIRED = "Password is required."
    PASSWORD_TOO_SHORT = "Password must be at least 8 characters."
    PASSWORD_CONFIRM_REQUIRED = "Please confirm your password."
    PASSWORDS_NO_MATCH = "Passwords do not match."
    CURRENT_PASSWORD_REQUIRED = "Current password is required."
    NEW_PASSWORD_REQUIRED = "New password is required."
    NEW_PASSWORD_TOO_SHORT = "New password must be at least 8 characters."
    NEW_PASSWORD_CONFIRM_REQUIRED = "Please confirm your new password."
    EMAIL_PASSWORD_CONFIRM = "Please enter your current password to confirm."

    # Verification code
    VERIFICATION_CODE_REQUIRED = "Verification code is required."
    VERIFICATION_CODE_INVALID = "Please enter the 6-digit code sent to your email."


class AuthMessages:
    """Authentication and account workflow messages."""

    # Login
    INVALID_CREDENTIALS = "Invalid username or password."
    ACCOUNT_UNVERIFIED = (
        "Your account has not been verified yet. "
        "Please check your email for the verification code."
    )

    # Verification
    VERIFICATION_CODE_SENT = "A new verification code has been sent to your email."
    CODE_SEND_FAILED = "Failed to send the code. Please try again in a moment."
    RESEND_UNAVAILABLE = "Unable to resend code. Your account may already be verified."

    # Password
    PASSWORD_CHANGED = "Password changed successfully."
    PASSWORD_RESET_SUCCESS = "Your password has been reset. You can now log in."
    RESET_LINK_INVALID = "The password reset link is invalid or has expired."
    RESET_ACCOUNT_NOT_FOUND = "No account found for this reset link."

    # General
    REGISTRATION_FAILED = "Registration failed. Please try again."
    ERROR_OCCURRED = "An error occurred. Please try again."


class AdminMessages:
    """Admin panel messages."""

    USER_NOT_FOUND = "User not found."
    NO_EMAIL_ON_FILE = "{username} has no email address on file."
    RESET_EMAIL_SENT = "Password reset email sent to {username} ({email})."
    EMAIL_SEND_FAILED = "Failed to send the email. Please try again."
    OPERATION_FAILED = "Operation failed. Please try again."
    USER_DELETED = "User deleted successfully."
    ACCESS_DENIED = "Access denied. Admins only."
    ADMIN_ACCESS_GRANTED = "Admin access granted for {username}."
    ADMIN_ACCESS_REVOKED = "Admin access revoked for {username}."


def get_error_message(exception):
    """Convert exception to concise user-facing message.

    Args:
        exception: The exception object

    Returns:
        str: Concise error message
    """
    exception_msg = str(exception).lower()

    if 'quantity' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_QUANTITY
    elif 'price' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_PRICE
    elif 'amount' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_AMOUNT
    elif 'date' in exception_msg and 'invalid' in exception_msg:
        return ErrorMessages.INVALID_DATE
    elif 'not found' in exception_msg and 'transaction' in exception_msg:
        return ErrorMessages.TRANSACTION_NOT_FOUND
    elif 'not found' in exception_msg and 'fund' in exception_msg:
        return ErrorMessages.FUND_NOT_FOUND
    elif 'symbol' in exception_msg and 'invalid' in exception_msg:
        return ErrorMessages.INVALID_SYMBOL
    else:
        # Return first line of error message if it's short, otherwise generic
        first_line = str(exception).split('\n')[0].strip()
        if len(first_line) <= 50:
            return first_line
        return ErrorMessages.OPERATION_FAILED


def get_first_form_error(form_errors):
    """Extract first error message from form errors dict.

    Args:
        form_errors: Dictionary of form errors (field: error_message)

    Returns:
        str: First error message, or 'Invalid input' if no errors
    """
    if not form_errors:
        return ErrorMessages.INVALID_INPUT

    # Get first error value
    first_error = next(iter(form_errors.values()))

    # Handle both list and string error formats
    if isinstance(first_error, list):
        return first_error[0] if first_error else ErrorMessages.INVALID_INPUT
    else:
        return str(first_error)
