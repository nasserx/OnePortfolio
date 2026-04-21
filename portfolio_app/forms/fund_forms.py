"""Forms for portfolio-related operations."""

from typing import List
from portfolio_app.forms.base_form import BaseForm
from portfolio_app.utils.messages import ValidationMessages


class PortfolioAddForm(BaseForm):
    """Form for creating a new portfolio."""

    def __init__(self, data: dict, existing_names: List[str]):
        super().__init__(data)
        self._existing_lower = {n.lower() for n in existing_names}

    def validate(self) -> bool:
        name = self._validate_required_string('name', ValidationMessages.REQUIRED)
        if name:
            if len(name) > 50:
                self.errors['name'] = ValidationMessages.NAME_TOO_LONG
            elif name.lower() in self._existing_lower:
                self.errors['name'] = ValidationMessages.PORTFOLIO_NAME_TAKEN
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


class PortfolioEventEditForm(BaseForm):
    """Form for editing a portfolio event."""

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


class PortfolioEventDeleteForm(BaseForm):
    """Form for deleting a portfolio event."""

    def __init__(self, data: dict, event_id: int, current_event_type: str = ''):
        super().__init__(data)
        self.event_id = event_id

    def validate(self) -> bool:
        self.cleaned_data['event_id'] = self.event_id
        return True


# Backward-compatible aliases.
FundAddForm = PortfolioAddForm
FundDepositForm = PortfolioDepositForm
FundWithdrawForm = PortfolioWithdrawForm
FundEventEditForm = PortfolioEventEditForm
FundEventDeleteForm = PortfolioEventDeleteForm
