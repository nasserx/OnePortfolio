"""Authentication service for user management."""

import secrets
import string
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from portfolio_app.models.user import User
from portfolio_app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Verification code expiry in minutes
VERIFICATION_CODE_EXPIRY_MINUTES = 10


class AuthService:
    """Service handling registration, login, and password management."""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, username: str, email: str, password: str) -> Tuple[User, str]:
        """Register a new unverified user and generate a 6-digit verification code.

        The first user to register is automatically granted admin status.
        The account is inactive (is_verified=False) until the user enters
        the verification code sent to their email.

        Args:
            username: Desired username.
            email: User's email address (stored in lowercase).
            password: Plain-text password (will be hashed).

        Returns:
            Tuple of (created User, 6-digit verification code).

        Raises:
            ValueError: If username or email is already taken.
        """
        # Remove stale unverified accounts before checking availability.
        # This lets users re-register freely if their previous attempt expired.
        self._purge_expired_unverified()

        if self.user_repo.get_by_username(username):
            raise ValueError('This username is already taken.')

        if self.user_repo.get_by_email(email):
            raise ValueError('An account with this email already exists.')

        is_first = self.user_repo.count() == 0
        code = self._make_verification_code()

        user = User(
            username=username,
            email=email.lower(),
            is_admin=is_first,
            is_verified=False,
            verification_code=code,
            verification_code_expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES),
        )
        user.set_password(password)
        self.user_repo.add(user)
        self.user_repo.commit()
        return user, code

    # ------------------------------------------------------------------
    # Email verification (6-digit OTP)
    # ------------------------------------------------------------------

    def verify_user(self, email: str, code: str) -> Tuple[bool, str]:
        """Verify a user's email using their 6-digit OTP code.

        Args:
            email: The user's email address.
            code: The 6-digit code entered by the user.

        Returns:
            Tuple of (success: bool, error_message: str).
            On success, error_message is an empty string.
        """
        user = self.user_repo.get_by_email(email)
        if not user:
            return False, 'No account found for this email.'

        if user.is_verified:
            return True, ''

        if not user.verification_code or not user.verification_code_expires_at:
            return False, 'No verification code found. Please request a new one.'

        if datetime.utcnow() > user.verification_code_expires_at:
            return False, 'This code has expired. Please request a new one.'

        if user.verification_code != code.strip():
            return False, 'Invalid verification code.'

        # Code is correct — activate the account and clear the OTP
        user.is_verified = True
        user.verification_code = None
        user.verification_code_expires_at = None
        self.user_repo.commit()
        return True, ''

    def resend_verification_code(self, email: str) -> Optional[str]:
        """Generate and store a fresh 6-digit code for an unverified user.

        Args:
            email: The user's email address.

        Returns:
            The new code, or None if the user is not found or already verified.
        """
        user = self.user_repo.get_by_email(email)
        if not user or user.is_verified:
            return None

        code = self._make_verification_code()
        user.verification_code = code
        user.verification_code_expires_at = datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        self.user_repo.commit()
        return code

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def authenticate(self, identifier: str, password: str) -> Optional[User]:
        """Verify credentials and update last_login on success.

        Accepts either a username or an email address as the identifier.
        Only verified accounts are allowed to log in.

        Args:
            identifier: Username or email address.
            password: Plain-text password to verify.

        Returns:
            The authenticated User on success,
            the string 'unverified' if credentials are correct but account is not verified,
            or None if credentials are invalid.
        """
        user = self.user_repo.get_by_username_or_email(identifier)
        if user and user.check_password(password):
            if not user.is_verified:
                # Signal to the route that the account exists but is unverified.
                # Returning a sentinel string avoids leaking "wrong password".
                return 'unverified'
            user.last_login = datetime.utcnow()
            self.user_repo.commit()
            return user
        return None

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change user password after verifying the current one.

        Args:
            user: The user changing their password.
            current_password: Must match the stored hash.
            new_password: New plain-text password.

        Raises:
            ValueError: If current_password is wrong.
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
    # Admin-only operations
    # ------------------------------------------------------------------

    def reset_password(self, user_id: int) -> str:
        """Admin action: generate and set a random temporary password.

        Args:
            user_id: ID of the user whose password will be reset.

        Returns:
            The generated temporary password (shown once to admin).

        Raises:
            ValueError: If user not found.
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
            user_id: Target user ID.
            current_user: The admin performing the action.

        Raises:
            ValueError: If user not found or trying to change own status.
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
            user_id: Target user ID.
            current_user: The admin performing the deletion.

        Raises:
            ValueError: If user not found or trying to delete own account.
        """
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError('User not found.')
        if user.id == current_user.id:
            raise ValueError('You cannot delete your own account.')
        self.user_repo.delete(user)
        self.user_repo.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _purge_expired_unverified(self) -> None:
        """Delete unverified accounts whose verification code has expired.

        Called at the start of every registration to keep the database clean
        and allow users to re-register freely after an expired attempt.
        """
        expired = self.user_repo.get_expired_unverified(datetime.utcnow())
        for user in expired:
            logger.info("Purging expired unverified account: %s", user.email)
            self.user_repo.delete(user)
        if expired:
            self.user_repo.commit()

    @staticmethod
    def _make_verification_code() -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return str(secrets.randbelow(900000) + 100000)
