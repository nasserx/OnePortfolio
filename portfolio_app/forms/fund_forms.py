"""Forms for fund-related operations."""

from typing import List
from portfolio_app.forms.base_form import BaseForm
from portfolio_app.utils.messages import ValidationMessages


class FundAddForm(BaseForm):
    """Form for adding a new fund."""

    def __init__(self, data: dict, available_categories: List[str]):
        """Initialize form.

        Args:
            data: Form data
            available_categories: List of available category names
        """
        super().__init__(data)
        self.available_categories = available_categories

    def validate(self) -> bool:
        """Validate fund add form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate category
        category = self._validate_required_string('category', ValidationMessages.SELECT_CATEGORY)
        if category and category not in self.available_categories:
            self.errors['category'] = f'{category} already exists.'
        elif category:
            self.cleaned_data['category'] = category

        # Validate amount
        amount = self._validate_decimal('amount', allow_zero=False)
        if amount is not None:
            self.cleaned_data['amount'] = amount

        # Validate date (required)
        date_str = self._get_string('add_fund_date', default='')
        if not date_str:
            self.errors['add_fund_date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['add_fund_date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class FundDepositForm(BaseForm):
    """Form for depositing funds."""

    def __init__(self, data: dict, fund_id: int):
        """Initialize form.

        Args:
            data: Form data
            fund_id: Fund ID
        """
        super().__init__(data)
        self.fund_id = fund_id

    def validate(self) -> bool:
        """Validate deposit form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate amount_delta
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['fund_id'] = self.fund_id

        # Get notes (optional)
        self.cleaned_data['notes'] = self._get_string('notes', default='')

        # Validate date (required)
        date_str = self._get_string('deposit_date', default='')
        if not date_str:
            self.errors['deposit_date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['deposit_date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class FundWithdrawForm(BaseForm):
    """Form for withdrawing funds."""

    def __init__(self, data: dict, fund_id: int):
        """Initialize form.

        Args:
            data: Form data
            fund_id: Fund ID
        """
        super().__init__(data)
        self.fund_id = fund_id

    def validate(self) -> bool:
        """Validate withdrawal form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate amount_delta
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['fund_id'] = self.fund_id

        # Get notes (optional)
        self.cleaned_data['notes'] = self._get_string('notes', default='')

        # Validate date (required)
        date_str = self._get_string('withdraw_date', default='')
        if not date_str:
            self.errors['withdraw_date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['withdraw_date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class FundEventEditForm(BaseForm):
    """Form for editing a fund event."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        """Validate event edit form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate amount_delta
        amount_delta = self._validate_decimal('edit_event_amount', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['event_id'] = self.event_id

        # Get notes (optional)
        self.cleaned_data['notes'] = self._get_string('edit_event_notes', default='')

        # Validate date (if provided)
        date_str = self._get_string('date', default='')
        if date_str:
            from datetime import datetime
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                self.cleaned_data['date'] = date_obj
            except ValueError:
                self.errors['date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class FundEventDeleteForm(BaseForm):
    """Form for deleting a fund event (any type, including Initial)."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        self.cleaned_data['event_id'] = self.event_id
        return True
