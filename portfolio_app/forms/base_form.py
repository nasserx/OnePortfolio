"""Base form class for common validation functionality."""

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from portfolio_app.forms.validators import validate_positive_decimal
from portfolio_app.utils.messages import MESSAGES, get_field_positive_message


# Hard caps applied at the form layer. The DB columns and HTML maxlength
# attributes back these up, but the only authoritative check is here.
NOTES_MAX_LENGTH  = 300
SYMBOL_MAX_LENGTH = 20


def _truncate_to_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _get_user_zone(user_timezone: Optional[str]):
    if not user_timezone:
        return timezone.utc
    try:
        return ZoneInfo(user_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def parse_user_timestamp_for_future_check(
    value: str,
    *,
    user_timezone: Optional[str] = None,
) -> tuple[datetime, datetime]:
    """Parse a user timestamp and return ``(stored_datetime, utc_datetime)``.

    Full ISO-8601 values with offsets are normalized directly. Date-only
    values are interpreted as midnight in the user's IANA timezone so a user
    at UTC+3 entering today's date at local midnight is not rejected by a UTC
    host whose calendar date is still yesterday.
    """
    raw_value = (value or '').strip()
    if not raw_value:
        raise ValueError('blank timestamp')

    user_zone = _get_user_zone(user_timezone)

    try:
        parsed_date = datetime.strptime(raw_value, '%Y-%m-%d').date()
    except ValueError:
        parsed_date = None

    if parsed_date is not None:
        local_dt = datetime.combine(parsed_date, time.min, tzinfo=user_zone)
        return datetime.combine(parsed_date, time.min), local_dt.astimezone(timezone.utc)

    normalized = raw_value[:-1] + '+00:00' if raw_value.endswith('Z') else raw_value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=user_zone)

    utc_dt = parsed.astimezone(timezone.utc)
    # Store the user's selected wall-clock value without tzinfo to match the
    # existing SQLAlchemy DateTime columns and display helpers.
    stored_dt = parsed.astimezone(user_zone).replace(tzinfo=None)
    return stored_dt, utc_dt


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
        """Parse a user date/timestamp and reject blanks, bad format, or future dates.

        On failure adds the appropriate message to ``self.errors`` keyed by
        ``error_field_name`` and returns None. On success returns the parsed
        :class:`datetime` for storage so callers don't need to repeat the
        parse-and-validate dance.
        """
        if not date_str:
            self.errors[error_field_name] = MESSAGES['FIELD_REQUIRED']
            return None
        try:
            parsed, parsed_utc = parse_user_timestamp_for_future_check(
                date_str,
                user_timezone=self._get_string('user_timezone', default=''),
            )
        except ValueError:
            self.errors[error_field_name] = MESSAGES['INVALID_DATE_FORMAT']
            return None
        now_utc = datetime.now(timezone.utc)
        if _truncate_to_minute(parsed_utc) > _truncate_to_minute(now_utc):
            self.errors[error_field_name] = MESSAGES['DATE_IN_FUTURE']
            return None
        return parsed
