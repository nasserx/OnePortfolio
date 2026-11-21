"""Bound note previews without shortening stored or editable financial history."""
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re

import pytest

from portfolio_app import db
from portfolio_app.models.user import User
from portfolio_app.services.factory import Services
from tests._auth import authenticate_client
from tests._html import Document


def test_note_preview_bounds_intrinsic_width_without_changing_table_layout():
    css = Path('portfolio_app/static/css/components.css').read_text(encoding='utf-8')
    match = re.search(r'\.records-table \.record-note\s*\{([^}]+)', css)
    assert match, 'Notes need a bounded preview inside the table cell'
    for declaration in (
        'display: block', 'max-width: 20ch', 'overflow: hidden',
        'text-overflow: ellipsis', 'white-space: nowrap', 'text-align: start',
    ):
        assert declaration in match[1]
    assert 'font-size:' not in match[1]
    assert 'table-layout: fixed' not in css


@pytest.mark.parametrize('notes', [
    '',
    'Short note',
    'هذه ملاحظة لغرض اختبار اختصار العرض مع الحفاظ على النص الكامل. ' * 4,
    'X' * 300,
    'First line\nSecond line\nThird line',
    '<script>alert("note")</script> & an apostrophe \'',
], ids=['empty', 'short', 'arabic', 'unbroken', 'multiline', 'escaped'])
def test_all_record_notes_keep_full_text_and_edit_payloads(app, notes):
    with app.app_context():
        user = User(username='note-reader', email='notes@example.test', is_verified=True)
        db.session.add(user)
        db.session.commit()
        uid = user.id
        services = Services(user_id=uid)
        portfolio = services.portfolio_service.create_portfolio('Notes', user_id=uid)
        event = services.portfolio_service.deposit_funds(
            portfolio.id, Decimal('100'), notes=notes, date=datetime(2024, 1, 1),
        ).events.one()
        transaction = services.transaction_service.add_transaction(
            portfolio_id=portfolio.id, transaction_type='Buy', symbol='ABC',
            price=Decimal('1'), quantity=Decimal('1'), fees=Decimal('0'),
            notes=notes, date=datetime(2024, 1, 2),
        )
        dividend = services.transaction_service.add_dividend(
            portfolio.id, 'ABC', Decimal('2'), datetime(2024, 1, 3), notes=notes,
        )
        records = [(type(record), record.id, record.notes)
                   for record in (event, transaction, dividend)]

    client = app.test_client()
    authenticate_client(client, uid)
    for url, payloads in (
        ('/portfolios/', ('data-event',)),
        ('/transactions/', ('data-tx', 'data-div')),
    ):
        response = client.get(url)
        assert response.status_code == 200
        doc = Document(response.get_data(as_text=True)).root
        cells = doc.find(lambda node: node.tag == 'td' and node.by_class('record-note'))
        assert len(cells) == len(payloads)
        for cell in cells:
            preview, = cell.by_class('record-note')
            assert preview.attrs.get('dir') == 'auto'
            assert preview.text == (notes or '—')
            assert all(isinstance(child, str) for child in preview.children)
            assert cell.attrs.get('title') == (notes or None)
        for attribute in payloads:
            button, = doc.find(lambda node: node.tag == 'button' and attribute in node.attrs)
            assert json.loads(button.attrs[attribute])['notes'] == notes

    with app.app_context():
        for model, record_id, stored_notes in records:
            assert db.session.get(model, record_id).notes == stored_notes
