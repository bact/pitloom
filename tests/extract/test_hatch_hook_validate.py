# ruff: noqa: F403, F405
from __future__ import annotations

from typing import Any

import pytest

from pitloom.plugins.hatch import (  # noqa: E402
    _validate_config,
)

from .conftest import *


def test_validate_config_defaults_pass() -> None:
    """Empty config (all defaults) must not raise."""
    _validate_config({})


def test_validate_config_valid_values_pass() -> None:
    """The only supported key, 'enabled', must not raise."""
    _validate_config({"enabled": True})


@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("enabled", "yes", "'enabled' must be a boolean"),
        ("enabled", 1, "'enabled' must be a boolean"),
    ],
)
def test_validate_config_invalid_raises(field: str, bad_value: Any, match: str) -> None:
    """Invalid field type or value must raise ``ValueError`` with a clear message."""
    with pytest.raises(ValueError, match=match):
        _validate_config({field: bad_value})


@pytest.mark.parametrize(
    ("key", "new_location"),
    [
        ("sbom-basename", r"\[tool\.pitloom\] sbom-basename"),
        ("fragments", r"\[tool\.pitloom\.fragment\] files"),
        ("creator-name", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creator-email", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creator-type", r"\[\[tool\.pitloom\.creator\]\]"),
        ("creation-tool", r"\[\[tool\.pitloom\.creation-tool\]\]"),
    ],
)
def test_validate_config_moved_key_raises(key: str, new_location: str) -> None:
    """A key that moved to [tool.pitloom]/[tool.pitloom.creation] must raise,
    pointing at its new location, rather than being silently ignored."""
    with pytest.raises(ValueError, match=new_location):
        _validate_config({key: "whatever"})


def test_validate_config_unknown_key_raises() -> None:
    """An unrecognised key must raise rather than being silently ignored."""
    with pytest.raises(ValueError, match="unknown key"):
        _validate_config({"typo-field": "x"})
