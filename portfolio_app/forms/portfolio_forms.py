"""Forms for portfolio-related operations."""

from typing import List
from portfolio_app.forms.base_form import BaseForm, NOTES_MAX_LENGTH
from portfolio_app.utils.messages import MESSAGES


class PortfolioAddForm(BaseForm):
    """Form for creating a new portfolio."""

    def __init__(self, data: dict, existing_names: List[str]):
        super().__init__(data)
        self._existing_lower = {n.lower() for n in existing_names}

    def validate(self) -> bool:
        name = self._validate_required_string('name', MESSAGES['FIELD_REQUIRED'])
        if name:
            if len(name) > 20:
                self.errors['name'] = MESSAGES['NAME_TOO_LONG']
            elif name.lower() in self._existing_lower:
                self.errors['name'] = MESSAGES['PORTFOLIO_NAME_TAKEN']
            else:
                self.cleaned_data['name'] = name

        return not self.has_errors()


class PortfolioDepositForm(BaseForm):
    """Form for depositing funds into a portfolio."""

    def __init__(self, data: dict, portfolio_id: int):
        super().__init__(data)
        self.portfolio_id = portfolio_id

    def validate(self) -> bool:
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['portfolio_id'] = self.portfolio_id

        notes = self._get_string('notes', default='')
        if self._validate_max_length('notes', notes, NOTES_MAX_LENGTH, MESSAGES['NOTES_TOO_LONG']):
            self.cleaned_data['notes'] = notes

        date_str = self._get_string('deposit_date', default='')
        parsed = self._parse_date_not_future(date_str, 'deposit_date')
        if parsed is not None:
            self.cleaned_data['date'] = parsed

        return not self.has_errors()


class PortfolioWithdrawForm(BaseForm):
    """Form for withdrawing funds from a portfolio."""

    def __init__(self, data: dict, portfolio_id: int):
        super().__init__(data)
        self.portfolio_id = portfolio_id

    def validate(self) -> bool:
        amount_delta = self._validate_decimal('amount_delta', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['portfolio_id'] = self.portfolio_id

        notes = self._get_string('notes', default='')
        if self._validate_max_length('notes', notes, NOTES_MAX_LENGTH, MESSAGES['NOTES_TOO_LONG']):
            self.cleaned_data['notes'] = notes

        date_str = self._get_string('withdraw_date', default='')
        parsed = self._parse_date_not_future(date_str, 'withdraw_date')
        if parsed is not None:
            self.cleaned_data['date'] = parsed

        return not self.has_errors()


class PortfolioEventEditForm(BaseForm):
    """Form for editing a portfolio cash event."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        amount_delta = self._validate_decimal('edit_cash_event_amount', allow_zero=False)
        if amount_delta is not None:
            self.cleaned_data['amount_delta'] = amount_delta
            self.cleaned_data['event_id'] = self.event_id

        notes = self._get_string('edit_cash_event_notes', default='')
        if self._validate_max_length(
            'edit_cash_event_notes', notes, NOTES_MAX_LENGTH, MESSAGES['NOTES_TOO_LONG']
        ):
            self.cleaned_data['notes'] = notes

        # Date is optional on edit; only validate when provided.
        date_str = self._get_string('date', default='')
        if date_str:
            parsed = self._parse_date_not_future(date_str, 'date')
            if parsed is not None:
                self.cleaned_data['date'] = parsed

        return not self.has_errors()


class PortfolioEventDeleteForm(BaseForm):
    """Form for deleting a portfolio cash event."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        self.cleaned_data['event_id'] = self.event_id
        return True
