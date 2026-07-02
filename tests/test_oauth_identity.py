"""OAuth identity persistence foundation tests."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from portfolio_app import db
from portfolio_app.models.oauth_identity import OAuthIdentity
from portfolio_app.models.user import User
from portfolio_app.repositories.oauth_identity_repository import OAuthIdentityRepository


def _create_user(username='alice', email='alice@example.com'):
    user = User(username=username, email=email, is_verified=True)
    user.set_password('CorrectHorse9')
    db.session.add(user)
    db.session.commit()
    return user


def _create_identity(user_id, provider='google', provider_subject='GoogleSub-123'):
    identity = OAuthIdentity(
        user_id=user_id,
        provider=provider,
        provider_subject=provider_subject,
    )
    db.session.add(identity)
    db.session.commit()
    return identity


def test_oauth_identity_can_be_created_for_user(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id)

        assert identity.id is not None
        assert identity.user_id == user.id


def test_provider_and_provider_subject_are_stored_correctly(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider='google', provider_subject='OpaqueSub-ABC')

        assert identity.provider == 'google'
        assert identity.provider_subject == 'OpaqueSub-ABC'


def test_provider_subject_remains_opaque_and_unchanged(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider_subject=' Sub-With-UPPER-123 ')

        assert identity.provider_subject == ' Sub-With-UPPER-123 '


def test_direct_model_creation_normalizes_provider_case(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider='Google')

        assert identity.provider == 'google'


def test_direct_model_creation_strips_provider_whitespace(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider='  Google  ')

        assert identity.provider == 'google'


def test_updating_provider_normalizes_value(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider='google')

        identity.provider = '  GITHUB  '
        db.session.commit()

        assert identity.provider == 'github'


@pytest.mark.parametrize('provider', ['', '   '])
def test_empty_or_whitespace_provider_is_rejected(app, provider):
    with app.app_context():
        user = _create_user()

        with pytest.raises(ValueError):
            OAuthIdentity(
                user_id=user.id,
                provider=provider,
                provider_subject='subject',
            )


def test_non_string_provider_is_rejected(app):
    with app.app_context():
        user = _create_user()

        with pytest.raises(ValueError):
            OAuthIdentity(
                user_id=user.id,
                provider=None,
                provider_subject='subject',
            )


def test_duplicate_provider_and_provider_subject_is_rejected(app):
    with app.app_context():
        first = _create_user('alice', 'alice@example.com')
        second = _create_user('bob', 'bob@example.com')
        _create_identity(first.id, provider='google', provider_subject='same-sub')

        db.session.add(OAuthIdentity(
            user_id=second.id,
            provider='google',
            provider_subject='same-sub',
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_provider_case_variants_cannot_bypass_provider_subject_unique_constraint(app):
    with app.app_context():
        first = _create_user('alice', 'alice@example.com')
        second = _create_user('bob', 'bob@example.com')
        _create_identity(first.id, provider='Google', provider_subject='same-sub')

        db.session.add(OAuthIdentity(
            user_id=second.id,
            provider='GOOGLE',
            provider_subject='same-sub',
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_duplicate_user_and_provider_is_rejected(app):
    with app.app_context():
        user = _create_user()
        _create_identity(user.id, provider='google', provider_subject='first-sub')

        db.session.add(OAuthIdentity(
            user_id=user.id,
            provider='google',
            provider_subject='second-sub',
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_provider_case_variants_cannot_bypass_user_provider_unique_constraint(app):
    with app.app_context():
        user = _create_user()
        _create_identity(user.id, provider='Google', provider_subject='first-sub')

        db.session.add(OAuthIdentity(
            user_id=user.id,
            provider='GOOGLE',
            provider_subject='second-sub',
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_same_user_can_have_identities_from_different_providers(app):
    with app.app_context():
        user = _create_user()
        _create_identity(user.id, provider='google', provider_subject='google-sub')
        _create_identity(user.id, provider='github', provider_subject='github-sub')

        assert OAuthIdentity.query.filter_by(user_id=user.id).count() == 2


def test_different_users_can_have_different_subjects_for_same_provider(app):
    with app.app_context():
        first = _create_user('alice', 'alice@example.com')
        second = _create_user('bob', 'bob@example.com')
        _create_identity(first.id, provider='google', provider_subject='alice-sub')
        _create_identity(second.id, provider='google', provider_subject='bob-sub')

        assert OAuthIdentity.query.filter_by(provider='google').count() == 2


def test_deleting_user_removes_linked_oauth_identities(app):
    with app.app_context():
        user = _create_user()
        user_id = user.id
        _create_identity(user.id)

        db.session.delete(user)
        db.session.commit()

        assert OAuthIdentity.query.filter_by(user_id=user_id).count() == 0


@pytest.mark.parametrize('field', ['user_id', 'provider', 'provider_subject'])
def test_required_oauth_identity_fields_cannot_be_null(app, field):
    with app.app_context():
        user = _create_user()
        values = {
            'user_id': user.id,
            'provider': 'google',
            'provider_subject': 'subject',
        }
        values[field] = None
        if field == 'provider':
            with pytest.raises(ValueError):
                OAuthIdentity(**values)
            return

        db.session.add(OAuthIdentity(**values))

        with pytest.raises(IntegrityError):
            db.session.commit()


def test_oauth_identity_has_no_token_or_secret_columns(app):
    with app.app_context():
        columns = {
            row[1]
            for row in db.session.execute(text('PRAGMA table_info(oauth_identity)')).fetchall()
        }

        assert 'access_token' not in columns
        assert 'refresh_token' not in columns
        assert 'id_token' not in columns
        assert 'authorization_code' not in columns
        assert 'client_secret' not in columns
        assert 'token_expires_at' not in columns


def test_oauth_identity_repository_lookups_and_create_normalize_provider(app):
    with app.app_context():
        user = _create_user()
        repo = OAuthIdentityRepository(OAuthIdentity, db)

        identity = repo.create(user.id, 'Google', 'CaseSensitiveSub')
        db.session.commit()

        assert identity.provider == 'google'
        assert identity.provider_subject == 'CaseSensitiveSub'
        assert repo.get_by_provider_subject('GOOGLE', 'CaseSensitiveSub').id == identity.id
        assert repo.get_for_user_and_provider(user.id, 'GOOGLE').id == identity.id


def test_oauth_identity_repr_does_not_include_provider_subject(app):
    with app.app_context():
        user = _create_user()
        identity = _create_identity(user.id, provider_subject='SensitiveOpaqueSub')

        representation = repr(identity)

        assert 'SensitiveOpaqueSub' not in representation
        assert 'provider=google' in representation
        assert f'user_id={user.id}' in representation
