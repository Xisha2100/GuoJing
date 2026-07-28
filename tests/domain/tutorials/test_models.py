"""Tests for tutorial graph value-object invariants."""

import pytest

from guojing.domain.tutorials.models import AppIdentity, NormalizedBounds, SemanticLocator


def test_normalized_bounds_accept_screen_relative_rectangle() -> None:
    bounds = NormalizedBounds(left=0.1, top=0.2, right=0.8, bottom=0.9)

    assert bounds.right == 0.8


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ((-0.1, 0.1, 0.5, 0.5), "between 0 and 1"),
        ((float("nan"), 0.1, 0.5, 0.5), "between 0 and 1"),
        ((0.5, 0.1, 0.5, 0.5), "left must be smaller"),
        ((0.1, 0.8, 0.5, 0.2), "top must be smaller"),
    ],
)
def test_normalized_bounds_reject_invalid_rectangles(
    coordinates: tuple[float, float, float, float],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        NormalizedBounds(*coordinates)


def test_semantic_locator_requires_meaningful_selector() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SemanticLocator()


def test_app_identity_requires_positive_android_version_code() -> None:
    with pytest.raises(ValueError, match="positive"):
        AppIdentity("com.tencent.mm", "8.0.60", 0)
