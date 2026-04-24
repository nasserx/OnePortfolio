"""User-facing messages for the application.

All user-facing strings — flash messages, API errors, form validation,
template prompts, and service-layer exceptions — MUST come from the
``MESSAGES`` dictionary below. No hardcoded user-facing strings elsewhere.

Dynamic messages use ``str.format`` placeholders; the key name signals the
placeholder(s) required. For example, ``ADMIN_ACCESS_GRANTED_USERNAME``
expects a ``{username}`` argument::

    MESSAGES['ADMIN_ACCESS_GRANTED_USERNAME'].format(username=user.username)
"""


MESSAGES = {
    # ------------------------------------------------------------------
    # Generic error / failure messages
    # ------------------------------------------------------------------
    'OPERATION_FAILED':            "Something went wrong. Please try again.",
    'INVALID_INPUT':               "Invalid input.",
    'INVALID_REQUEST':             "Invalid request. Please refresh the page and try again.",
    'SESSION_EXPIRED':             "Your session has expired. Please refresh the page.",
    'CSRF_CHECK_FAILED':           "Security check failed. Please refresh the page and try again.",
    'NOT_FOUND':                   "The requested resource was not found.",
    'INTERNAL_SERVER_ERROR':       "An unexpected error occurred.",

    # ------------------------------------------------------------------
    # Domain entity not-found errors
    # ------------------------------------------------------------------
    'PORTFOLIO_NOT_FOUND':         "This portfolio no longer exists.",
    'TRANSACTION_NOT_FOUND':       "This transaction no longer exists.",
    'DIVIDEND_NOT_FOUND':          "This dividend transaction no longer exists.",
    'CASH_EVENT_NOT_FOUND':        "This transaction no longer exists.",
    'SYMBOL_NOT_FOUND':            "This tracked symbol no longer exists.",

    # ------------------------------------------------------------------
    # Domain validation errors (numeric / identifier input)
    # ------------------------------------------------------------------
    'INVALID_PORTFOLIO_ID':        "Invalid portfolio ID.",
    'INVALID_SYMBOL':              "Please enter a valid symbol (e.g., AAPL, BTC).",
    'INVALID_QUANTITY':            "Please enter a valid quantity greater than zero.",
    'INVALID_PRICE':               "Please enter a valid price greater than zero.",
    'INVALID_AMOUNT':              "Please enter a valid amount greater than zero.",
    'INVALID_DATE':                "Please use the date format YYYY-MM-DD.",

    # ------------------------------------------------------------------
    # Business rule violations
    # ------------------------------------------------------------------
    'INSUFFICIENT_FUNDS':          "Insufficient amount. Your available cash balance is too low for this withdrawal.",
    'INSUFFICIENT_QUANTITY':       "Insufficient quantity. You don't hold enough of this symbol to complete the sale.",
    'FEES_EXCEED_PROCEEDS':        "Fees cannot exceed the sale proceeds.",
    'PORTFOLIO_NAME_TAKEN':        "A portfolio with this name already exists.",
    'SYMBOL_ALREADY_TRACKED_SYMBOL': "'{symbol}' is already being tracked in this portfolio.",

    # ------------------------------------------------------------------
    # Success — transactions
    # ------------------------------------------------------------------
    'TRANSACTION_ADDED':           "Transaction added.",
    'TRANSACTION_UPDATED':         "Transaction updated.",
    'TRANSACTION_DELETED':         "Transaction deleted.",

    # ------------------------------------------------------------------
    # Success — tracked symbols
    # ------------------------------------------------------------------
    'SYMBOL_ADDED':                "Symbol is now being tracked.",
    'SYMBOL_DELETED':              "Symbol removed.",

    # ------------------------------------------------------------------
    # # Success messages for portfolios and transaction operations
    # ------------------------------------------------------------------
    'PORTFOLIO_CREATED':           "Portfolio created.",
    'PORTFOLIO_DELETED':           "Portfolio removed.",
    'DEPOSIT_COMPLETED':           "Deposit completed.",
    'DEPOSIT_UPDATED':             "Deposit updated.",
    'DEPOSIT_DELETED':             "Deposit deleted.",
    'WITHDRAWAL_COMPLETED':        "Withdrawal completed.",
    'WITHDRAWAL_UPDATED':          "Withdrawal updated.",
    'WITHDRAWAL_DELETED':          "Withdrawal deleted.",

    # ------------------------------------------------------------------
    # Success — dividends
    # ------------------------------------------------------------------
    'DIVIDEND_ADDED':              "Dividend income added.",
    'DIVIDEND_UPDATED':            "Dividend updated.",
    'DIVIDEND_DELETED':            "Dividend removed.",

    # ------------------------------------------------------------------
    # Confirmation prompts (delete dialogs)
    # ------------------------------------------------------------------
    'CONFIRM_DELETE_TRANSACTION':  "Delete this transaction?",
    'CONFIRM_DELETE_DIVIDEND':     "Delete this dividend transaction?",

    # ------------------------------------------------------------------
    # Form validation — generic
    # ------------------------------------------------------------------
    'FIELD_REQUIRED':              "This field is required.",
    'INVALID_NUMBER':              "Please enter a valid number.",
    'VALUE_POSITIVE':              "Must be greater than zero.",
    'VALUE_NON_NEGATIVE':          "Please enter zero or a positive number.",
    'INVALID_DATE_FORMAT':         "Invalid date. Please use YYYY-MM-DD format (e.g., 2025-04-18).",
    'NAME_TOO_LONG':               "Name must be 50 characters or less.",

    # ------------------------------------------------------------------
    # Form validation — portfolio / symbol selectors
    # ------------------------------------------------------------------
    'PORTFOLIO_SELECT_REQUIRED':   "Please select a portfolio.",
    'PORTFOLIO_SELECTION_INVALID': "Invalid portfolio selection.",
    'SYMBOL_REQUIRED':             "Please enter a symbol (e.g., AAPL, BTC).",

    # ------------------------------------------------------------------
    # Form validation — username
    # ------------------------------------------------------------------
    'USERNAME_REQUIRED':           "Username is required.",
    'USERNAME_TOO_SHORT':          "Username must be at least 3 characters.",
    'USERNAME_TOO_LONG':           "Username cannot exceed 80 characters.",
    'USERNAME_INVALID_CHARS':      "Username can only contain letters and underscores — no spaces or special characters.",
    'USERNAME_TAKEN':              "This username is already taken.",

    # ------------------------------------------------------------------
    # Form validation — email
    # ------------------------------------------------------------------
    'EMAIL_REQUIRED':              "Email address is required.",
    'EMAIL_INVALID':               "Please enter a valid email address.",
    'EMAIL_TOO_LONG':              "Email address is too long.",
    'EMAIL_TAKEN':                 "This email is already registered. Try signing in instead.",
    'EMAIL_IN_USE':                "This email address is already linked to another account.",
    'EMAIL_ALREADY_EXISTS':        "An account with this email already exists.",

    # ------------------------------------------------------------------
    # Form validation — passwords
    # ------------------------------------------------------------------
    'PASSWORD_REQUIRED':           "Password is required.",
    'PASSWORD_TOO_SHORT':          "Password must be at least 8 characters long.",
    'PASSWORD_CONFIRM_REQUIRED':   "Please confirm your password.",
    'PASSWORDS_NO_MATCH':          "Passwords don't match. Please try again.",
    'CURRENT_PASSWORD_REQUIRED':   "Please enter your current password.",
    'CURRENT_PASSWORD_INCORRECT':  "Current password is incorrect.",
    'NEW_PASSWORD_REQUIRED':       "New password is required.",
    'NEW_PASSWORD_TOO_SHORT':      "New password must be at least 8 characters long.",
    'NEW_PASSWORD_CONFIRM_REQUIRED': "Please confirm your new password.",
    'EMAIL_PASSWORD_CONFIRM_REQUIRED': "Please enter your current password to confirm this change.",

    # ------------------------------------------------------------------
    # Authentication — login, registration, verification
    # ------------------------------------------------------------------
    'INVALID_CREDENTIALS':         "Invalid username or password.",
    'ACCOUNT_UNVERIFIED':          "Your account hasn't been verified yet. Please check your email for the verification code.",
    'ACCOUNT_NOT_FOUND':           "No account was found for this email.",
    'ACCOUNT_ALREADY_VERIFIED':    "This account is already verified. Please sign in.",
    'REGISTRATION_FAILED':         "Registration failed. Please try again.",

    'VERIFICATION_CODE_REQUIRED':  "Verification code is required.",
    'VERIFICATION_CODE_INVALID_FORMAT': "Please enter the 6-digit code sent to your email.",
    'VERIFICATION_CODE_MISMATCH':  "Invalid verification code.",
    'VERIFICATION_CODE_EXPIRED':   "This code has expired. Please request a new one.",
    'VERIFICATION_CODE_NOT_FOUND': "No verification code was found. Please request a new one.",
    'VERIFICATION_CODE_SENT':      "A new verification code has been sent to your email.",
    'VERIFICATION_CODE_SEND_FAILED': "Failed to send the code. Please try again in a moment.",
    'VERIFICATION_CODE_RESEND_UNAVAILABLE': "Unable to resend the code. Your account may already be verified.",

    'EMAIL_UPDATED':               "Email address updated successfully.",
    'PASSWORD_CHANGED':            "Password changed successfully.",
    'PASSWORD_RESET_SUCCESS':      "Your password has been reset. You can now sign in.",
    'PASSWORD_RESET_LINK_INVALID': "This password reset link is invalid or has expired.",
    'PASSWORD_RESET_ACCOUNT_NOT_FOUND': "No account was found for this reset link.",

    # ------------------------------------------------------------------
    # Account self-service (settings, deletion, demo restrictions)
    # ------------------------------------------------------------------
    'DEMO_ACTION_DISABLED':        "This feature is disabled in demo mode.",
    'DELETION_CODE_SEND_FAILED':   "Failed to send the confirmation code. Please try again.",
    'DELETION_CONFIRMED':          "Your account has been permanently deleted.",
    'DELETION_INVALID_CODE':       "The code is incorrect or has expired. Please request a new one.",
    'DELETION_NO_EMAIL':           "No email address is linked to your account. Please contact an administrator for help.",

    # ------------------------------------------------------------------
    # Admin panel
    # ------------------------------------------------------------------
    'USER_NOT_FOUND':              "User not found.",
    'ADMIN_USER_DELETED':          "User account removed.",
    'ADMIN_ACCESS_DENIED':         "You don't have permission to access this page.",
    'ADMIN_EMAIL_SEND_FAILED':     "Failed to send the email. Please try again.",
    'ADMIN_CANNOT_CHANGE_OWN_STATUS': "You cannot change your own admin status.",
    'ADMIN_CANNOT_DELETE_SELF':    "You cannot delete your own account.",

    # Admin — dynamic messages
    'ADMIN_NO_EMAIL_ON_FILE_USERNAME':
        "{username} has no email address on file.",
    'ADMIN_RESET_EMAIL_SENT_USERNAME_EMAIL':
        "Password reset email sent to {username} ({email}).",
    'ADMIN_ACCESS_GRANTED_USERNAME':
        "Admin access granted for {username}.",
    'ADMIN_ACCESS_REVOKED_USERNAME':
        "Admin access revoked for {username}.",
}


