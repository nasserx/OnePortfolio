"""Authentication service for user management."""

import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from portfolio_app.models.user import User
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.repositories.pending_registration_repository import (
    PendingRegistrationRepository,
)
from portfolio_app.utils.messages import MESSAGES

logger = logging.getLogger(__name__)

# Verification code expiry in minutes (the 6-digit OTP)
VERIFICATION_CODE_EXPIRY_MINUTES = 10
# Hard TTL on a staged pending_registration row (independent of OTP refreshes)
PENDING_REGISTRATION_TTL_HOURS = 24

# Brute-force protection
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30


class AuthService:
    """Service handling registration, login, and password management.

    Sign-ups are first staged in :class:`PendingRegistration`. The row is
    promoted into :class:`User` only after the user confirms the OTP, so
    the live users table never contains unverified records.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        pending_repo: PendingRegistrationRepository,
    ):
        self.user_repo = user_repo
        self.pending_repo = pending_repo

    # ------------------------------------------------------------------
    # Registration — stages into pending_registration
    # ------------------------------------------------------------------

    def register(self, username: str, email: str, password: str) -> Tuple[PendingRegistration, str]:
        """Stage a new sign-up and generate a 6-digit verification code.

        The account is **not** inserted into the ``user`` table until the
        OTP is confirmed via :meth:`verify_user`. Any prior pending row for
        the same email is deleted so its token/OTP can no longer be used.

        Args:
            username: Desired username.
            email: User's email address (stored lowercase).
            password: Plain-text password (hashed before storing, even in
                the staging table).

        Returns:
            Tuple of (created PendingRegistration, 6-digit verification code).

        Raises:
            ValueError: If username or email is already taken by an existing
                user, or by a different live pending registration.
        """
        # Tidy stale staged rows so old reservations don't block new sign-ups.
        self.pending_repo.purge_expired(datetime.now(timezone.utc))

        email_lc = email.lower()

        # Guard against collisions with verified accounts first.
        if self.user_repo.get_by_username(username):
            raise ValueError(MESSAGES['USERNAME_TAKEN'])
        if self.user_repo.get_by_email(email_lc):
            raise ValueError(MESSAGES['EMAIL_ALREADY_EXISTS'])

        # Same-email sign-up: invalidate any prior staged token for this
        # email by deleting the pending row outright.
        self.pending_repo.delete_by_email(email_lc)
        self.pending_repo.delete_by_username(username)

        # Cross-row username collision (different email) — block it.
        if self.pending_repo.get_by_username(username):
            raise ValueError(MESSAGES['USERNAME_TAKEN'])

        code = self._make_verification_code()
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)

        # Hash with bcrypt even at the staging layer so plaintext passwords
        # never sit in the database, even briefly.
        temp_user = User()
        temp_user.set_password(password)

        pending = PendingRegistration(
            token=token,
            username=username,
            email=email_lc,
            password_hash=temp_user.password_hash,
            verification_code=code,
            verification_code_expires_at=now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES),
            created_at=now,
            expires_at=now + timedelta(hours=PENDING_REGISTRATION_TTL_HOURS),
        )
        self.pending_repo.add(pending)
        self.pending_repo.commit()
        return pending, code

    # ------------------------------------------------------------------
    # Email verification (6-digit OTP)
    # ------------------------------------------------------------------

    def verify_user(self, email: str, code: str) -> Tuple[bool, str]:
        """Verify a 6-digit OTP and finalise the account.

        Three flows funnel into this method:

        - **Sign-up**: a row in ``pending_registration`` matches ``email``.
          On success it is promoted to a ``User`` and the staging row is
          deleted.
        - **Email update** for a logged-in user: the new address sits in
          ``user.pending_email`` until the OTP is confirmed; then it is
          applied as the new ``user.email``.
        - **Idempotency**: returning a friendly error if the email is
          already a verified account or no pending state exists.
        """
        email_lc = email.lower()
        now = datetime.now(timezone.utc)
        code = code.strip()

        # ── Case 1: pending email update for an already-verified account ──
        user_pending_email = self.user_repo.get_by_pending_email(email_lc)
        if user_pending_email:
            if (
                not user_pending_email.verification_code
                or not user_pending_email.verification_code_expires_at
            ):
                return False, MESSAGES['VERIFICATION_CODE_NOT_FOUND']
            expires_at = self._as_utc(user_pending_email.verification_code_expires_at)
            if now > expires_at:
                return False, MESSAGES['VERIFICATION_CODE_EXPIRED']
            if user_pending_email.verification_code != code:
                return False, MESSAGES['VERIFICATION_CODE_MISMATCH']

            user_pending_email.email = user_pending_email.pending_email
            user_pending_email.pending_email = None
            user_pending_email.verification_code = None
            user_pending_email.verification_code_expires_at = None
            self.user_repo.commit()
            return True, ''

        # ── Case 2: new sign-up confirmation ──
        pending = self.pending_repo.get_by_email(email_lc)
        if pending:
            expires_at = self._as_utc(pending.verification_code_expires_at)
            if now > expires_at:
                return False, MESSAGES['VERIFICATION_CODE_EXPIRED']
            if pending.verification_code != code:
                return False, MESSAGES['VERIFICATION_CODE_MISMATCH']

            # Re-check live user table for late collisions before promoting.
            if self.user_repo.get_by_username(pending.username):
                self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return False, MESSAGES['USERNAME_TAKEN']
            if self.user_repo.get_by_email(pending.email):
                self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return False, MESSAGES['EMAIL_ALREADY_EXISTS']

            is_first = self.user_repo.count() == 0
            user = User(
                username=pending.username,
                email=pending.email,
                is_admin=is_first,
                is_verified=True,
                created_at=datetime.now(timezone.utc),
            )
            user.password_hash = pending.password_hash
            self.user_repo.add(user)
            self.pending_repo.delete(pending)
            self.user_repo.commit()
            return True, ''

        # ── Case 3: no pending state for this email ──
        existing = self.user_repo.get_by_email(email_lc)
        if existing and existing.is_verified:
            return False, MESSAGES['ACCOUNT_ALREADY_VERIFIED']
        return False, MESSAGES['ACCOUNT_NOT_FOUND']

    def resend_verification_code(self, email: str) -> Optional[str]:
        """Generate a fresh OTP for a pending sign-up or pending email update.

        Returns the new code, or ``None`` if there is no live pending record
        for ``email`` (already verified, never registered, or expired).
        """
        email_lc = email.lower()
        now = datetime.now(timezone.utc)

        # Pending sign-up — extend OTP, but not the row's hard TTL.
        pending = self.pending_repo.get_by_email(email_lc)
        if pending:
            if self._as_utc(pending.expires_at) < now:
                # Hard TTL expired; force the user to re-register.
                self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return None
            code = self._make_verification_code()
            pending.verification_code = code
            pending.verification_code_expires_at = (
                now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
            )
            self.pending_repo.commit()
            return code

        # Pending email update for a verified user.
        user = self.user_repo.get_by_pending_email(email_lc)
        if user:
            code = self._make_verification_code()
            user.verification_code = code
            user.verification_code_expires_at = (
                now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
            )
            self.user_repo.commit()
            return code

        return None

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def authenticate(self, identifier: str, password: str) -> Union[User, str, None]:
        """Verify credentials and update last_login on success.

        Returns:
            * The authenticated :class:`User` on success.
            * ``'locked'`` if the account is currently locked from too many
              failed attempts.
            * ``'pending'`` if the identifier matches a staged sign-up that
              hasn't been verified yet.
            * ``None`` if the credentials are invalid.

        On a successful login any legacy (non-bcrypt) password hash is
        transparently rehashed to bcrypt and the failed-attempt counter
        is reset.
        """
        user = self.user_repo.get_by_username_or_email(identifier)
        if user:
            if user.is_locked():
                return 'locked'

            if user.check_password(password):
                # Transparent upgrade to bcrypt for legacy hashes.
                if user.needs_rehash():
                    user.set_password(password)
                user.failed_login_attempts = 0
                user.locked_until = None
                user.last_login = datetime.now(timezone.utc)
                self.user_repo.commit()
                return user

            # Wrong password for an existing user — increment counter.
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=LOCKOUT_DURATION_MINUTES
                )
            self.user_repo.commit()
            return None

        # No verified user. If a pending sign-up exists, surface it so the
        # route can prompt the user to finish verification.
        pending = self.pending_repo.get_by_username(identifier) or \
            self.pending_repo.get_by_email(identifier.lower())
        if pending:
            return 'pending'

        return None

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def update_email(self, user: User, new_email: str, password: str) -> str:
        """Stage a new email address and generate a verification OTP."""
        if not user.check_password(password):
            raise ValueError(MESSAGES['CURRENT_PASSWORD_INCORRECT'])

        code = self._make_verification_code()
        user.pending_email = new_email.lower()
        user.verification_code = code
        user.verification_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        self.user_repo.commit()
        return code

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change user password after verifying the current one."""
        if not user.check_password(current_password):
            raise ValueError(MESSAGES['CURRENT_PASSWORD_INCORRECT'])
        user.set_password(new_password)
        self.user_repo.commit()

    def reset_password_with_token(self, email: str, new_password: str) -> Optional[User]:
        """Set a new password for the user identified by their email."""
        user = self.user_repo.get_by_email(email)
        if not user:
            return None
        user.set_password(new_password)
        # A successful reset implicitly clears any active lockout.
        user.failed_login_attempts = 0
        user.locked_until = None
        self.user_repo.commit()
        return user

    # ------------------------------------------------------------------
    # Account self-deletion (OTP-confirmed)
    # ------------------------------------------------------------------

    def request_account_deletion(self, user: User) -> str:
        code = self._make_verification_code()
        user.deletion_code = code
        user.deletion_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        self.user_repo.commit()
        return code

    def confirm_account_deletion(self, user: User, code: str) -> Tuple[bool, str]:
        if (
            not user.deletion_code
            or not user.deletion_code_expires_at
            or datetime.now(timezone.utc) > self._as_utc(user.deletion_code_expires_at)
            or user.deletion_code != code.strip()
        ):
            return False, MESSAGES['DELETION_INVALID_CODE']

        self.user_repo.delete(user)
        self.user_repo.commit()
        return True, ''

    # ------------------------------------------------------------------
    # Admin-only operations
    # ------------------------------------------------------------------

    def toggle_admin(self, user_id: int, current_user: User) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(MESSAGES['USER_NOT_FOUND'])
        if user.id == current_user.id:
            raise ValueError(MESSAGES['ADMIN_CANNOT_CHANGE_OWN_STATUS'])
        user.is_admin = not user.is_admin
        self.user_repo.commit()
        return user

    def delete_user(self, user_id: int, current_user: User) -> None:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(MESSAGES['USER_NOT_FOUND'])
        if user.id == current_user.id:
            raise ValueError(MESSAGES['ADMIN_CANNOT_DELETE_SELF'])
        self.user_repo.delete(user)
        self.user_repo.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_verification_code() -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return str(secrets.randbelow(900000) + 100000)

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        """Treat a naive (SQLite-roundtripped) datetime as UTC for comparison."""
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
