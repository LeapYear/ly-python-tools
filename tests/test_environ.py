"""Test the environment helpers."""
from __future__ import annotations

import os
from ly_python_tools.pyproper import environ


def test_environ():
    """Test that context manager environ works as expected."""
    key = "__TEST_VAR__"
    value = "__TEST_VAR_VALUE__"

    old_env = os.environ.copy()
    assert key not in os.environ
    with environ(**{key: value}):
        assert os.environ[key] == value
    assert os.environ == old_env
