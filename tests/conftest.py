"""Pytest test configuration and fixtures."""

import gc
import pytest


@pytest.fixture(autouse=True)
def _cleanup_tk_cycles():
    """Ensure cyclic garbage is collected synchronously on main thread after each test."""
    yield
    gc.collect()
