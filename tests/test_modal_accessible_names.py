"""RCR-12: every production modal names itself and its close control.

Bootstrap's ``.btn-close`` renders as an empty button whose glyph is a CSS
background image, so without ``aria-label`` a screen reader announces an
unnamed button. And a ``.modal`` with no ``aria-labelledby`` is announced as a
bare dialog, even though every modal here has a visible ``<h5 class="modal-title">``
sitting right there.

These checks run against *rendered* pages rather than template source, so a
modal that is only assembled at request time still has to satisfy the contract.
"""

from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser

from portfolio_app import db
from portfolio_app.models.user import User
from tests._auth import authenticate_client
from portfolio_app.services.factory import Services


# Elements that never carry an end tag, so they must not move the depth counter.
VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
    'link', 'meta', 'param', 'source', 'track', 'wbr',
}

ASSETS_MODALS = {
    'addSymbolModal', 'addTransactionModal', 'editTransactionModal',
    'deleteTransactionModal', 'deleteSymbolModal', 'addDividendModal',
    'editDividendModal', 'deleteDividendModal',
}
PORTFOLIO_MODALS = {
    'depositFundsModal', 'withdrawFundsModal', 'newPortfolioModal',
    'renamePortfolioModal', 'deletePortfolioModal', 'editPortfolioEventModal',
    'deletePortfolioEventModal',
}


class _Modal:
    def __init__(self, modal_id, labelledby):
        self.id = modal_id
        self.labelledby = labelledby
        self.close_buttons = []      # list of aria-label values (None when absent)
        self.titles = {}             # element id -> visible text
        self.element_ids = []


class _ModalParser(HTMLParser):
    """Collect every ``.modal`` subtree plus document-wide element ids."""

    def __init__(self):
        super().__init__()
        self.modals = []
        self.document_ids = []
        # Every .btn-close on the page, modal or not: (aria-label, dismiss target).
        self.dismiss_controls = []
        self._depth = 0
        self._modal = None
        self._modal_depth = None
        self._title_depth = None
        self._title_id = None
        self._title_text = []

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _classes(attrs):
        return set((attrs.get('class') or '').split())

    def _open(self, tag, attrs):
        attrs = dict(attrs)
        classes = self._classes(attrs)

        if attrs.get('id'):
            self.document_ids.append(attrs['id'])

        if 'btn-close' in classes:
            self.dismiss_controls.append(
                (attrs.get('aria-label'), attrs.get('data-bs-dismiss')))

        if self._modal is None and 'modal' in classes:
            self._modal = _Modal(attrs.get('id'), attrs.get('aria-labelledby'))
            self._modal_depth = self._depth
            self.modals.append(self._modal)

        if self._modal is not None:
            if attrs.get('id'):
                self._modal.element_ids.append(attrs['id'])
            if 'btn-close' in classes:
                self._modal.close_buttons.append(attrs.get('aria-label'))
            if 'modal-title' in classes and self._title_depth is None:
                self._title_depth = self._depth
                self._title_id = attrs.get('id')
                self._title_text = []

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)
        if tag not in VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_data(self, data):
        if self._title_depth is not None and data.strip():
            self._title_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        self._depth -= 1
        if self._title_depth is not None and self._depth == self._title_depth:
            self._modal.titles[self._title_id] = ' '.join(self._title_text)
            self._title_depth = None
        if self._modal is not None and self._depth == self._modal_depth:
            self._modal = None
            self._modal_depth = None


def _seed_user(username='modal_a11y_user'):
    user = User(username=username, email=f'{username}@example.com', is_verified=True)
    user.password_hash = 'legacy-test-hash'
    db.session.add(user)
    db.session.commit()
    return user.id


def _seed_activity(uid):
    """Enough data that every row-level modal is actually rendered."""
    svc = Services(user_id=uid)
    portfolio = svc.portfolio_service.create_portfolio('Growth', user_id=uid)
    svc.portfolio_service.deposit_funds(
        portfolio.id, Decimal('5000'), date=datetime(2024, 1, 1))
    svc.transaction_service.add_transaction(
        portfolio_id=portfolio.id, transaction_type='Buy', symbol='AAPL',
        price=Decimal('100'), quantity=Decimal('10'), fees=Decimal('0'),
        notes='', date=datetime(2024, 1, 2),
    )
    svc.transaction_service.add_dividend(
        portfolio_id=portfolio.id, symbol='AAPL', amount=Decimal('75'),
        date=datetime(2024, 1, 4), notes='',
    )
    return portfolio.id


