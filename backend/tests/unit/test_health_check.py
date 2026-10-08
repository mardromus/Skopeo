"""Unit test for health check script."""

from scripts.health_check import check_health


def test_check_health_returns_true():
    assert check_health() is True
