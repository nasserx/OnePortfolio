"""Base form class for common validation functionality."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from portfolio_app.forms.validators import validate_positive_decimal
from portfolio_app.utils.messages import MESSAGES, get_field_positive_message


# Hard caps applied at the form layer. The DB columns and HTML maxlength
# attributes back these up, but the only authoritative check is here.
NOTES_MAX_LENGTH  = 300
SYMBOL_MAX_LENGTH = 20


class BaseForm:
    """Base form class with common validation methods."""

    def __init__(self, data: Dict[str, Any]):
        """Initialize form with request data.

        Args:
            data: Form data from request.form
        """
        self.data = data
        self.errors: Dict[str, str] = {}
        self.cleaned_data: Dict[str, Any] = {}

    def validate(self) -> bool:
        """Validate the form.

        Returns:
            True if validation passes, False otherwise
        """
        raise NotImplementedError("Subclasses must implement validate()")

    def get_cleaned_data(self) -> Dict[str, Any]:
        """Get cleaned and validated data.

        Returns:
            Dictionary of cleaned data
        """
        return self.cleaned_data

    def has_errors(self) -> bool:
        """Check if form has validation errors.

        Returns:
            True if there are errors, False otherwise
        """
        return len(self.errors) > 0

    def _validate_decimal(
        self,
        field_name: str,
        *,
        allow_zero: bool = False,
        allow_blank: bool = False,
    ) -> Optional[Decimal]:
        """Validate a decimal field.

        Args:
            field_name: Name of the field in form data
            allow_zero: Whether to allow zero values
            allow_blank: Whether to allow blank values

        Returns:
            Decimal value if valid, None otherwise (error added to self.errors)
        """
        value_str = (self.data.get(field_name) or '').strip()
        dec, err = validate_positive_decimal(value_str, allow_zero=allow_zero, allow_blank=allow_blank)

        if err:
            if err == MESSAGES['VALUE_POSITIVE']:
                self.errors[field_name] = get_field_positive_message(field_name)
            else:
                self.errors[field_name] = err
            return None

        return dec

    def _validate_required_string(
        self,
        field_name: str,
        error_msg: Optional[str] = None,
    ) -> Optional[str]:
        """Validate a required string field.

        Args:
            field_name: Name of the field in form data
            error_msg: Error message if validation fails

        Returns:
            String value if valid, None otherwise (error added to self.errors)
        """
        value = (self.data.get(field_name) or '').strip()
        if not value:
            self.errors[field_name] = error_msg or MESSAGES['FIELD_REQUIRED']
            return None
        return value

    def _validate_choice(
        self,
        field_name: str,
        choices: list,
        error_msg: Optional[str] = None,
    ) -> Optional[str]:
        """Validate a choice field.

        Args:
            field_name: Name of the field in form data
            choices: List of valid choices
            error_msg: Error message if validation fails

        Returns:
            Choice value if valid, None otherwise (error added to self.errors)
        """
        value = (self.data.get(field_name) or '').strip()
        if value not in choices:
            self.errors[field_name] = error_msg or MESSAGES['INVALID_INPUT']
            return None
        return value

    def _get_string(self, field_name: str, default: Optional[str] = '') -> Optional[str]:
        """Get string value from form data.

        Args:
            field_name: Name of the field
            default: Default value if field not present

        Returns:
            String value or None
        """
        value = self.data.get(field_name, default)
        if value is None:
            return None
        return value.strip()

    def _validate_max_length(
        self,
        field_name: str,
        value: Optional[str],
        max_len: int,
        error_msg: str,
    ) -> bool:
        """Reject if ``value`` exceeds ``max_len`` characters.

        Returns True when the value is within bounds (including None/empty);
        adds an entry to ``self.errors`` and returns False otherwise.
        """
        if value is not None and len(value) > max_len:
            self.errors[field_name] = error_msg
            return False
        return True

    def _parse_date_not_future(
        self,
        date_str: str,
        error_field_name: str,
    ) -> Optional[datetime]:
        """Parse ``YYYY-MM-DD`` and reject blanks, bad format, or future dates.

        On failure adds the appropriate message to ``self.errors`` keyed by
        ``error_field_name`` and returns None. On success returns the parsed
        :class:`datetime` (naive, midnight) so callers don't need to repeat
        the parse-and-validate dance.
        """
        if not date_str:
            self.errors[error_field_name] = MESSAGES['FIELD_REQUIRED']
            return None
        try:
            parsed = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            self.errors[error_field_name] = MESSAGES['INVALID_DATE_FORMAT']
            return None
        # Compare against UTC + 24h grace. The server clock is UTC but the
        # user is in their local timezone; at e.g. 2 AM in UTC+3 the user
        # legitimately reports "today" as one calendar day ahead of the
        # server's UTC date. A 24h ceiling covers any timezone up to
        # UTC+12 without permitting genuinely future dates (which would
        # corrupt the chronological recompute downstream).
        max_allowed = datetime.now(timezone.utc).date() + timedelta(days=1)
        if parsed.date() > max_allowed:
            self.errors[error_field_name] = MESSAGES['DATE_IN_FUTURE']
            return None
        return parsed