def _logged_in_client(app):
    """One seeded account with activity, rendered through one session.

    Seeding per page would violate the unique-email constraint, and the
    clean_database fixture resets between tests, not within one.
    """
    with app.app_context():
        uid = _seed_user()
        _seed_activity(uid)

    client = app.test_client()
    authenticate_client(client, uid)
    return client


def _parse(client, path):
    response = client.get(path)
    assert response.status_code == 200, path

    parser = _ModalParser()
    parser.feed(response.get_data(as_text=True))
    return parser


def _pages(app):
    client = _logged_in_client(app)
    return (
        ('/transactions/', ASSETS_MODALS, _parse(client, '/transactions/')),
        ('/portfolios/', PORTFOLIO_MODALS, _parse(client, '/portfolios/')),
    )


def test_every_expected_modal_is_rendered(app):
    for path, expected, parsed in _pages(app):
        rendered = {modal.id for modal in parsed.modals}
        assert expected <= rendered, (
            '{0} is missing modals: {1}'.format(path, sorted(expected - rendered)))


def test_every_modal_close_control_has_an_accessible_name(app):
    unnamed = []
    for path, _expected, parsed in _pages(app):
        for modal in parsed.modals:
            for index, label in enumerate(modal.close_buttons):
                if not (label or '').strip():
                    unnamed.append('{0} {1} close#{2}'.format(path, modal.id, index))

    assert unnamed == [], 'close controls with no accessible name: {0}'.format(unnamed)


def test_every_modal_is_labelled_by_its_visible_title(app):
    problems = []
    for path, _expected, parsed in _pages(app):
        for modal in parsed.modals:
            where = '{0} {1}'.format(path, modal.id)
            if not modal.titles:
                continue  # no visible title: aria-labelledby is not the contract
            if not modal.labelledby:
                problems.append(where + ': no aria-labelledby')
                continue
            if modal.labelledby not in modal.titles:
                problems.append('{0}: aria-labelledby="{1}" is not a modal-title id '
                                'in this modal (have {2})'.format(
                                    where, modal.labelledby, sorted(modal.titles)))
                continue
            if not modal.titles[modal.labelledby].strip():
                problems.append(where + ': referenced title renders empty')

    assert problems == [], 'broken modal labelling: {0}'.format(problems)


def test_modal_title_ids_are_unique_within_the_document(app):
    for path, _expected, parsed in _pages(app):
        duplicates = sorted(
            {name for name in parsed.document_ids
             if parsed.document_ids.count(name) > 1}
        )
        assert duplicates == [], '{0} renders duplicate ids: {1}'.format(path, duplicates)


def test_flash_alert_dismiss_controls_have_an_accessible_name(app):
    """The passwordless entry page gives flashed-alert dismiss controls a name.

    These alerts only exist when a message is flashed, so the regression has to
    plant one; an unflashed page renders no dismiss control at all and would
    pass vacuously.
    """
    unnamed = []
    for path in ('/login',):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_flashes'] = [('error', 'Planted flash for the dismiss control.')]

        response = client.get(path)
        assert response.status_code == 200, path

        parser = _ModalParser()
        parser.feed(response.get_data(as_text=True))

        alerts = [control for control in parser.dismiss_controls
                  if control[1] == 'alert']
        assert alerts, '{0} rendered no alert dismiss control to check'.format(path)

        for index, (label, _target) in enumerate(alerts):
            if not (label or '').strip():
                unnamed.append('{0} alert-close#{1}'.format(path, index))

    assert unnamed == [], 'alert dismiss controls with no accessible name: {0}'.format(unnamed)


def test_the_add_entry_modal_keeps_the_title_id_its_script_reads(app):
    """assets.html wires the Buy/Sell heading through getElementById.

    The labelling contract reuses that id instead of adding a second one, so
    renaming it would break the script as well as the label.
    """
    parsed = _parse(_logged_in_client(app), '/transactions/')
    modal = next(m for m in parsed.modals if m.id == 'addTransactionModal')

    assert modal.labelledby == 'add_tx_modal_title'
    assert modal.titles['add_tx_modal_title'] == 'Add Asset Entry'
