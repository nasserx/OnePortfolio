"""Shared signed-session setup for authenticated non-auth behavior tests."""

from portfolio_app.utils.auth_session import establish_auth_session


def authenticate_client(client, user_id: int, auth_generation: int = 0) -> None:
    with client.session_transaction() as state:
        state['_user_id'] = f'v1:{user_id}:{auth_generation}'
        state['_fresh'] = True
        establish_auth_session(state)
