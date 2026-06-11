"""User-facing messages for the application.

All user-facing strings MUST come from ``MESSAGES`` below — no hardcoded
strings elsewhere. Dynamic messages use ``str.format`` placeholders.
"""


MESSAGES = {
    # Generic errors. ``OPERATION_FAILED`` is a last-resort fallback only;
    # every interactive route should use one of the action-specific
    # ``*_FAILED`` keys below so users see what actually went wrong.
    'OPERATION_FAILED':            "Something went wrong. Please try again.",
    'INVALID_INPUT':               "Invalid input.",
    'INVALID_REQUEST':             "Invalid request. Please refresh the page and try again.",
    'SESSION_EXPIRED':             "Your session has expired. Please refresh the page.",
    'CSRF_CHECK_FAILED':           "Security check failed. Please refresh the page and try again.",
    'NOT_FOUND':                   "The requested resource was not found.",
    'INTERNAL_SERVER_ERROR':       "An unexpected error occurred.",

    # Action-specific failure messages — used on the unexpected-exception
    # branch of each CRUD route so the user sees what they were trying to
    # do, not a generic banner.
    'PORTFOLIO_ADD_FAILED':        "We couldn't create the portfolio. Please try again in a moment.",
    'PORTFOLIO_DELETE_FAILED':     "We couldn't remove the portfolio. Please try again in a moment.",
    'DEPOSIT_FAILED':              "We couldn't record your deposit. Please try again in a moment.",
    'WITHDRAWAL_FAILED':           "We couldn't process your withdrawal. Please try again in a moment.",
    'CASH_EVENT_UPDATE_FAILED':    "We couldn't update this transaction. Please try again in a moment.",
    'CASH_EVENT_DELETE_FAILED':    "We couldn't remove this transaction. Please try again in a moment.",
    'TRANSACTION_ADD_FAILED':      "We couldn't add the transaction. Please try again in a moment.",
    'TRANSACTION_UPDATE_FAILED':   "We couldn't update the transaction. Please try again in a moment.",
    'TRANSACTION_DELETE_FAILED':   "We couldn't remove the transaction. Please try again in a moment.",
    'DIVIDEND_ADD_FAILED':         "We couldn't add the dividend. Please try again in a moment.",
    'DIVIDEND_UPDATE_FAILED':      "We couldn't update the dividend. Please try again in a moment.",
    'DIVIDEND_DELETE_FAILED':      "We couldn't remove the dividend. Please try again in a moment.",
    'SYMBOL_ADD_FAILED':           "We couldn't track this symbol. Please try again in a moment.",
    'SYMBOL_DELETE_FAILED':        "We couldn't stop tracking this symbol. Please try again in a moment.",
    'PASSWORD_CHANGE_FAILED':      "We couldn't change your password. Please try again in a moment.",
    'EMAIL_UPDATE_FAILED':         "We couldn't update your email. Please try again in a moment.",
    'ADMIN_TOGGLE_ADMIN_FAILED':   "We couldn't update admin access. Please try again in a moment.",
    'ADMIN_DELETE_USER_FAILED':    "We couldn't remove this user. Please try again in a moment.",
    'ADMIN_RESET_EMAIL_FAILED':    "We couldn't send the reset email. Please try again in a moment.",

    # Not-found errors
    'PORTFOLIO_NOT_FOUND':         "This portfolio no longer exists.",
    'TRANSACTION_NOT_FOUND':       "This transaction no longer exists.",
    'DIVIDEND_NOT_FOUND':          "This dividend transaction no longer exists.",
    'CASH_EVENT_NOT_FOUND':        "This transaction no longer exists.",
    'SYMBOL_NOT_FOUND':            "This tracked symbol no longer exists.",

    # Input validation
    'INVALID_PORTFOLIO_ID':        "Invalid portfolio ID.",
    'INVALID_SYMBOL':              "Please enter a valid symbol (e.g., AAPL, BTC).",
    # Single canonical wording for "value must be > 0", shared by every
    # numeric field (price/quantity/amount/etc.) and matched verbatim by
    # the client-side validator so the server reply doesn't replace the
    # already-shown inline message with a different one.
    'INVALID_QUANTITY':            "Must be more than 0.",
    'INVALID_PRICE':               "Must be more than 0.",
    'INVALID_AMOUNT':              "Must be more than 0.",

    # Business rules
    'INSUFFICIENT_AMOUNT':         "Insufficient amount.",
    'WITHDRAWAL_EXCEEDS_CASH':     "Amount exceeds available cash.",
    'INSUFFICIENT_QUANTITY':       "Insufficient quantity.",
    # Surfaces when a delete/edit/symbol-change would leave a previously
    # covered Sell without enough holdings on its date — distinct from
    # INSUFFICIENT_QUANTITY (which means the proposed Sell itself is too
    # large at its date).
    'LATER_SELL_NEEDS_BUY':        "A later Sell depends on this Buy. Remove that Sell first.",
    # Clawback case — the user is removing or shrinking an *inflow*
    # (a Deposit, a Sell, a Dividend) that's already been spent on a
    # later Buy/Withdrawal. Different from INSUFFICIENT_AMOUNT, which
    # means the user is asking the portfolio to *spend* more than it
    # has (raise a Buy, raise a Withdrawal).
    'CASH_ALREADY_SPENT':          "Cash already spent. Reverse a later transaction first.",
    'FEES_EXCEED_PROCEEDS':        "Fees cannot exceed the sale proceeds.",
    'PORTFOLIO_NAME_TAKEN':        "A portfolio with this name already exists.",
    'SYMBOL_ALREADY_TRACKED':      "'{symbol}' is already being tracked in this portfolio.",

    # Transactions
    'TRANSACTION_ADDED':           "Transaction added.",
    'TRANSACTION_UPDATED':         "Transaction updated.",
    'TRANSACTION_REMOVED':         "Transaction removed.",

    # Tracked symbols
    'SYMBOL_ADDED':                "'{symbol}' added to portfolio.",
    'SYMBOL_REMOVED':              "Symbol removed.",

    # Portfolios and cash events
    # Edits/removals of deposits or withdrawals reuse TRANSACTION_UPDATED / TRANSACTION_REMOVED.
    'PORTFOLIO_CREATED':           "Portfolio created.",
    'PORTFOLIO_REMOVED':           "Portfolio removed.",
    'DEPOSIT_SUCCESSFUL':          "Deposit successful.",
    'WITHDRAWAL_SUCCESSFUL':       "Withdrawal successful.",

    # Dividends
    'DIVIDEND_ADDED':              "Dividend income added.",
    'DIVIDEND_UPDATED':            "Dividend updated.",
    'DIVIDEND_REMOVED':            "Dividend removed.",

    # Remove confirmation prompts
    'CONFIRM_REMOVE_TRANSACTION':  "Remove this transaction?",
    'CONFIRM_REMOVE_DIVIDEND':     "Remove this dividend transaction?",

    # Form validation — generic
    'FIELD_REQUIRED':              "This field is required.",
    'INVALID_NUMBER':              "Please enter a valid number.",
    'VALUE_POSITIVE':              "Must be more than 0.",
    'VALUE_NON_NEGATIVE':          "Please enter zero or a positive number.",
    'INVALID_DATE_FORMAT':         "Invalid date. Please use YYYY-MM-DD format (e.g., 2025-04-18).",
    'DATE_IN_FUTURE':              "Date cannot be in the future.",
    'NAME_TOO_LONG':               "Name must be 20 characters or less.",
    'NOTES_TOO_LONG':              "Notes must be 300 characters or less.",
    'SYMBOL_TOO_LONG':             "Symbol must be 20 characters or less.",

    # Form validation — portfolio / symbol selectors
    'PORTFOLIO_SELECT_REQUIRED':   "Please select a portfolio.",
    'PORTFOLIO_SELECTION_INVALID': "Invalid portfolio selection.",
    'SYMBOL_REQUIRED':             "Please enter a symbol (e.g., AAPL, BTC).",

    # Form validation — username
    'USERNAME_REQUIRED':           "Username is required.",
    'USERNAME_TOO_SHORT':          "Username must be at least 3 characters.",
    'USERNAME_TOO_LONG':           "Username cannot exceed 80 characters.",
    'USERNAME_INVALID_CHARS':      "Username can only contain letters and underscores — no spaces or special characters.",
    'USERNAME_TAKEN':              "This username is already taken.",

    # Form validation — email
    'EMAIL_REQUIRED':              "Email address is required.",
    'EMAIL_INVALID':               "Please enter a valid email address.",
    'EMAIL_TOO_LONG':              "Email address is too long.",
    'EMAIL_TAKEN':                 "This email is already registered. Try signing in instead.",
    'EMAIL_IN_USE':                "This email address is already linked to another account.",
    'EMAIL_ALREADY_EXISTS':        "An account with this email already exists.",

    # Form validation — passwords
    'PASSWORD_REQUIRED':           "Password is required.",
    'PASSWORD_TOO_SHORT':          "Password must be at least 12 characters long.",
    'PASSWORD_CONFIRM_REQUIRED':   "Please confirm your password.",
    'PASSWORDS_NO_MATCH':          "Passwords don't match. Please try again.",
    'CURRENT_PASSWORD_REQUIRED':   "Please enter your current password.",
    'CURRENT_PASSWORD_INCORRECT':  "Current password is incorrect.",
    'NEW_PASSWORD_REQUIRED':       "New password is required.",
    'NEW_PASSWORD_TOO_SHORT':      "New password must be at least 12 characters long.",
    'NEW_PASSWORD_CONFIRM_REQUIRED': "Please confirm your new password.",
    'EMAIL_PASSWORD_CONFIRM_REQUIRED': "Please enter your current password to confirm this change.",

    # Auth — login, registration, verification
    'INVALID_CREDENTIALS':         "Invalid email or password.",
    'ACCOUNT_LOCKED':              "Too many failed sign-in attempts. Please try again in a few minutes.",
    'REGISTRATION_FAILED':         "Registration failed. Please try again.",
    'RATE_LIMIT_SIGNUP':           "Too many sign-up attempts. Please try again later.",
    'RATE_LIMIT_RESEND':           "Too many resend requests. Please try again later.",
    'GOOGLE_SIGNIN_COMING_SOON':   "Google sign-in is coming soon.",
    'GOOGLE_SIGNIN_NOT_CONFIGURED': "Google sign-in is not configured yet.",

    'VERIFICATION_CODE_REQUIRED':  "Verification code is required.",
    'VERIFICATION_CODE_INVALID_FORMAT': "Please enter the 6-digit code sent to your email.",
    # Generic, non-enumerating message for verify-code failures — used by
    # auth_service.verify_user so the response cannot distinguish "email
    # not registered" / "already verified" / "wrong code" / "expired".
    'VERIFICATION_CODE_INVALID_OR_EXPIRED': "Invalid or expired verification code.",
    'VERIFICATION_CODE_SENT':      "A new verification code has been sent to your email.",
    'VERIFICATION_CODE_SEND_FAILED': "Failed to send the code. Please try again in a moment.",
    'VERIFICATION_CODE_RESEND_UNAVAILABLE': "This verification request is no longer active. Please sign in if your account is already verified, or register again to start over.",

    'EMAIL_UPDATED':               "Email address updated successfully.",
    'PASSWORD_CHANGED':            "Password changed successfully.",
    'PASSWORD_RESET_SUCCESS':      "Your password has been reset. You can now sign in.",
    'PASSWORD_RESET_LINK_INVALID': "This password reset link is invalid or has expired.",

    # Account self-service
    'DEMO_ACTION_DISABLED':        "This feature is disabled in demo mode.",
    'DELETION_CODE_SEND_FAILED':   "Failed to send the confirmation code. Please try again.",
    'DELETION_CONFIRMED':          "Your account has been permanently deleted.",
    'DELETION_INVALID_CODE':       "The code is incorrect or has expired. Please request a new one.",
    'DELETION_NO_EMAIL':           "No email address is linked to your account. Please contact an administrator for help.",
    'DELETION_CODE_NOT_VERIFIED':    "Please verify the confirmation code first.",
    'DELETION_CONFIRM_TEXT_REQUIRED': "Type \"delete\" to confirm account deletion.",

    # Admin panel
    'USER_NOT_FOUND':              "User not found.",
    'ADMIN_USER_REMOVED':          "User account removed.",
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


# Field-specific positive-value error lookup
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
