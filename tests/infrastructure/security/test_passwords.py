"""Real Argon2id password hashing behavior."""

from guojing.infrastructure.security.passwords import Argon2PasswordHasher


def test_argon2id_hashes_are_salted_and_verifiable() -> None:
    hasher = Argon2PasswordHasher()

    first = hasher.hash("correct horse battery staple")
    second = hasher.hash("correct horse battery staple")

    assert first.startswith("$argon2id$")
    assert first != second
    assert hasher.verify_and_update("correct horse battery staple", first)[0] is True
    assert hasher.verify_and_update("wrong password", first) == (False, None)
