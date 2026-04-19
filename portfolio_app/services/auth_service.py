"""Authentication service for user management."""

import secrets
import logging
from datetime import datetime, timedelta, timezone
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
            verification_code_expires_at=datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES),
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

        Handles two cases:
        - Registration: looks up by email (is_verified=False).
        - Email update: looks up by pending_email (is_verified=True), then
          promotes pending_email → email and clears the pending field.

        Args:
            email: The email address supplied in the verification URL.
            code: The 6-digit code entered by the user.

        Returns:
            Tuple of (success: bool, error_message: str).
            On success, error_message is an empty string.
        """
        # Case 1: pending email update for an already-verified account
        user = self.user_repo.get_by_pending_email(email)
        if user:
            if not user.verification_code or not user.verification_code_expires_at:
                return False, 'No verification code found. Please request a new one.'
            if datetime.now(timezone.utc) > user.verification_code_expires_at:
                return False, 'This code has expired. Please request a new one.'
            if user.verification_code != code.strip():
                return False, 'Invalid verification code.'

            # Apply the pending email change
            user.email = user.pending_email
            user.pending_email = None
            user.verification_code = None
            user.verification_code_expires_at = None
            self.user_repo.commit()
            return True, ''

        # Case 2: new registration verification
        user = self.user_repo.get_by_email(email)
        if not user:
            return False, 'No account found for this email.'

        if user.is_verified:
            return False, 'This account is already verified. Please log in.'

        if not user.verification_code or not user.verification_code_expires_at:
            return False, 'No verification code found. Please request a new one.'

        if datetime.now(timezone.utc) > user.verification_code_expires_at:
            return False, 'This code has expired. Please request a new one.'

        if user.verification_code != code.strip():
            return False, 'Invalid verification code.'

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
        user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
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
            user.last_login = datetime.now(timezone.utc)
            self.user_repo.commit()
            return user
        return None

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def update_email(self, user: User, new_email: str, password: str) -> str:
        """Stage a new email address and generate a verification OTP.

        The current email is NOT changed until the user confirms the OTP.
        The new address is stored in pending_email and only promoted to email
        after successful verification, so a failed or abandoned flow leaves
        the account fully intact.

        Args:
            user: The logged-in user requesting the change.
            new_email: The desired new email address (stored lowercase).
            password: Current password for identity confirmation.

        Returns:
            The 6-digit OTP to be sent to new_email.

        Raises:
            ValueError: If the password is incorrect.
        """
        if not user.check_password(password):
            raise ValueError('Current password is incorrect.')

        code = self._make_verification_code()
        user.pending_email = new_email.lower()
        user.verification_code = code
        user.verification_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        # is_verified and email are intentionally left unchanged until confirmation
        self.user_repo.commit()
        return code

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
    # Account self-deletion (OTP-confirmed)
    # ------------------------------------------------------------------

    def request_account_deletion(self, user: User) -> str:
        """Generate and store a 6-digit OTP for account deletion confirmation.

        Uses the dedicated deletion_code fields to avoid any conflict with
        the verification_code used for registration and email updates.

        Args:
            user: The authenticated user requesting account deletion.

        Returns:
            The 6-digit confirmation code to be emailed to the user.
        """
        code = self._make_verification_code()
        user.deletion_code = code
        user.deletion_code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        self.user_repo.commit()
        return code

    def confirm_account_deletion(self, user: User, code: str) -> Tuple[bool, str]:
        """Verify the deletion OTP and permanently delete the user's account.

        Args:
            user: The authenticated user confirming deletion.
            code: The 6-digit OTP entered by the user.

        Returns:
            Tuple of (success: bool, error_message: str).
        """
        if (
            not user.deletion_code
            or not user.deletion_code_expires_at
            or datetime.now(timezone.utc) > user.deletion_code_expires_at
            or user.deletion_code != code.strip()
        ):
            return False, 'Invalid or expired confirmation code.'

        self.user_repo.delete(user)
        self.user_repo.commit()
        return True, ''

    # ------------------------------------------------------------------
    # Admin-only operations
    # ------------------------------------------------------------------

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
        expired = self.user_repo.get_expired_unverified(datetime.now(timezone.utc))
        for user in expired:
            logger.info("Purging expired unverified account: %s", user.email)
            self.user_repo.delete(user)
        if expired:
            self.user_repo.commit()

    @staticmethod
    def _make_verification_code() -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return str(secrets.randbelow(900000) + 100000)
