"""Bounded, read-only transaction presentation; never a mutation workflow.

These are preview resource budgets, not financial input/storage restrictions.
The final transaction forms, services and arithmetic retain their own contracts.
"""
from decimal import Decimal, localcontext
from types import SimpleNamespace

from portfolio_app.calculators.financial_math import transaction_cash_effect
from portfolio_app.forms.validators import parse_decimal_field
from portfolio_app.utils.decimal_utils import decimal_text
from portfolio_app.utils.formatting import fmt_money


PREVIEW_BODY_BYTES = 16 * 1024
PREVIEW_OPERAND_CHARS = 4096
PREVIEW_DECIMAL_SPAN = 8192


class PreviewUnavailable(ValueError):
    """Invalid, unavailable or resource-limited preview; safe generic response."""


def bounded_preview_value(value):
    """Bound one stored or parsed Decimal before expanding or aligning it."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise PreviewUnavailable()
    exponent = value.as_tuple().exponent
    if (len(value.as_tuple().digits) > PREVIEW_OPERAND_CHARS
            or max(value.adjusted() + 1, 0) - min(exponent, 0) > PREVIEW_DECIMAL_SPAN):
        raise PreviewUnavailable()
    return value


def preview_values(data, transaction=None):
    values = {}
    for name in ('price', 'quantity', 'fees'):
        raw = data.get(name, '')
        if not isinstance(raw, str) or len(raw) > PREVIEW_OPERAND_CHARS:
            raise PreviewUnavailable()
        if not raw.strip() and transaction is not None:
            # Same partial-edit semantics as TransactionEditForm/update_transaction.
            value = getattr(transaction, name)
        elif not raw.strip() and name == 'fees':
            value = Decimal('0')
        else:
            value, error = parse_decimal_field(raw)
            if error:
                raise PreviewUnavailable()
        values[name] = bounded_preview_value(value)

    price, quantity, fees = (values[key] for key in ('price', 'quantity', 'fees'))
    # Bound multiplication and fee alignment before allocating expanded results.
    low = min(price.as_tuple().exponent + quantity.as_tuple().exponent,
              fees.as_tuple().exponent, -2)
    high = max(price.adjusted() + quantity.adjusted() + 2, fees.adjusted() + 1, 0) + 1
    if high - low > PREVIEW_DECIMAL_SPAN:
        raise PreviewUnavailable()
    return values


def render_preview(transaction_type, values):
    # Reuse the authoritative calculator, including exact finite sums/products.
    effect = transaction_cash_effect(SimpleNamespace(transaction_type=transaction_type, **values))
    amount = effect.copy_negate() if transaction_type == 'Buy' else effect
    with localcontext() as context:
        context.prec = PREVIEW_DECIMAL_SPAN + 4
        formatted = fmt_money(amount)
    return {'transaction_type': transaction_type, 'amount': decimal_text(amount),
            'formatted_amount': formatted}
