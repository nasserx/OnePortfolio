"""Passwordless authentication and account-security service."""

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError

from portfolio_app.models.auth_challenge import AuthChallenge
from portfolio_app.models.pending_registration import PendingRegistration
from portfolio_app.models.user import User
from portfolio_app.repositories.auth_challenge_repository import AuthChallengeRepository
from portfolio_app.repositories.pending_registration_repository import PendingRegistrationRepository
from portfolio_app.repositories.user_repository import UserRepository
from portfolio_app.utils.messages import MESSAGES
from portfolio_app.utils.otp import otp_digest, verify_otp


VERIFICATION_CODE_EXPIRY_MINUTES = 10
PENDING_REGISTRATION_TTL_HOURS = 24
MAX_OTP_ATTEMPTS = 5
USERNAME_MAX_LENGTH = 80
AUTHENTICATION_PURPOSE = 'authentication'
RECENT_AUTH_PURPOSE = 'recent-auth'
_USERNAME_SAFE_RE = re.compile(r'[^a-z0-9]+')


@dataclass(frozen=True)
class ChallengeIssue:
    token: str = field(repr=False)
    recipient: str = field(repr=False)
    code: str = field(repr=False)


class AuthService:
    """Own passwordless challenges, registration, and account OTP workflows."""

    def __init__(self, user_repo: UserRepository,
                 pending_repo: PendingRegistrationRepository,
                 challenge_repo: AuthChallengeRepository):
        self.user_repo = user_repo
        self.pending_repo = pending_repo
        self.challenge_repo = challenge_repo

    def begin_authentication(self, email: str) -> ChallengeIssue:
        """Issue an indistinguishable challenge for an existing or new email."""
        email_lc = email.strip().lower()
        now = datetime.now(timezone.utc)
        self._purge_expired_pending_registrations(now, commit=False)
        user = self.user_repo.get_by_email(email_lc)
        pending = None
        if user is None:
            pending = self.pending_repo.get_by_email(email_lc)
            if pending is None:
                pending = PendingRegistration(
                    username=self._generate_username(email_lc),
                    email=email_lc,
                    created_at=now,
                    expires_at=now + timedelta(hours=PENDING_REGISTRATION_TTL_HOURS),
                )
                self.pending_repo.add(pending)
                self.pending_repo.flush()
        try:
            issue = self._issue_challenge(
                AUTHENTICATION_PURPOSE, user=user, pending=pending, now=now,
            )
            self.user_repo.commit()
            return issue
        except IntegrityError:
            self.user_repo.db.session.rollback()
            user = self.user_repo.get_by_email(email_lc)
            pending = None if user else self.pending_repo.get_by_email(email_lc)
            if user is None and pending is None:
                raise
            issue = self._issue_challenge(
                AUTHENTICATION_PURPOSE, user=user, pending=pending, now=now,
            )
            self.user_repo.commit()
            return issue

    def begin_recent_authentication(self, user: User) -> ChallengeIssue:
        issue = self._issue_challenge(
            RECENT_AUTH_PURPOSE,
            user=user,
            pending=None,
            now=datetime.now(timezone.utc),
        )
        self.user_repo.commit()
        return issue

    def resend_challenge(self, token: str,
                         expected_purpose: str) -> Optional[ChallengeIssue]:
        """Rotate code, digest, expiry, and attempt count for an open challenge."""
        challenge = self.challenge_repo.get_by_token(token)
        if not self._challenge_target_is_valid(challenge, expected_purpose):
            return None
        now = datetime.now(timezone.utc)
        if (challenge.pending_registration is not None
                and now > self._as_utc(challenge.pending_registration.expires_at)):
            return None
        code = self._make_verification_code()
        recipient = self._challenge_recipient(challenge)
        challenge.code_digest = self._challenge_digest(
            code, challenge.token, challenge.purpose, recipient,
        )
        challenge.expires_at = self._challenge_expires_at(
            now, challenge.pending_registration,
        )
        challenge.failed_attempts = 0
        self.challenge_repo.commit()
        return ChallengeIssue(challenge.token, recipient, code)

    def verify_challenge(self, token: str, code: str,
                         expected_purpose: str) -> Optional[User]:
        """Atomically consume a live OTP and return its authenticated user."""
        challenge = self.challenge_repo.get_by_token(token)
        if not self._challenge_target_is_valid(challenge, expected_purpose):
            return None
        now = datetime.now(timezone.utc)
        if (now > self._as_utc(challenge.expires_at)
                or challenge.failed_attempts >= MAX_OTP_ATTEMPTS):
            return None
        pending = challenge.pending_registration
        if pending is not None and now > self._as_utc(pending.expires_at):
            return None
        recipient = self._challenge_recipient(challenge)
        supplied = code.strip()
        if not verify_otp(
            challenge.code_digest,
            supplied,
            purpose=challenge.purpose,
            context=(challenge.token, recipient),
        ):
            self.challenge_repo.record_failed_attempt(token, now, MAX_OTP_ATTEMPTS)
            self.challenge_repo.commit()
            return None
        expected_digest = self._challenge_digest(
            supplied, challenge.token, challenge.purpose, recipient,
        )
        if not self.challenge_repo.claim(
            token, expected_digest, now, MAX_OTP_ATTEMPTS,
        ):
            self.challenge_repo.db.session.rollback()
            return None
        user = challenge.user
        if user is None and pending is not None:
            user = self.user_repo.get_by_email(pending.email)
            if user is None:
                username = pending.username
                if self.user_repo.get_by_username(username):
                    username = self._generate_username(pending.email)
                user = User(
                    username=username,
                    email=pending.email,
                    password_hash=None,
                    is_verified=True,
                    created_at=now,
                )
                self.user_repo.add(user)
                self.user_repo.flush()
            self.pending_repo.delete(pending)
        if user is None:
            self.challenge_repo.db.session.rollback()
            return None
        user.is_verified = True
        user.last_login = now
        self.user_repo.commit()
        return user

    def stage_email_change(self, user: User, new_email: str) -> str:
        email_lc = new_email.strip().lower()
        if email_lc == (user.email or '').lower() or self.email_is_unavailable(email_lc):
            raise ValueError(MESSAGES['EMAIL_IN_USE'])
        code = self._make_verification_code()
        user.pending_email = email_lc
        user.verification_code = self._email_change_otp_digest(code, user, email_lc)
        user.verification_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        user.verification_code_failed_attempts = 0
        self.user_repo.commit()
        return code

    def verify_email_change(self, user: User, code: str) -> Tuple[bool, str]:
        now = datetime.now(timezone.utc)
        fail = (False, MESSAGES['VERIFICATION_CODE_INVALID_OR_EXPIRED'])
        if not self._pending_email_is_live(user, now):
            return fail
        if not verify_otp(
            user.verification_code,
            code.strip(),
            purpose='email-change',
            context=(str(user.id), user.pending_email.lower()),
        ):
            user.verification_code_failed_attempts += 1
            if user.verification_code_failed_attempts >= MAX_OTP_ATTEMPTS:
                self._clear_pending_email_state(user)
            self.user_repo.commit()
            return fail
        user.email = user.pending_email
        self._clear_pending_email_state(user)
        self.user_repo.commit()
        return True, ''

    def resend_email_change(self, user: User) -> Optional[str]:
        if not user.pending_email:
            return None
        code = self._make_verification_code()
        user.verification_code = self._email_change_otp_digest(
            code, user, user.pending_email,
        )
        user.verification_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        user.verification_code_failed_attempts = 0
        self.user_repo.commit()
        return code

    def email_is_unavailable(self, email: str) -> bool:
        email_lc = email.strip().lower()
        now = datetime.now(timezone.utc)
        live_pending_user = self._get_live_pending_email_user(email_lc, now)
        self._purge_expired_pending_registrations(now)
        return (
            self.user_repo.get_by_email(email_lc) is not None
            or live_pending_user is not None
            or self.pending_repo.get_by_email(email_lc) is not None
        )

    def request_account_deletion(self, user: User) -> str:
        code = self._make_verification_code()
        user.deletion_code = otp_digest(
            code, purpose='account-deletion', context=(str(user.id),),
        )
        user.deletion_code_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        )
        user.deletion_code_failed_attempts = 0
        self.user_repo.commit()
        return code

    def cancel_account_deletion(self, user: User) -> None:
        user.deletion_code = None
        user.deletion_code_expires_at = None
        user.deletion_code_failed_attempts = 0
        self.user_repo.commit()

    def confirm_account_deletion(self, user: User, code: str) -> Tuple[bool, str]:
        if not self._deletion_code_is_live(user):
            return False, MESSAGES['DELETION_INVALID_CODE']
        if not verify_otp(
            user.deletion_code,
            code.strip(),
            purpose='account-deletion',
            context=(str(user.id),),
        ):
            user.deletion_code_failed_attempts += 1
            if user.deletion_code_failed_attempts >= MAX_OTP_ATTEMPTS:
                user.deletion_code = None
                user.deletion_code_expires_at = None
                user.deletion_code_failed_attempts = 0
            self.user_repo.commit()
            return False, MESSAGES['DELETION_INVALID_CODE']
        self.user_repo.delete(user)
        self.user_repo.commit()
        return True, ''

    def _issue_challenge(self, purpose: str, *, user: Optional[User],
                         pending: Optional[PendingRegistration],
                         now: datetime) -> ChallengeIssue:
        if (user is None) == (pending is None):
            raise ValueError('An authentication challenge requires one target.')
        if user is not None:
            self.challenge_repo.delete_open_for_user(user.id, purpose)
            recipient = user.email
        else:
            self.challenge_repo.delete_open_for_pending(pending.id, purpose)
            recipient = pending.email
        token = secrets.token_urlsafe(32)
        code = self._make_verification_code()
        self.challenge_repo.add(AuthChallenge(
            token=token,
            purpose=purpose,
            user_id=user.id if user else None,
            pending_registration_id=pending.id if pending else None,
            code_digest=self._challenge_digest(code, token, purpose, recipient),
            expires_at=self._challenge_expires_at(now, pending),
            failed_attempts=0,
            created_at=now,
        ))
        return ChallengeIssue(token, recipient, code)

    @classmethod
    def _challenge_expires_at(cls, now: datetime,
                              pending: Optional[PendingRegistration]) -> datetime:
        """Cap registration OTPs at their owning registration's hard expiry."""
        otp_expiry = now + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)
        if pending is None:
            return otp_expiry
        return min(otp_expiry, cls._as_utc(pending.expires_at))

    @staticmethod
    def _challenge_target_is_valid(challenge, expected_purpose: str) -> bool:
        return bool(
            challenge is not None
            and challenge.purpose == expected_purpose
            and challenge.consumed_at is None
            and ((challenge.user is None) != (challenge.pending_registration is None))
        )

    @staticmethod
    def _challenge_recipient(challenge: AuthChallenge) -> str:
        return challenge.user.email if challenge.user else challenge.pending_registration.email

    @staticmethod
    def _challenge_digest(code: str, token: str, purpose: str, email: str) -> str:
        return otp_digest(
            code, purpose=purpose, context=(token, email.lower()),
        )

    def _deletion_code_is_live(self, user: User) -> bool:
        return bool(
            user.deletion_code and user.deletion_code_expires_at
            and datetime.now(timezone.utc) <= self._as_utc(user.deletion_code_expires_at)
        )

    def _get_live_pending_email_user(self, email: str,
                                     now: datetime) -> Optional[User]:
        user = self.user_repo.get_by_pending_email(email)
        if not user:
            return None
        if self._pending_email_is_live(user, now):
            return user
        self._clear_pending_email_state(user)
        self.user_repo.commit()
        return None

    def _pending_email_is_live(self, user: User, now: datetime) -> bool:
        return bool(
            user.pending_email and user.verification_code
            and user.verification_code_expires_at
            and now <= self._as_utc(user.verification_code_expires_at)
        )

    @staticmethod
    def _clear_pending_email_state(user: User) -> None:
        user.pending_email = None
        user.verification_code = None
        user.verification_code_expires_at = None
        user.verification_code_failed_attempts = 0

    def _purge_expired_pending_registrations(self, now: datetime,
                                              *, commit: bool = True) -> None:
        if self.pending_repo.purge_expired(now) and commit:
            self.pending_repo.commit()

    @staticmethod
    def _email_change_otp_digest(code: str, user: User, email: str) -> str:
        return otp_digest(
            code, purpose='email-change', context=(str(user.id), email.lower()),
        )

    @staticmethod
    def _make_verification_code() -> str:
        return str(secrets.randbelow(900000) + 100000)

    def _generate_username(self, email: str) -> str:
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
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
