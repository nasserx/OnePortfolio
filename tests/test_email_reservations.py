"""Email ownership and reservation races use disposable databases and mock mail."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError

from portfolio_app import db
from portfolio_app.models import User, PendingRegistration, AuthChallenge
from portfolio_app.services.auth_service import AUTHENTICATION_PURPOSE
from portfolio_app.services.factory import Services
from portfolio_app.utils.auth_session import RECENT_AUTH_AT_KEY
from portfolio_app.utils.messages import MESSAGES
from tests.test_auth import app, mail_log, _create_user, _begin, _verify


TARGET = 'reserved@example.com'


def _stage(app):
    uid, _, _ = _create_user(app)
    with app.app_context():
        code = Services().auth_service.stage_email_change(db.session.get(User, uid), TARGET)
    return uid, code


def test_registration_cannot_take_live_pending_email_and_owner_can_confirm(app, mail_log):
    uid, code = _stage(app)
    browser = app.test_client()
    response = browser.post('/login', data={'email': TARGET.upper()})
    assert response.status_code == 302
    assert response.location.endswith('/verify-code')
    assert mail_log == []
    with app.app_context():
        assert PendingRegistration.query.count() == 0
        svc = Services().auth_service
        assert svc.verify_email_change(db.session.get(User, uid), code) == (True, '')
        assert User.query.count() == 1
        assert db.session.get(User, uid).email == TARGET
    _verify(browser, _begin(browser, mail_log, TARGET))
    assert browser.get('/settings').status_code == 200


@pytest.mark.parametrize('competitor', ['owner', 'registration'])
def test_confirmation_rechecks_committed_owner_without_partial_change(app, mail_log, competitor):
    uid, code = _stage(app)
    if competitor == 'owner':
        _create_user(app, TARGET, 'winner')  # Competing commit / pre-fix overlap.
    else:
        with app.app_context():
            db.session.add(PendingRegistration(username='winner', email=TARGET,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)))
            db.session.commit()
    browser = app.test_client()
    _verify(browser, _begin(browser, mail_log))
    response = browser.post('/settings/email/verify', data={'code': code})
    assert response.status_code == 200
    assert MESSAGES['EMAIL_IN_USE'] in response.text
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.email == 'alice@example.com'
        assert user.pending_email == TARGET
        assert user.verification_code is not None


def test_confirmation_integrity_error_rolls_back_and_keeps_session_usable(app, monkeypatch):
    uid, code = _stage(app)
    with app.app_context():
        svc = Services().auth_service
        user = db.session.get(User, uid)
        original = (user.email, user.pending_email, user.verification_code, user.verification_code_expires_at)
        commit = svc.user_repo.commit
        def conflict():
            svc.user_repo.flush()  # Prove rollback also undoes already-flushed changes.
            raise IntegrityError('UPDATE user', {}, Exception('UNIQUE constraint failed: user.email'))
        monkeypatch.setattr(svc.user_repo, 'commit', conflict)
        assert svc.verify_email_change(user, code) == (False, MESSAGES['EMAIL_IN_USE'])
        db.session.expire_all()
        assert (user.email, user.pending_email, user.verification_code, user.verification_code_expires_at) == original
        monkeypatch.setattr(svc.user_repo, 'commit', commit)
        assert svc.verify_email_change(user, code) == (True, '')


def test_expired_change_releases_email_and_resend_cannot_reclaim_it(app, mail_log):
    uid, _ = _stage(app)
    with app.app_context():
        db.session.get(User, uid).verification_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
    browser = app.test_client()
    code = _begin(browser, mail_log, TARGET)
    with app.app_context():
        svc = Services().auth_service
        assert svc.resend_email_change(db.session.get(User, uid)) is None
    _verify(browser, code)
    with app.app_context():
        assert User.query.filter_by(email=TARGET).count() == 1
        assert db.session.get(User, uid).email == 'alice@example.com'


def test_registration_confirmation_and_resend_recheck_other_reservations(app, mail_log):
    uid, _, _ = _create_user(app)
    browser = app.test_client()
    code = _begin(browser, mail_log, TARGET)
    with browser.session_transaction() as state:
        token = state['auth_challenge_token']
    with app.app_context():
        # Model an overlap produced by the old application.
        svc = Services().auth_service
        user = db.session.get(User, uid)
        user.pending_email = TARGET
        user.verification_code = svc._email_change_otp_digest('123456', user, TARGET)
        user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.session.commit()
        assert svc.resend_challenge(token, AUTHENTICATION_PURPOSE) is None
        assert svc.verify_challenge(token, code, AUTHENTICATION_PURPOSE) is None
        assert User.query.count() == 1
        assert AuthChallenge.query.filter_by(token=token).one().consumed_at is None


def test_expired_registration_no_longer_blocks_change(app, mail_log):
    uid, _, _ = _create_user(app)
    _begin(app.test_client(), mail_log, TARGET)
    with app.app_context():
        PendingRegistration.query.one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        svc = Services().auth_service
        code = svc.stage_email_change(db.session.get(User, uid), TARGET)
        assert svc.verify_email_change(db.session.get(User, uid), code) == (True, '')


@pytest.mark.parametrize('via_http', [False, True])
def test_cancelling_change_releases_reservation_and_invalidates_code(app, mail_log, via_http):
    uid, code = _stage(app)
    if via_http:
        owner = app.test_client()
        _verify(owner, _begin(owner, mail_log))
        assert owner.post('/settings/email/cancel').status_code == 302
    with app.app_context():
        svc = Services().auth_service
        user = db.session.get(User, uid)
        if not via_http:
            svc.cancel_email_change(user)
        assert not svc.verify_email_change(user, code)[0]
        assert user.email == 'alice@example.com' and user.pending_email is None
    browser = app.test_client()
    _verify(browser, _begin(browser, mail_log, TARGET))
    assert browser.get('/settings').status_code == 200


def test_concurrent_registration_and_email_change_have_one_reservation(app):
    uid, _, _ = _create_user(app)
    barrier = Barrier(2)
    def attempt(change):
        with app.app_context():
            svc = Services().auth_service
            user = db.session.get(User, uid) if change else None
            barrier.wait(timeout=10)
            try:
                result = svc.stage_email_change(user, TARGET) if change else svc.begin_authentication(TARGET)
                return result is not None
            except ValueError as exc:
                assert str(exc) == MESSAGES['EMAIL_IN_USE']
                return False
            finally:
                db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (False, True)))
    assert sum(results) == 1
    with app.app_context():
        assert (PendingRegistration.query.filter_by(email=TARGET).count()
                + User.query.filter_by(pending_email=TARGET).count()) == 1


def test_concurrent_confirmation_has_one_winner_and_no_partial_account(app):
    uid, code = _stage(app)
    other_id, _, _ = _create_user(app, 'other@example.com', 'other')
    barrier = Barrier(2)
    def verify():
        with app.app_context():
            user = db.session.get(User, uid)
            barrier.wait(timeout=10)
            try:
                return Services().auth_service.verify_email_change(user, code)[0]
            finally:
                db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: verify(), range(2)))
    assert sum(results) == 1
    with app.app_context():
        assert db.session.get(User, uid).email == TARGET
        assert db.session.get(User, other_id).email == 'other@example.com'


def test_registration_integrity_failure_rolls_back_claim_and_promotion(app, monkeypatch):
    with app.app_context():
        svc = Services().auth_service
        issue = svc.begin_authentication(TARGET)
        commit = svc.user_repo.commit
        def conflict():
            svc.user_repo.flush()
            raise IntegrityError('INSERT user', {}, Exception('UNIQUE constraint failed: user.email'))
        monkeypatch.setattr(svc.user_repo, 'commit', conflict)
        assert svc.verify_challenge(issue.token, issue.code, AUTHENTICATION_PURPOSE) is None
        assert User.query.count() == 0
        assert PendingRegistration.query.count() == 1
        assert AuthChallenge.query.one().consumed_at is None
        monkeypatch.setattr(svc.user_repo, 'commit', commit)
        assert svc.verify_challenge(issue.token, issue.code, AUTHENTICATION_PURPOSE).email == TARGET


def test_expired_first_claim_does_not_hide_another_users_live_claim(app):
    uid, _ = _stage(app)
    other_id, _, _ = _create_user(app, 'other@example.com', 'other')
    with app.app_context():
        svc = Services().auth_service
        db.session.get(User, uid).verification_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        code = svc.stage_email_change(db.session.get(User, other_id), TARGET)
        assert svc.begin_authentication(TARGET) is None
        assert svc.resend_email_change(db.session.get(User, uid)) is None
        assert svc.verify_email_change(db.session.get(User, other_id), code) == (True, '')
        assert db.session.get(User, uid).email == 'alice@example.com'


def test_expired_change_can_be_renewed_if_address_remains_available(app):
    uid, _ = _stage(app)
    with app.app_context():
        user = db.session.get(User, uid)
        user.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
        svc = Services().auth_service
        code = svc.resend_email_change(user)
        assert code is not None
        assert svc.verify_email_change(user, code) == (True, '')


def test_replacing_pending_change_releases_old_address(app, mail_log, monkeypatch):
    uid, old_code = _stage(app)
    with app.app_context():
        svc = Services().auth_service
        user = db.session.get(User, uid)
        replacement_code = '123456' if old_code != '123456' else '654321'
        monkeypatch.setattr(svc, '_make_verification_code', lambda: replacement_code)
        new_code = svc.stage_email_change(user, 'replacement@example.com')
        assert not svc.verify_email_change(user, old_code)[0]
        assert svc.verify_email_change(user, new_code) == (True, '')
    browser = app.test_client()
    _verify(browser, _begin(browser, mail_log, TARGET))
    assert browser.get('/settings').status_code == 200


def test_concurrent_email_changes_cannot_reserve_same_target(app):
    first, _, _ = _create_user(app)
    second, _, _ = _create_user(app, 'other@example.com', 'other')
    barrier = Barrier(2)
    def stage(uid):
        with app.app_context():
            user = db.session.get(User, uid)
            barrier.wait(timeout=10)
            try:
                Services().auth_service.stage_email_change(user, TARGET)
                return True
            except ValueError as exc:
                assert str(exc) == MESSAGES['EMAIL_IN_USE']
                return False
            finally:
                db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(stage, (first, second))) == 1
    with app.app_context():
        assert User.query.filter_by(pending_email=TARGET).count() == 1
        assert {user.email for user in User.query.all()} == {'alice@example.com', 'other@example.com'}


@pytest.mark.parametrize('barrier', ['anonymous', 'stale_auth', 'csrf', 'other_user'])
def test_cancel_preserves_other_claims_and_requires_authentication(app, mail_log, barrier):
    uid, _ = _stage(app)
    browser = app.test_client()
    if barrier == 'other_user':
        _create_user(app, 'other@example.com', 'other')
        _verify(browser, _begin(browser, mail_log, 'other@example.com'))
    elif barrier != 'anonymous':
        _verify(browser, _begin(browser, mail_log))
    if barrier == 'stale_auth':
        with browser.session_transaction() as state:
            state[RECENT_AUTH_AT_KEY] = (
                datetime.now(timezone.utc) - timedelta(minutes=16)
            ).timestamp()
    if barrier == 'csrf':
        app.config['WTF_CSRF_ENABLED'] = True
    response = browser.post('/settings/email/cancel', data={'user_id': uid})
    assert response.status_code == 302
    if barrier == 'csrf':
        with browser.session_transaction() as state:
            assert ('warning', MESSAGES['CSRF_CHECK_FAILED']) in state['_flashes']
    if barrier == 'stale_auth':
        assert '/reauthenticate' in response.location
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.pending_email == TARGET
        assert user.email == 'alice@example.com'
        assert user.verification_code is not None
