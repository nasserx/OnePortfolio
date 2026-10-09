"""Transfer form boundaries reuse the exact Decimal and effective-date parsers."""

from portfolio_app.forms.base_form import BaseForm, NOTES_MAX_LENGTH
from portfolio_app.utils.messages import MESSAGES


class TransferForm(BaseForm):
    def __init__(self, data, portfolios):
        super().__init__(data)
        self.portfolio_ids = [str(row.id) for row in portfolios]

    def validate(self):
        for field in ('source_portfolio_id', 'destination_portfolio_id'):
            value = self._validate_choice(field, self.portfolio_ids, MESSAGES['TRANSFER_PORTFOLIO_INVALID'])
            if value is not None:
                self.cleaned_data[field] = int(value)
        amount = self._validate_decimal('amount')
        if amount is not None:
            self.cleaned_data['amount'] = amount
        date = self._parse_date_not_future(self._get_string('date', default=''), 'date')
        if date is not None:
            self.cleaned_data['date'] = date
        notes = self._get_string('notes', default='')
        if self._validate_max_length('notes', notes, NOTES_MAX_LENGTH, MESSAGES['NOTES_TOO_LONG']):
            self.cleaned_data['notes'] = notes
        return not self.has_errors()
