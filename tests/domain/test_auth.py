"""Administrator identity and password policy tests."""

import pytest

from guojing.domain.auth import normalize_username, require_valid_password


def test_username_is_normalized_to_a_canonical_login() -> None:
    assert normalize_username("  Family.Admin  ") == "family.admin"


@pytest.mark.parametrize("username", ["ab", "bad name", "admin@home", "_admin"])
def test_username_rejects_ambiguous_or_unsupported_values(username: str) -> None:
    with pytest.raises(ValueError):
        normalize_username(username)


def test_password_policy_preserves_unicode_and_spaces() -> None:
    require_valid_password("家人的 安全 长密码 2026")


@pytest.mark.parametrize("password", ["short", " " * 12, "a" * 257])
def test_password_policy_rejects_unsafe_lengths(password: str) -> None:
    with pytest.raises(ValueError):
        require_valid_password(password)
