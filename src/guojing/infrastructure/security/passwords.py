"""Argon2id implementation of the application password hashing port."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    """Hash passwords and transparently upgrade old Argon2 parameters."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify_and_update(self, password: str, encoded_hash: str) -> tuple[bool, str | None]:
        try:
            valid = self._hasher.verify(encoded_hash, password)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False, None
        replacement = (
            self._hasher.hash(password) if self._hasher.check_needs_rehash(encoded_hash) else None
        )
        return valid, replacement
