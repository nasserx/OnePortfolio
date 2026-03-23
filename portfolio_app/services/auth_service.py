"""Authentication service for user management."""

import secrets
import string
import logging
from datetime import datetime
from typing import Optional, Tuple

from portfolio_app.models.user import User
from portfolio_app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """Service handling registration, login, and password management."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def register(self, username: str, email: str, password: str) -> Tuple[User, bool]:
        """Register a new unverified user.

        The first user to register is automatically granted admin status.
        The account is inactive (is_verified=False) until the user clicks
        the verification link sent to their email.

        Args:
            username: Desired username
            email: User's email address (stored in lowercase)
            password: Plain-text password (will be hashed)

        Returns:
            Tuple of (created User, is_first_user)

        Raises:
            ValueError: If username or email is already taken
        """
        if self.user_repo.get_by_username(username):
            raise ValueError('This username is already taken.')

        if self.user_repo.get_by_email(email):
            raise ValueError('An account with this email already exists.')

        is_first = self.user_repo.count() == 0
        user = User(
            username=username,
            email=email.lower(),
            is_admin=is_first,
            is_verified=False,
        )
        user.set_password(password)
        self.user_repo.add(user)
        self.user_repo.commit()
        return user, is_first

    def verify_user(self, email: str) -> Optional[User]:
        """Mark a user's email as verified, activating their account.

        Args:
            email: The email address decoded from the verification token.

        Returns:
            The activated User, or None if no matching user was found.
        """
        user = self.user_repo.get_by_email(email)
        if not user:
            return None

        user.is_verified = True
        self.user_repo.commit()
        return user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Verify credentials and update last_login on success.

        Only verified accounts are allowed to log in.

        Args:
            username: Username to authenticate
            password: Plain-text password to verify

        Returns:
            The authenticated User, or None if credentials are invalid
            or the account is not yet verified.
        """
        user = self.user_repo.get_by_username(username)
        if user and user.check_password(password):
            if not user.is_verified:
                # Signal to the route that the account exists but is unverified.
                # Returning a special sentinel avoids leaking "wrong password".
                return 'unverified'
            user.last_login = datetime.utcnow()
            self.user_repo.commit()
            return user
        return None

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change user password after verifying the current one.

        Args:
            user: The user changing their password
            current_password: Must match the stored hash
            new_password: New plain-text password

        Raises:
            ValueError: If current_password is wrong
        """
        if not user.check_password(current_password):
            raise ValueError('Current password is incorrect.')
        user.set_password(new_password)
        self.user_repo.commit()

    def reset_password_with_token(self, email: str, new_password: str) -> Optional[User]:
        """Set a new password for the user identified by their email.

        Called after the reset token has already been validated by the route.

        Args:
            email: The email address decoded from the reset token.
            new_password: New plain-text password to hash and store.

        Returns:
            The updated User, or None if no matching user was found.
        """
        user = self.user_repo.get_by_email(email)
        if not user:
            return None
        user.set_password(new_password)
        self.user_repo.commit()
        return user

    # ------------------------------------------------------------------
    # Admin-only operations (kept for the admin panel)
    # ------------------------------------------------------------------

    def reset_password(self, user_id: int) -> str:
        """Admin action: generate and set a random temporary password.

        Args:
            user_id: ID of the user whose password will be reset

        Returns:
            The generated temporary password (shown once to admin)

        Raises:
            ValueError: If user not found
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError('User not found.')

        alphabet = string.ascii_letters + string.digits
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        user.set_password(temp_password)
        self.user_repo.commit()
        return temp_password

    def toggle_admin(self, user_id: int, current_user: User) -> User:
        """Toggle admin status for a user (admin only).

        Args:
            user_id: Target user ID
            current_user: The admin performing the action

        Raises:
            ValueError: If user not found or trying to change own status
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError('User not found.')
        if user.id == current_user.id:
            raise ValueError('You cannot change your own admin status.')
        user.is_admin = not user.is_admin
        self.user_repo.commit()
        return user

    def delete_user(self, user_id: int, current_user: User) -> None:
        """Delete a user account (admin only).

        Args:
            user_id: Target user ID
            current_user: The admin performing the deletion

        Raises:
            ValueError: If user not found or trying to delete own account
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError('User not found.')
        if user.id == current_user.id:
            raise ValueError('You cannot delete your own account.')
        self.user_repo.delete(user)
        self.user_repo.commit()
