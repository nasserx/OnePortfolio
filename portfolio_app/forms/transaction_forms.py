"""Forms for transaction-related operations."""

from decimal import Decimal
from typing import List
from portfolio_app.forms.base_form import BaseForm
from portfolio_app.models.fund import Fund
from portfolio_app.utils.messages import ValidationMessages
from config import Config


class TransactionAddForm(BaseForm):
    """Form for adding a new transaction."""

    def __init__(self, data: dict, funds: List[Fund]):
        """Initialize form.

        Args:
            data: Form data
            funds: List of available funds
        """
        super().__init__(data)
        self.funds = funds

    def validate(self) -> bool:
        """Validate transaction add form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate fund_id
        fund_id_str = (self.data.get('fund_id') or '').strip()
        try:
            fund_id = int(fund_id_str) if fund_id_str else 0
            if fund_id <= 0:
                self.errors['fund_id'] = ValidationMessages.SELECT_CATEGORY
            else:
                # Find fund in list
                fund = next((f for f in self.funds if f.id == fund_id), None)
                if not fund:
                    self.errors['fund_id'] = ValidationMessages.CATEGORY_NOT_FOUND
                else:
                    self.cleaned_data['fund_id'] = fund_id
                    self.cleaned_data['fund'] = fund
        except (ValueError, TypeError):
            self.errors['fund_id'] = ValidationMessages.INVALID_CATEGORY

        # Validate transaction_type
        transaction_type = self._validate_choice(
            'transaction_type',
            Config.TRANSACTION_TYPES,
            ValidationMessages.SELECT_TRANSACTION_TYPE,
        )
        if transaction_type:
            self.cleaned_data['transaction_type'] = transaction_type

        # Validate symbol
        symbol = self._validate_required_string('symbol', ValidationMessages.SYMBOL_REQUIRED)
        if symbol:
            self.cleaned_data['symbol'] = symbol.upper()

        # Validate price
        price = self._validate_decimal('price', allow_zero=False)
        if price is not None:
            self.cleaned_data['price'] = price

        # Validate quantity
        quantity = self._validate_decimal('quantity', allow_zero=False)
        if quantity is not None:
            self.cleaned_data['quantity'] = quantity

        # Validate fees (optional, allow zero)
        fees = self._validate_decimal('fees', allow_zero=True, allow_blank=True)
        if fees is not None:
            self.cleaned_data['fees'] = fees
        elif 'fees' not in self.errors:
            self.cleaned_data['fees'] = Decimal('0')

        # Get notes (optional)
        self.cleaned_data['notes'] = self._get_string('notes', default='')

        # Validate date (required)
        date_str = self._get_string('date', default='')
        if not date_str:
            self.errors['date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class TransactionEditForm(BaseForm):
    """Form for editing an existing transaction."""

    def __init__(self, data: dict, transaction_id: int, current_transaction_type: str):
        """Initialize form.

        Args:
            data: Form data
            transaction_id: Transaction ID
            current_transaction_type: Current transaction type
        """
        super().__init__(data)
        self.transaction_id = transaction_id
        self.current_transaction_type = current_transaction_type

    def validate(self) -> bool:
        """Validate transaction edit form.

        Returns:
            True if validation passes, False otherwise
        """
        self.cleaned_data['transaction_id'] = self.transaction_id

        # Validate symbol (if provided)
        symbol = self._get_string('edit_symbol', default='')
        if symbol:
            self.cleaned_data['symbol'] = symbol.upper()

        # Validate price (if provided)
        price_str = self._get_string('edit_price', default='')
        if price_str:
            price = self._validate_decimal('edit_price', allow_zero=False)
            if price is not None:
                self.cleaned_data['price'] = price

        # Validate quantity (if provided)
        quantity_str = self._get_string('edit_quantity', default='')
        if quantity_str:
            quantity = self._validate_decimal('edit_quantity', allow_zero=False)
            if quantity is not None:
                self.cleaned_data['quantity'] = quantity

        # Validate fees (if provided)
        fees_str = self._get_string('edit_fees', default='')
        if fees_str:
            fees = self._validate_decimal('edit_fees', allow_zero=True, allow_blank=False)
            if fees is not None:
                self.cleaned_data['fees'] = fees

        # Get notes (if provided)
        notes = self._get_string('edit_notes', default=None)
        if notes is not None:
            self.cleaned_data['notes'] = notes

        # Validate date (if provided)
        date_str = self._get_string('edit_date', default='')
        if date_str:
            from datetime import datetime
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                self.cleaned_data['date'] = date_obj
            except ValueError:
                self.errors['edit_date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class DividendAddForm(BaseForm):
    """Form for adding a new dividend income record."""

    def __init__(self, data: dict, funds: List[Fund]):
        super().__init__(data)
        self.funds = funds

    def validate(self) -> bool:
        # Validate fund_id
        fund_id_str = (self.data.get('fund_id') or '').strip()
        try:
            fund_id = int(fund_id_str) if fund_id_str else 0
            if fund_id <= 0:
                self.errors['fund_id'] = ValidationMessages.SELECT_CATEGORY
            else:
                fund = next((f for f in self.funds if f.id == fund_id), None)
                if not fund:
                    self.errors['fund_id'] = ValidationMessages.CATEGORY_NOT_FOUND
                else:
                    self.cleaned_data['fund_id'] = fund_id
        except (ValueError, TypeError):
            self.errors['fund_id'] = ValidationMessages.INVALID_CATEGORY

        # Validate symbol (required — submitted as div_symbol from the form)
        symbol = (self.data.get('div_symbol') or '').strip().upper()
        if not symbol:
            self.errors['div_symbol'] = ValidationMessages.SYMBOL_REQUIRED
        else:
            self.cleaned_data['symbol'] = symbol

        # Validate amount (must be > 0)
        amount_str = (self.data.get('amount') or '').strip()
        if not amount_str:
            self.errors['amount'] = ValidationMessages.AMOUNT_POSITIVE
        else:
            try:
                amount = Decimal(amount_str.replace(',', '.'))
                if amount <= 0:
                    self.errors['amount'] = ValidationMessages.AMOUNT_POSITIVE
                else:
                    self.cleaned_data['amount'] = amount
            except Exception:
                self.errors['amount'] = ValidationMessages.AMOUNT_POSITIVE

        # Get notes (optional)
        self.cleaned_data['notes'] = self._get_string('notes', default='')

        # Validate date (required)
        date_str = self._get_string('date', default='')
        if not date_str:
            self.errors['date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class DividendEditForm(BaseForm):
    """Form for editing an existing dividend income record."""

    def __init__(self, data: dict, dividend_id: int):
        super().__init__(data)
        self.dividend_id = dividend_id

    def validate(self) -> bool:
        self.cleaned_data['dividend_id'] = self.dividend_id

        # Validate amount (must be > 0)
        amount_str = (self.data.get('edit_amount') or '').strip()
        if not amount_str:
            self.errors['edit_amount'] = ValidationMessages.AMOUNT_POSITIVE
        else:
            try:
                amount = Decimal(amount_str.replace(',', '.'))
                if amount <= 0:
                    self.errors['edit_amount'] = ValidationMessages.AMOUNT_POSITIVE
                else:
                    self.cleaned_data['amount'] = amount
            except Exception:
                self.errors['edit_amount'] = ValidationMessages.AMOUNT_POSITIVE

        # Get notes (optional)
        notes = self._get_string('edit_notes', default=None)
        if notes is not None:
            self.cleaned_data['notes'] = notes

        # Validate date (required)
        date_str = self._get_string('edit_date', default='')
        if not date_str:
            self.errors['edit_date'] = ValidationMessages.REQUIRED
        else:
            from datetime import datetime
            try:
                self.cleaned_data['date'] = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                self.errors['edit_date'] = ValidationMessages.INVALID_DATE_FORMAT

        return not self.has_errors()


class AssetAddForm(BaseForm):
    """Form for adding a tracked asset."""

    def __init__(self, data: dict, funds: List[Fund]):
        """Initialize form.

        Args:
            data: Form data
            funds: List of available funds
        """
        super().__init__(data)
        self.funds = funds

    def validate(self) -> bool:
        """Validate asset add form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate fund_id
        fund_id_str = (self.data.get('asset_fund_id') or '').strip()
        try:
            fund_id = int(fund_id_str) if fund_id_str else 0
            if fund_id <= 0:
                self.errors['asset_fund_id'] = ValidationMessages.SELECT_CATEGORY
            else:
                fund = next((f for f in self.funds if f.id == fund_id), None)
                if not fund:
                    self.errors['asset_fund_id'] = ValidationMessages.CATEGORY_NOT_FOUND
                else:
                    self.cleaned_data['fund_id'] = fund_id
        except (ValueError, TypeError):
            self.errors['asset_fund_id'] = ValidationMessages.INVALID_CATEGORY

        # Validate symbol
        symbol = self._validate_required_string('asset_symbol', ValidationMessages.SYMBOL_REQUIRED)
        if symbol:
            self.cleaned_data['symbol'] = symbol.upper()

        return not self.has_errors()


class AssetDeleteForm(BaseForm):
    """Form for deleting a tracked asset."""

    def __init__(self, data: dict):
        """Initialize form.

        Args:
            data: Form data
        """
        super().__init__(data)

    def validate(self) -> bool:
        """Validate asset delete form.

        Returns:
            True if validation passes, False otherwise
        """
        # Validate fund_id
        fund_id_str = (self.data.get('delete_asset_fund_id') or '').strip()
        try:
            fund_id = int(fund_id_str) if fund_id_str else 0
            if fund_id <= 0:
                self.errors['delete_asset_fund_id'] = ValidationMessages.INVALID_FUND_ID
            else:
                self.cleaned_data['fund_id'] = fund_id
        except (ValueError, TypeError):
            self.errors['delete_asset_fund_id'] = ValidationMessages.INVALID_FUND_ID

        # Validate symbol
        symbol = self._validate_required_string('delete_asset_symbol', ValidationMessages.SYMBOL_REQUIRED)
        if symbol:
            self.cleaned_data['symbol'] = symbol.upper()

        return not self.has_errors()
