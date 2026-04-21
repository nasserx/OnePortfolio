"""User-facing messages for the application.

All user-facing strings used in routes, forms, and templates must come from
one of the classes below — no hardcoded strings elsewhere.
"""


class ErrorMessages:
    """Error messages shown to the user."""

    INVALID_QUANTITY    = "Please enter a valid quantity greater than zero."
    INVALID_PRICE       = "Please enter a valid price greater than zero."
    INVALID_AMOUNT      = "Please enter a valid amount greater than zero."
    INVALID_DATE        = "Please use the date format YYYY-MM-DD."
    TRANSACTION_NOT_FOUND  = "This transaction no longer exists."
    DIVIDEND_NOT_FOUND     = "This dividend record no longer exists."
    PORTFOLIO_NOT_FOUND    = "This portfolio no longer exists."
    INVALID_INPUT          = "Invalid input."
    INVALID_SYMBOL         = "Please enter a valid symbol (e.g., AAPL, BTC)."
    OPERATION_FAILED       = "Something went wrong. Please try again."
    EVENT_NOT_FOUND        = "This record no longer exists."
    INVALID_REQUEST        = "Invalid request. Please refresh the page and try again."
    INVALID_PORTFOLIO_ID   = "Invalid portfolio ID."
    USER_NOT_FOUND         = "User not found."
    INSUFFICIENT_FUNDS     = "Insufficient funds. Your available cash balance is too low for this withdrawal."
    INSUFFICIENT_QUANTITY  = "Insufficient quantity. You don't hold enough of this asset to complete the sell."

    # Backward-compatible aliases
    FUND_NOT_FOUND  = PORTFOLIO_NOT_FOUND
    INVALID_FUND_ID = INVALID_PORTFOLIO_ID


class SuccessMessages:
    """Success messages shown after completed actions."""

    # Transaction messages
    TRANSACTION_ADDED   = "Transaction recorded."
    TRANSACTION_UPDATED = "Transaction updated."
    TRANSACTION_DELETED = "Transaction deleted."

    # Symbol messages
    ASSET_ADDED         = "Symbol is now being tracked."
    ASSET_DELETED       = "Symbol removed."

    # Portfolio messages
    PORTFOLIO_CREATED   = "Portfolio created."
    PORTFOLIO_DELETED   = "Portfolio removed."
    FUND_CREATED        = PORTFOLIO_CREATED
    FUND_DELETED        = PORTFOLIO_DELETED
    DEPOSIT_COMPLETED   = "Deposit recorded."
    WITHDRAWAL_COMPLETED = "Withdrawal recorded."
    ENTRY_UPDATED       = "Record updated."
    ENTRY_DELETED       = "Record deleted."

    # Dividend messages
    DIVIDEND_ADDED      = "Dividend income recorded."
    DIVIDEND_UPDATED    = "Dividend updated."
    DIVIDEND_DELETED    = "Dividend removed."


class ConfirmMessages:
    """Confirmation prompts shown in delete dialogs."""

    DELETE_TRANSACTION  = "Delete this transaction?"
    DELETE_DIVIDEND     = "Delete this dividend record?"
    DELETE_FUND_ENTRY   = "Delete this record?"


class ValidationMessages:
    """Form and input validation error messages."""

    # Generic
    REQUIRED              = "This field is required."
    INVALID_NUMBER        = "Please enter a valid number."
    VALUE_POSITIVE        = "Must be greater than zero."
    VALUE_NON_NEGATIVE    = "Please enter zero or a positive number."

    # Field-specific
    PRICE_POSITIVE        = "Please enter a valid price greater than zero."
    QUANTITY_POSITIVE     = "Please enter a valid quantity greater than zero."
    AMOUNT_POSITIVE       = "Please enter a valid amount greater than zero."

    # Date
    INVALID_DATE_FORMAT   = "Invalid date. Please use YYYY-MM-DD format (e.g., 2025-04-18)."

    # Portfolio / asset class
    SELECT_CATEGORY         = "Please select a portfolio."
    CATEGORY_NOT_FOUND      = "Portfolio not found."
    INVALID_CATEGORY        = "Invalid portfolio selection."
    INVALID_PORTFOLIO_ID    = "Invalid portfolio ID."
    INVALID_FUND_ID         = INVALID_PORTFOLIO_ID
    SELECT_TRANSACTION_TYPE = "Please select a transaction type."

    # Portfolio name
    NAME_TOO_LONG           = "Name must be 50 characters or less."
    PORTFOLIO_NAME_TAKEN    = 'A portfolio with this name already exists.'

    # Symbol
    SYMBOL_REQUIRED       = "Please enter a symbol (e.g., AAPL, BTC)."

    # Username
    USERNAME_REQUIRED     = "Username is required."
    USERNAME_TOO_SHORT    = "Username must be at least 3 characters."
    USERNAME_TOO_LONG     = "Username cannot exceed 80 characters."
    USERNAME_INVALID_CHARS = "Username can only contain letters and underscores — no spaces or special characters."
    USERNAME_TAKEN        = "This username is already taken."

    # Email
    EMAIL_REQUIRED        = "Email address is required."
    EMAIL_INVALID         = "Please enter a valid email address."
    EMAIL_TOO_LONG        = "Email address is too long."
    EMAIL_TAKEN           = "This email is already registered. Try signing in instead."
    EMAIL_IN_USE          = "This email address is already linked to another account."

    # Password
    PASSWORD_REQUIRED          = "Password is required."
    PASSWORD_TOO_SHORT         = "Password must be at least 8 characters long."
    PASSWORD_CONFIRM_REQUIRED  = "Please confirm your password."
    PASSWORDS_NO_MATCH         = "Passwords don't match. Please try again."
    CURRENT_PASSWORD_REQUIRED  = "Please enter your current password."
    NEW_PASSWORD_REQUIRED      = "New password is required."
    NEW_PASSWORD_TOO_SHORT     = "New password must be at least 8 characters long."
    NEW_PASSWORD_CONFIRM_REQUIRED = "Please confirm your new password."
    EMAIL_PASSWORD_CONFIRM     = "Please enter your current password to confirm this change."

    # Verification code
    VERIFICATION_CODE_REQUIRED = "Verification code is required."
    VERIFICATION_CODE_INVALID  = "Please enter the 6-digit code sent to your email."


