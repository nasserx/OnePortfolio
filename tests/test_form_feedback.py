"""Rendered feedback contracts; server validation remains authoritative."""
from html.parser import HTMLParser

import pytest

from portfolio_app import db
from portfolio_app.models.dividend import Dividend
from portfolio_app.models.portfolio_event import PortfolioEvent
from tests.test_edit_dividend_single_submit import _seed_user, _seed_dividend, _login


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def by_id(self, id):
        return next(attrs for _, attrs in self.nodes if attrs.get('id') == id)


def seeded_client(app):
    with app.app_context():
        uid = _seed_user('form_feedback')
        portfolio_id, dividend_id = _seed_dividend(uid)
    client = app.test_client()
    _login(client, uid)
    return client, portfolio_id, dividend_id


@pytest.mark.parametrize('path,count', [('/transactions/', 8), ('/portfolios/', 9)])
def test_every_financial_dialog_has_one_persistent_general_error(app, path, count):
    client, _, _ = seeded_client(app)
    response = client.get(path)
    assert response.status_code == 200
    markup = Markup(response.get_data(as_text=True))
    summaries = [a for _, a in markup.nodes if 'data-form-error' in a]
    assert len(summaries) == count
    for attrs in summaries:
        assert attrs['role'] == 'alert'
        assert attrs['tabindex'] == '-1'
        assert 'hidden' in attrs
        assert 'd-none' in attrs['class'].split()
    ids = [a['id'] for _, a in markup.nodes if 'id' in a]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('path,count', [('/transactions/', 8), ('/portfolios/', 9)])
