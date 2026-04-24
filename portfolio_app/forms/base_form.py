"""Base form class for common validation functionality."""

from decimal import Decimal
from typing import Dict, Any, Optional
from portfolio_app.forms.validators import validate_positive_decimal
from portfolio_app.utils.messages import MESSAGES, get_field_positive_message


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
        value = self.data.get(field_name) or default
        if value is None:
            return None
        return value.strip()
