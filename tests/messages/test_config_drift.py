# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The configuration families' closed tables against the readers they
name: the tables against the known keys, each ``one-of-*`` text against its
reader's choices, the budget minimum, and every moved key's destination.
:mod:`pitloom.messages` cannot import the configuration readers (they
import it), so only the tests hold them together; and the two import in
either order.

See also: tests/messages/test_config.py (the mechanism).
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys

import pytest

from pitloom.core._config_keys import KNOWN_ENTRY_KEYS, KNOWN_KEYS
from pitloom.core._config_legacy import (
    _MOVED_CREATION_KEYS,
    _MOVED_FLAT_KEYS,
    _MOVED_TOP_LEVEL_TABLES,
)
from pitloom.core._config_types import VALID_CONTENT_TYPE_METHODS
from pitloom.core.config import (
    _VALID_PRESERVE_SOURCE_METADATA,
    _VALID_PROVENANCE_DETAIL,
    _VALID_PROVENANCE_FORMATS,
)
from pitloom.core.creation import VALID_CREATOR_TYPES
from pitloom.core.provenance import MIN_SOURCE_METADATA_BYTES
from pitloom.messages import TOPIC_TITLES, topic_of
from pitloom.messages.config import (
    ARRAY_TABLES,
    BUDGET_MINIMUM,
    CONFIG_INVALID,
    CONFIG_MALFORMED,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
    DATETIME_UNPINNED,
    DESTINATIONS,
    EXPECTED,
    SOURCE_DATE_EPOCH_INVALID,
    TABLES,
)
from pitloom.plugins._hatch_config import _MOVED_KEYS

_ROOT = "tool.pitloom"
_ENTRIES = (
    CONFIG_INVALID,
    CONFIG_MALFORMED,
    CONFIG_MOVED,
    CONFIG_UNKNOWN_KEY,
    DATETIME_UNPINNED,
    SOURCE_DATE_EPOCH_INVALID,
)


@pytest.mark.parametrize(
    ("expected", "choices"),
    [
        ("one-of-format", _VALID_PROVENANCE_FORMATS),
        ("one-of-detail", _VALID_PROVENANCE_DETAIL),
        ("one-of-preserve", _VALID_PRESERVE_SOURCE_METADATA),
        ("one-of-method", VALID_CONTENT_TYPE_METHODS),
        ("creator-type", VALID_CREATOR_TYPES),
    ],
    ids=["format", "detail", "preserve", "method", "creator-type"],
)
def test_a_choice_text_lists_the_readers_choices(
    expected: str, choices: frozenset[str]
) -> None:
    assert EXPECTED[expected] == "one of " + ", ".join(sorted(choices))


def test_the_budget_minimum_is_the_providers() -> None:
    assert BUDGET_MINIMUM == MIN_SOURCE_METADATA_BYTES
    assert EXPECTED["budget"].endswith(f"at least {MIN_SOURCE_METADATA_BYTES}")


def test_the_tables_are_the_known_tables() -> None:
    known = {_ROOT + (f".{name}" if name else "") for name in KNOWN_KEYS}
    assert known == set(TABLES) - {"tool", "tool.hatch.build.hooks.pitloom"}


def test_the_arrays_of_tables_are_the_known_arrays() -> None:
    """``files`` holds inline tables under a key, so a place names it as a
    key (``[tool.pitloom.fragment] files entry 0``), not as an array."""
    arrays = {
        ".".join(filter(None, (_ROOT, name, key)))
        for name, key in KNOWN_ENTRY_KEYS
        if (name, key) != ("fragment", "files")
    }
    assert arrays == set(ARRAY_TABLES)


@pytest.mark.parametrize(
    "moved",
    [_MOVED_CREATION_KEYS, _MOVED_TOP_LEVEL_TABLES, _MOVED_FLAT_KEYS, _MOVED_KEYS],
    ids=["creation", "top-level", "flat", "hook"],
)
def test_every_destination_is_in_the_table(moved: dict[str, str]) -> None:
    """The readers' moved-key tables name a destination of
    :data:`DESTINATIONS` (the hook's table is a second copy, not shared)."""
    assert set(moved.values()) <= set(DESTINATIONS)


def test_every_destination_is_named_by_a_reader() -> None:
    named = {
        d
        for moved in (
            _MOVED_CREATION_KEYS,
            _MOVED_TOP_LEVEL_TABLES,
            _MOVED_FLAT_KEYS,
            _MOVED_KEYS,
        )
        for d in moved.values()
    }
    assert set(DESTINATIONS) <= named


def test_the_families_are_on_the_configuration_page() -> None:
    assert list(TOPIC_TITLES).index("config") == list(TOPIC_TITLES).index("options") + 1
    assert {topic_of(entry.code) for entry in _ENTRIES} == {"config"}
    assert {entry.since for entry in _ENTRIES} == {"0.25.0"}


@pytest.mark.parametrize(
    "first",
    ["pitloom.messages.config", "pitloom.core._config_parse"],
    ids=["messages-first", "reader-first"],
)
def test_the_catalogue_and_the_readers_import_in_either_order(first: str) -> None:
    second = {
        "pitloom.messages.config": "pitloom.core._config_parse",
        "pitloom.core._config_parse": "pitloom.messages.config",
    }[first]
    code = f"import {first}; import {second}"
    done = subprocess.run(  # nosec B603
        [sys.executable, "-c", code], capture_output=True, check=False, timeout=120
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