def test_financial_dialog_error_placement_and_accessibility_associations(app, path, count):
    """Check all 17 rendered dialogs, including shared portfolio transfers."""
    from tests.test_modal_accessible_names import VOID_TAGS

    class DialogMarkup(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.stack = []
            self.dialogs = {}
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'modal' in attrs.get('class', '').split():
                self.dialogs[attrs['id']] = []
            ancestors = self.stack + [(tag, attrs)]
            dialog = next((a['id'] for _, a in ancestors
                           if 'modal' in a.get('class', '').split()), None)
            if dialog:
                self.dialogs[dialog].append((tag, attrs, list(self.stack)))
            if tag not in VOID_TAGS:
                self.stack.append((tag, attrs))

        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    del self.stack[index:]
                    break

    client, _, _ = seeded_client(app)
    response = client.get(path)
    assert response.status_code == 200
    markup = DialogMarkup(response.get_data(as_text=True))
    assert len(markup.dialogs) == count
    for dialog_id, nodes in markup.dialogs.items():
        summaries = [(index, attrs, parents) for index, (_, attrs, parents) in enumerate(nodes)
                     if 'data-form-error' in attrs]
        assert len(summaries) == 1, dialog_id
        summary_index, _, parents = summaries[0]
        assert any('modal-body' in a.get('class', '').split() for _, a in parents)
        header_index = next(i for i, (_, a, _) in enumerate(nodes)
                            if 'modal-header' in a.get('class', '').split())
        assert header_index < summary_index
        form = next(a for tag, a in parents if tag == 'form')
        assert form['method'].lower() == 'post'
        assert any(a.get('name') == 'csrf_token' for _, a, _ in nodes)
        assert any(a.get('name') == 'mutation_token' for _, a, _ in nodes)
        ids = {a['id'] for _, a, _ in nodes if 'id' in a}
        for index, (tag, attrs, _) in enumerate(nodes):
            for ref in ('aria-describedby', 'aria-labelledby'):
                assert set(attrs.get(ref, '').split()) <= ids, (dialog_id, ref)
            if tag in ('input', 'select', 'textarea') and attrs.get('type') != 'hidden':
                assert summary_index < index, (dialog_id, attrs.get('id'))
                assert 'novalidate' in form
                if 'required' in attrs:
                    assert any(a.get('for') == attrs.get('id') for t, a, _ in nodes if t == 'label')


@pytest.mark.parametrize('editing', [False, True])
def test_dividend_failed_post_retains_values_accessible_errors_and_reopens(app, editing):
    client, portfolio_id, dividend_id = seeded_client(app)
    if editing:
        path = f'/transactions/dividends/edit/{dividend_id}'
        data = {'edit_amount': '-12.3456789', 'edit_date': '2024-01-05', 'edit_notes': 'keep <notes>'}
        amount_id, date_id, notes_id = 'edit_amount', 'edit_dividend_date', 'edit_dividend_notes'
        modal = 'editDividendModal'
    else:
        path = '/transactions/dividends/add'
        data = {'portfolio_id': str(portfolio_id), 'div_symbol': 'AAPL', 'amount': '-12.3456789', 'date': '2024-01-05', 'notes': 'keep <notes>'}
        amount_id, date_id, notes_id = 'add_div_amount', 'add_div_date', 'add_div_notes'
        modal = 'addDividendModal'
    response = client.post(path, data=data)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    markup = Markup(html)
    amount = markup.by_id(amount_id)
    assert amount['value'] == '-12.3456789'
    assert amount['aria-invalid'] == 'true'
    assert amount['aria-describedby'] == f'{amount_id}-error'
    assert 'required' in amount
    error = markup.by_id(f'{amount_id}-error')
    assert error['role'] == 'alert'
    assert 'hidden' not in error
    assert markup.by_id(date_id)['value'] == '2024-01-05'
    assert f'id="{notes_id}"' in html and 'keep &lt;notes&gt;</textarea>' in html
    assert f"if (which === '{modal}'" in html
    # The shared programmatic opener preserves Bootstrap ownership and adds
    # return focus; failed POSTs still reopen the exact populated dialog.
    assert "OnePortfolioDialogs.show(document.getElementById('" + modal + "'))" in html
    with app.app_context():
        assert db.session.get(Dividend, dividend_id).amount == 75
        assert Dividend.query.count() == 1


def test_login_failed_post_has_accessible_feedback_without_removing_required(app):
    response = app.test_client().post('/login', data={'email': 'invalid-email'})
    assert response.status_code == 200
    markup = Markup(response.get_data(as_text=True))
    email = markup.by_id('email')
    assert email['value'] == 'invalid-email'
    assert email['aria-invalid'] == 'true'
    assert email['aria-describedby'] == 'email-error'
    assert 'required' in email
    assert markup.by_id('email-error')['role'] == 'alert'
    assert any('novalidate' in attrs for tag, attrs in markup.nodes if tag == 'form')


def test_summary_keeps_unknown_errors_and_escapes_messages(app):
    with app.app_context():
        macros = app.jinja_env.get_template('macros/forms.html').module
        html = str(macros.form_errors_summary({'__all__': 'General', 'unknown': '<script>bad</script>', 'amount': 'Inline'}, ['amount']))
    assert 'General &lt;script&gt;bad&lt;/script&gt;' in html
    assert 'Inline' not in html
    assert 'hidden' not in Markup(html).nodes[0][1]


def test_cash_event_failed_post_keeps_submitted_values(app):
    client, portfolio_id, _ = seeded_client(app)
    with app.app_context():
        event = PortfolioEvent.query.filter_by(portfolio_id=portfolio_id).first()
        event_id, original_amount = event.id, event.amount_delta
    response = client.post(f'/portfolios/events/edit/{event_id}', data={
        'edit_cash_event_amount': '-7.123456789', 'date': 'bad-date',
        'edit_cash_event_notes': 'retain <notes>',
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    markup = Markup(html)
    assert markup.by_id('edit_cash_event_amount')['value'] == '-7.123456789'
    assert markup.by_id('edit_event_date')['value'] == 'bad-date'
    assert markup.by_id('edit_event_date')['aria-describedby'] == 'edit_event_date-error'
    assert 'retain &lt;notes&gt;</textarea>' in html
    with app.app_context():
        assert db.session.get(PortfolioEvent, event_id).amount_delta == original_amount