# ---------------------------------------------------------------------------
# Field-specific positive-value error lookup
# ---------------------------------------------------------------------------

_FIELD_POSITIVE_MESSAGE_KEYS = {
    'price':                  'INVALID_PRICE',
    'edit_price':             'INVALID_PRICE',
    'quantity':               'INVALID_QUANTITY',
    'edit_quantity':          'INVALID_QUANTITY',
    'amount':                 'INVALID_AMOUNT',
    'amount_delta':           'INVALID_AMOUNT',
    'edit_amount':            'INVALID_AMOUNT',
    'edit_cash_event_amount': 'INVALID_AMOUNT',
}


def get_field_positive_message(field_name: str) -> str:
    """Return a field-specific 'must be positive' error message.

    Falls back to the generic VALUE_POSITIVE message for unknown fields.
    """
    key = _FIELD_POSITIVE_MESSAGE_KEYS.get(field_name, 'VALUE_POSITIVE')
    return MESSAGES[key]


# ---------------------------------------------------------------------------
# Exception → user-friendly message mapping
# ---------------------------------------------------------------------------

def get_error_message(exception: Exception) -> str:
    """Convert a service-layer exception to a clear, user-facing message.

    The service layer raises ``ValueError`` / ``ValidationError`` with
    canonical message strings (sourced from ``MESSAGES``). This helper
    keeps any such message as-is for display, falling back to a generic
    message for unexpected text.
    """
    text = str(exception).strip()
    first_line = text.split('\n', 1)[0].strip()

    # Short, already-human-friendly messages pass through unchanged.
    if first_line and len(first_line) <= 120:
        return first_line
    return MESSAGES['OPERATION_FAILED']


def get_first_form_error(form_errors: dict) -> str:
    """Extract the first error message from a form errors dictionary."""
    if not form_errors:
        return MESSAGES['INVALID_INPUT']

    first_error = next(iter(form_errors.values()))
    if isinstance(first_error, list):
        return first_error[0] if first_error else MESSAGES['INVALID_INPUT']
    return str(first_error)
