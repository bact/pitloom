# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pitloom Hatchling build hook's config validation."""

from __future__ import annotations

from typing import Any

import pytest

from pitloom.plugins._hatch_config import validate_config


def test_validate_config_defaults_pass() -> None:
    """Empty config (all defaults) must not raise."""
    validate_config({})


@pytest.mark.parametrize(
    "key",
    [
        "enabled",
        "enable-by-default",
        "dependencies",
        "require-runtime-dependencies",
        "require-runtime-features",
    ],
)
def test_validate_config_valid_values_pass(key: str) -> None:
    """'enabled' and the keys Hatchling itself reads from a hook's table must
    not raise."""
    validate_config({key: True})


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
        validate_config({field: bad_value})


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
        validate_config({key: "whatever"})


def test_validate_config_unknown_key_raises() -> None:
    """An unrecognised key must raise rather than being silently ignored."""
    with pytest.raises(ValueError, match="unknown key"):
        validate_config({"typo-field": "x"})
