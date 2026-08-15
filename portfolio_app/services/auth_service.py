"""Authentication service for user management."""

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union

from portfolio_app.models.user import User
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.repositories.pending_registration_repository import (
    PendingRegistrationRepository,
)
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.utils.otp import otp_digest, verify_otp

# Verification code expiry in minutes (the 6-digit OTP)
VERIFICATION_CODE_EXPIRY_MINUTES = 10
# Hard TTL on a staged pending_registration row (independent of OTP refreshes)
PENDING_REGISTRATION_TTL_HOURS = 24

# Brute-force protection
MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30

# OTP brute-force defence: after this many bad codes we wipe the OTP so
# the user has to request a fresh one. Combined with the per-email rate
# limit on /verify-code, this closes the 900K-code brute-force window.
MAX_OTP_ATTEMPTS = 5
USERNAME_MAX_LENGTH = 80
_USERNAME_SAFE_RE = re.compile(r'[^a-z0-9]+')

# Fixed current-scheme bcrypt hash whose random source password was discarded.
# Verifying attacker input against it exercises the same current + legacy
# bcrypt checks as a real wrong password without creating or persisting a user.
_DUMMY_PASSWORD_HASH = (
    '$2b$12$Cy5DRkakgcRAcXpTEgrSKuV2IH01/2lcFoxfCJ7ZSLJghiTNXlOAS'
)


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

    def register(self, email: str, password: str) -> Tuple[PendingRegistration, str]:
        """Stage a new sign-up and generate a 6-digit verification code.

        The account is **not** inserted into the ``user`` table until the
        OTP is confirmed via :meth:`verify_user`. A live pending row for the
        same email is preserved so an unauthenticated retry cannot replace
        its staged credentials; the existing resend flow can issue a new OTP.

        Args:
            email: User's email address (stored lowercase).
            password: Plain-text password (hashed before storing, even in
                the staging table).

        Returns:
            Tuple of (created PendingRegistration, 6-digit verification code).

        Raises:
            ValueError: If the email is already taken by an existing user or
                has a live pending registration.
        """
        email_lc = email.lower()

        # Completed accounts, live email-change reservations, and live staged
        # registrations all own the address for the duration of their
        # respective workflows. Stale state is cleaned by the shared check.
        if self.email_is_unavailable(email_lc):
            raise ValueError(MESSAGES['EMAIL_ALREADY_EXISTS'])

        username = self._generate_username(email_lc)

        token = secrets.token_urlsafe(32)
        code = self._make_verification_code()
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
            verification_code=self._registration_otp_digest(code, token),
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

        # All failure paths return the same generic message so the response
        # can't be used to distinguish "email is registered" from "wrong
        # code" from "expired" from "no pending state at all". Success
        # paths still return the empty string + ok=True.
        FAIL = (False, MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'])

        # ── Case 1: pending email update for an already-verified account ──
        user_pending_email = self._get_live_pending_email_user(email_lc, now)
        if user_pending_email:
            if not verify_otp(
                user_pending_email.verification_code,
                code,
                purpose='email-change',
                context=(
                    str(user_pending_email.id),
                    user_pending_email.pending_email.lower(),
                ),
            ):
                # Burn an attempt; wipe the code (and the staged email) once
                # the cap is hit so the user must request a fresh OTP.
                user_pending_email.verification_code_failed_attempts = (
                    (user_pending_email.verification_code_failed_attempts or 0) + 1
                )
                if user_pending_email.verification_code_failed_attempts >= MAX_OTP_ATTEMPTS:
                    self._clear_pending_email_state(user_pending_email)
                self.user_repo.commit()
                return FAIL

            user_pending_email.email = user_pending_email.pending_email
            self._clear_pending_email_state(user_pending_email)
            self.user_repo.commit()
            return True, ''

        # ── Case 2: new sign-up confirmation ──
        pending = self.pending_repo.get_by_email(email_lc)
        if pending:
            expires_at = self._as_utc(pending.verification_code_expires_at)
            if now > expires_at:
                return FAIL
            if not verify_otp(
                pending.verification_code,
                code,
                purpose='registration',
                context=(pending.token,),
            ):
                # Same per-OTP lockout as Case 1, but the staged-registration
                # columns (verification_code / expires_at) are NOT NULL, so
                # we burn the entire pending row instead of nulling fields.
                # The user must re-register from scratch — the strictest
                # behaviour is the right default for a financial app.
                pending.failed_otp_attempts = (pending.failed_otp_attempts or 0) + 1
                if pending.failed_otp_attempts >= MAX_OTP_ATTEMPTS:
                    self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return FAIL

            # Re-check live user table for late collisions before promoting.
            # These race-window failures also collapse into the generic
            # message — the legitimate user retries and succeeds in the
            # normal sign-up flow; the attacker learns nothing extra.
            if self.user_repo.get_by_username(pending.username):
                self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return FAIL
            if self.user_repo.get_by_email(pending.email):
                self.pending_repo.delete(pending)
                self.pending_repo.commit()
                return FAIL

            # Verified registrations always create ordinary user accounts.
            # Cross-user privilege is not part of the application contract.
            user = User(
                username=pending.username,
                email=pending.email,
                is_verified=True,
                created_at=datetime.now(timezone.utc),
            )
            user.password_hash = pending.password_hash
            self.user_repo.add(user)
            self.pending_repo.delete(pending)
            self.user_repo.commit()
            return True, ''

        # ── Case 3: no pending state for this email ──
        # Was previously two distinct messages (already-verified vs
        # not-found). Collapsing them removes the enumeration oracle.
        return FAIL

    def resend_verification_code(self, email: str) -> Optional[str]:
        """Generate a fresh OTP for a pending sign-up or pending email update.

        Returns the new code, or ``None`` if there is no live pending record
        for ``email`` (already verified, never registered, or expired).
        """
        email_lc = email.lower()
        now = datetime.now(timezone.utc)

        # A live email-change claim takes the same precedence here as it does
        # during verification. Expired/malformed state is cleared and cannot
        # be revived by resend; the authenticated user must start over.
        user = self._get_live_pending_email_user(email_lc, now)
        if user:
            code = self._make_verification_code()
            user.verification_code = self._email_change_otp_digest(
                code,
                user,
                user.pending_email,
            )
            user.verification_code_expires_at = (
                now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
            )
            user.verification_code_failed_attempts = 0
            self.user_repo.commit()
            return code

        # Pending sign-up — extend OTP, but not the row's hard TTL.
        self._purge_expired_pending_registrations(now)
        pending = self.pending_repo.get_by_email(email_lc)
        if pending:
            code = self._make_verification_code()
            pending.verification_code = self._registration_otp_digest(
                code,
                pending.token,
            )
            pending.verification_code_expires_at = (
                now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
            )
            # Fresh code, fresh attempt counter.
            pending.failed_otp_attempts = 0
            self.pending_repo.commit()
            return code

        return None

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def authenticate(self, identifier: str, password: str) -> Union[User, str, None]:
        """Verify credentials and update last_login on success.

        Returns:
            * The authenticated :class:`User` on success.
            * ``'locked'`` if the account is currently locked and the
              submitted password is correct.
            * ``'pending'`` if the identifier matches a staged sign-up that
              hasn't been verified yet.
            * ``None`` if the credentials are invalid.

        On a successful login any legacy (non-bcrypt) password hash is
        transparently rehashed to bcrypt and the failed-attempt counter
        is reset.
        """
        user = self.user_repo.get_by_username_or_email(identifier)
        if user:
            password_matches = user.check_password(password)

            # Persisted unverified rows can exist in legacy/imported data even
            # though current registrations remain staged until verification.
            # Verify the submitted password first to preserve the login timing
            # contract, then reject without exposing verification or lockout
            # state and before any successful-login mutation or rehash.
            if password_matches and not user.is_verified:
                return None

            if user.is_locked():
                # Wrong guesses against locked accounts stay generic and do
                # not extend the existing lockout. A legitimate user who
                # proves the password may still be told to wait.
                return 'locked' if password_matches else None

            if password_matches:
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
        self._verify_dummy_password(password)
        if pending:
            return 'pending'

        return None

    @staticmethod
    def _verify_dummy_password(password: str) -> None:
        """Burn the real wrong-password verification path without DB state."""
        dummy_user = User(password_hash=_DUMMY_PASSWORD_HASH)
        dummy_user.check_password(password)

    # ------------------------------------------------------------------
    # Password management
    # ------------------------------------------------------------------

    def update_email(self, user: User, new_email: str, password: str) -> str:
        """Stage a new email address and generate a verification OTP."""
        if not user.check_password(password):
            raise ValueError(MESSAGES['CURRENT_PASSWORD_INCORRECT'])

        email_lc = new_email.lower()
        if self.email_is_unavailable(email_lc):
            raise ValueError(MESSAGES['EMAIL_IN_USE'])

        code = self._make_verification_code()
        user.pending_email = email_lc
        user.verification_code = self._email_change_otp_digest(
            code,
            user,
            email_lc,
        )
        user.verification_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        user.verification_code_failed_attempts = 0
        self.user_repo.commit()
        return code

    def email_is_unavailable(self, email: str) -> bool:
        """Return whether an email is owned by a live account workflow.

        A pending email change owns its target only while its complete OTP
        state is live. Stale user state and expired staged registrations are
        cleaned here so routes/forms do not duplicate expiry policy.
        """
        email_lc = email.lower()
        now = datetime.now(timezone.utc)
        live_pending_user = self._get_live_pending_email_user(email_lc, now)
        self._purge_expired_pending_registrations(now)
        return (
            self.user_repo.get_by_email(email_lc) is not None
            or live_pending_user is not None
            or self.pending_repo.get_by_email(email_lc) is not None
        )

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change user password after verifying the current one."""
        if not user.check_password(current_password):
            raise ValueError(MESSAGES['CURRENT_PASSWORD_INCORRECT'])
        user.set_password(new_password)
        user.auth_generation = User.auth_generation + 1
        self.user_repo.commit()

    def begin_password_reset(self, user: User) -> str:
        """Stamp ``user`` with a fresh single-use reset jti and return it.

        Persisting the jti turns the otherwise-stateless itsdangerous token
        into a one-shot credential: the matching call site
        (``reset_password_with_token``) refuses any redemption whose jti
        doesn't match the stored value, and clears the jti on success.
        """
        jti = secrets.token_hex(16)  # 32 hex chars, fits the column
        user.password_reset_jti = jti
        self.user_repo.commit()
        return jti

    def reset_password_with_token(
        self, email: str, jti: str, new_password: str
    ) -> Optional[User]:
        """Set a new password if ``(email, jti)`` matches the live user.

        Returns ``None`` for any of: unknown email, no live jti, jti
        mismatch (token already used or never issued for this user). On
        success one conditional database UPDATE clears the jti, resets
        lockouts, advances the authentication generation, and stores a
        password hash produced under the current scheme.
        """
        if not jti:
            return None

        # Cheap advisory rejection before bcrypt. The conditional UPDATE
        # below remains authoritative if this state changes after the read.
        user = self.user_repo.get_by_email(email)
        if not user:
            return None
        stored = user.password_reset_jti or ''
        if not stored or not hmac.compare_digest(stored, jti):
            return None

        # Reuse the model's authoritative bcrypt hashing behavior without
        # attaching a transient object to the database session.
        password_holder = User()
        password_holder.set_password(new_password)

        consumed = self.user_repo.consume_password_reset(
            email,
            jti,
            password_holder.password_hash,
        )
        if not consumed:
            return None

        return self.user_repo.get_by_email(email)

    # ------------------------------------------------------------------
    # Account self-deletion (OTP-confirmed)
    # ------------------------------------------------------------------

    def request_account_deletion(self, user: User) -> str:
        code = self._make_verification_code()
        user.deletion_code = otp_digest(
            code,
            purpose='account-deletion',
            context=(str(user.id),),
        )
        user.deletion_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        user.deletion_code_failed_attempts = 0
        self.user_repo.commit()
        return code

    def cancel_account_deletion(self, user: User) -> None:
        """Revoke every credential associated with account deletion."""
        user.deletion_code = None
        user.deletion_code_expires_at = None
        user.deletion_code_failed_attempts = 0
        self.user_repo.commit()

    def confirm_account_deletion(self, user: User, code: str) -> Tuple[bool, str]:
        # Reject upfront if the code was never set or has expired — the same
        # generic message hides whether the user is in the deletion flow.
        if not self._deletion_code_is_live(user):
            return False, MESSAGES['DELETION_INVALID_CODE']

        if not verify_otp(
            user.deletion_code,
            code.strip(),
            purpose='account-deletion',
            context=(str(user.id),),
        ):
            user.deletion_code_failed_attempts = (
                (user.deletion_code_failed_attempts or 0) + 1
            )
            if user.deletion_code_failed_attempts >= MAX_OTP_ATTEMPTS:
                # Burn the code so the attacker can't keep guessing.
                user.deletion_code = None
                user.deletion_code_expires_at = None
                user.deletion_code_failed_attempts = 0
            self.user_repo.commit()
            return False, MESSAGES['DELETION_INVALID_CODE']

        user.deletion_code_failed_attempts = 0
        self.user_repo.delete(user)
        self.user_repo.commit()
        return True, ''

    def _deletion_code_is_live(self, user: User) -> bool:
        return (
            bool(user.deletion_code)
            and bool(user.deletion_code_expires_at)
            and datetime.now(timezone.utc) <= self._as_utc(user.deletion_code_expires_at)
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_live_pending_email_user(
        self,
        email: str,
        now: datetime,
    ) -> Optional[User]:
        """Return the live pending-email owner, cleaning stale state."""
        user = self.user_repo.get_by_pending_email(email)
        if not user:
            return None
        if self._pending_email_is_live(user, now):
            return user

        self._clear_pending_email_state(user)
        self.user_repo.commit()
        return None

    def _pending_email_is_live(self, user: User, now: datetime) -> bool:
        return (
            bool(user.pending_email)
            and bool(user.verification_code)
            and bool(user.verification_code_expires_at)
            and now <= self._as_utc(user.verification_code_expires_at)
        )

    @staticmethod
    def _clear_pending_email_state(user: User) -> None:
        user.pending_email = None
        user.verification_code = None
        user.verification_code_expires_at = None
        user.verification_code_failed_attempts = 0

    def _purge_expired_pending_registrations(self, now: datetime) -> None:
        if self.pending_repo.purge_expired(now):
            self.pending_repo.commit()

    @staticmethod
    def _registration_otp_digest(code: str, token: str) -> str:
        return otp_digest(
            code,
            purpose='registration',
            context=(token,),
        )

    @staticmethod
    def _email_change_otp_digest(code: str, user: User, pending_email: str) -> str:
        return otp_digest(
            code,
            purpose='email-change',
            context=(str(user.id), pending_email.lower()),
        )

    @staticmethod
    def _make_verification_code() -> str:
        """Generate a cryptographically random 6-digit OTP code."""
        return str(secrets.randbelow(900000) + 100000)

    def _generate_username(self, email: str) -> str:
        """Create a stable internal username from an email prefix."""
        prefix = (email.split('@', 1)[0] or '').lower()
        base = _USERNAME_SAFE_RE.sub('_', prefix).strip('_') or 'user'
        base = base[:USERNAME_MAX_LENGTH].strip('_') or 'user'

        if self._username_available(base):
            return base

        for suffix_num in range(2, 10000):
            suffix = f'_{suffix_num}'
            candidate = f'{base[:USERNAME_MAX_LENGTH - len(suffix)].rstrip("_")}{suffix}'
            if self._username_available(candidate):
                return candidate

        while True:
            suffix = f'_{secrets.token_hex(3)}'
            candidate = f'{base[:USERNAME_MAX_LENGTH - len(suffix)].rstrip("_")}{suffix}'
            if self._username_available(candidate):
                return candidate

    def _username_available(self, username: str) -> bool:
        return (
            self.user_repo.get_by_username(username) is None
            and self.pending_repo.get_by_username(username) is None
        )

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        """Treat a naive (SQLite-roundtripped) datetime as UTC for comparison."""
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