class AuthMessages:
    """Authentication and account workflow messages."""

    # Login
    INVALID_CREDENTIALS  = "Invalid username or password."
    ACCOUNT_UNVERIFIED   = (
        "Your account hasn't been verified yet. "
        "Please check your email for the verification code."
    )

    # Verification
    VERIFICATION_CODE_SENT = "A new verification code has been sent to your email."
    CODE_SEND_FAILED       = "Failed to send the code. Please try again in a moment."
    RESEND_UNAVAILABLE     = "Unable to resend code. Your account may already be verified."

    # Email
    EMAIL_UPDATED          = "Email address updated successfully."

    # Password
    PASSWORD_CHANGED       = "Password changed successfully."
    PASSWORD_RESET_SUCCESS = "Your password has been reset. You can now sign in."
    RESET_LINK_INVALID     = "This password reset link is invalid or has expired."
    RESET_ACCOUNT_NOT_FOUND = "No account was found for this reset link."

    # General
    REGISTRATION_FAILED    = "Registration failed. Please try again."
    ERROR_OCCURRED         = "Something went wrong. Please try again."


class AccountMessages:
    """Account self-service messages (settings, deletion)."""

    # Demo account restrictions
    DEMO_ACTION_DISABLED   = "This feature is disabled in demo mode."

    # Deletion flow
    DELETION_CODE_SENT     = "A confirmation code has been sent to your email. Enter it below to permanently delete your account."
    DELETION_CODE_SEND_FAILED = "Failed to send the confirmation code. Please try again."
    DELETION_CONFIRMED     = "Your account has been permanently deleted."
    DELETION_INVALID_CODE  = "The code is incorrect or has expired. Please request a new one."
    DELETION_NO_EMAIL      = "No email address is linked to your account. Please contact an administrator for help."


class AdminMessages:
    """Admin panel messages."""

    USER_NOT_FOUND         = "User not found."
    NO_EMAIL_ON_FILE       = "{username} has no email address on file."
    RESET_EMAIL_SENT       = "Password reset email sent to {username} ({email})."
    EMAIL_SEND_FAILED      = "Failed to send the email. Please try again."
    OPERATION_FAILED       = "Something went wrong. Please try again."
    USER_DELETED           = "User account removed."
    ACCESS_DENIED          = "You don't have permission to access this page."
    ADMIN_ACCESS_GRANTED   = "Admin access granted for {username}."
    ADMIN_ACCESS_REVOKED   = "Admin access revoked for {username}."


def get_error_message(exception):
    """Convert exception to a clear, user-facing message.

    Args:
        exception: The exception object

    Returns:
        str: User-friendly error message
    """
    exception_msg = str(exception).lower()

    if 'quantity' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_QUANTITY
    elif 'insufficient' in exception_msg and 'quantity' in exception_msg:
        return ErrorMessages.INSUFFICIENT_QUANTITY
    elif 'insufficient' in exception_msg:
        return ErrorMessages.INSUFFICIENT_FUNDS
    elif 'price' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_PRICE
    elif 'amount' in exception_msg and ('invalid' in exception_msg or 'must be' in exception_msg):
        return ErrorMessages.INVALID_AMOUNT
    elif 'date' in exception_msg and 'invalid' in exception_msg:
        return ErrorMessages.INVALID_DATE
    elif 'not found' in exception_msg and 'transaction' in exception_msg:
        return ErrorMessages.TRANSACTION_NOT_FOUND
    elif 'not found' in exception_msg and ('portfolio' in exception_msg or 'fund' in exception_msg):
        return ErrorMessages.PORTFOLIO_NOT_FOUND
    elif 'symbol' in exception_msg and 'invalid' in exception_msg:
        return ErrorMessages.INVALID_SYMBOL
    else:
        first_line = str(exception).split('\n')[0].strip()
        if len(first_line) <= 80:
            return first_line
        return ErrorMessages.OPERATION_FAILED


def get_first_form_error(form_errors):
    """Extract the first error message from a form errors dictionary.

    Args:
        form_errors: Dictionary of form errors (field: error_message)

    Returns:
        str: First error message, or fallback if no errors found
    """
    if not form_errors:
        return ErrorMessages.INVALID_INPUT

    first_error = next(iter(form_errors.values()))

    if isinstance(first_error, list):
        return first_error[0] if first_error else ErrorMessages.INVALID_INPUT
    return str(first_error)
