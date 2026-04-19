"""Forms for fund-related operations."""

from typing import List
from portfolio_app.forms.base_form import BaseForm
from portfolio_app.utils.messages import ValidationMessages


class FundAddForm(BaseForm):
    """Form for creating a new portfolio (name only, no initial deposit)."""

    def __init__(self, data: dict, existing_names: List[str]):
        """Initialize form.

        Args:
            data: Form data
            existing_names: Portfolio names already used by this user
        """
        super().__init__(data)
        self._existing_lower = {n.lower() for n in existing_names}

    def validate(self) -> bool:
        name = self._validate_required_string('name', ValidationMessages.REQUIRED)
        if name:
            if len(name) > 50:
                self.errors['name'] = 'Name must be 50 characters or less.'
            elif name.lower() in self._existing_lower:
                self.errors['name'] = f'A portfolio named "{name}" already exists.'
            else:
                self.cleaned_data['name'] = name

        return not self.has_errors()


class FundDepositForm(BaseForm):
    """Form for depositing funds."""

    def __init__(self, data: dict, fund_id: int):
        super().__init__(data)
        self.fund_id = fund_id

    def validate(self) -> bool:
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['fund_id'] = self.fund_id

        self.cleaned_data['notes'] = self._get_string('notes', default='')

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
        super().__init__(data)
        self.fund_id = fund_id

    def validate(self) -> bool:
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['fund_id'] = self.fund_id

        self.cleaned_data['notes'] = self._get_string('notes', default='')

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
        amount_delta = self._validate_decimal('edit_event_amount', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['event_id'] = self.event_id

        self.cleaned_data['notes'] = self._get_string('edit_event_notes', default='')

        date_str = self._get_string('date', default='')
        if date_str:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class FundEventDeleteForm(BaseForm):
    """Form for deleting a fund event."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        self.cleaned_data['event_id'] = self.event_id
        return True
