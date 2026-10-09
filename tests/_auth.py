"""Shared signed-session setup for authenticated non-auth behavior tests."""

from portfolio_app.utils.auth_session import establish_auth_session
from portfolio_app import db
from portfolio_app.models import User


def authenticate_client(client, user_id: int, auth_generation: int = 0) -> None:
    with client.application.app_context():
        user = db.session.get(User, user_id)
        identity = f'v2:{user.session_identity}:{auth_generation}'
    with client.session_transaction() as state:
        state['_user_id'] = identity
        state['_fresh'] = True
        establish_auth_session(state)
