# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :meth:`pitloom.id_registry.IdRegistry.promote_alias`.

See also: test_registry_generate_promote.py (``generate`` using it).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE, IdRegistry
from tests.registry_helpers import entries_of, make_registry

_OLD, _NEW = "demo/x.py", "src/demo/x.py"
_HASH = "ab" * 32


def _held() -> IdRegistry:
    return make_registry(
        {
            (FILE_TYPE, _OLD): ("https://spdx.org/spdxdocs/test-1#File-1", _HASH),
            (AI_PACKAGE_TYPE, _OLD): ("https://spdx.org/spdxdocs/test-1#AIP-4", None),
        }
    )


def test_promote_alias_moves_the_entry_and_mints_nothing() -> None:
    registry = _held()
    before = dict(registry.elements)
    counters = dict(registry.id_counters)

    assert registry.promote_alias(FILE_TYPE, _OLD, _NEW) is True

    assert registry.elements[(FILE_TYPE, _NEW)] == before[(FILE_TYPE, _OLD)]
    assert (FILE_TYPE, _OLD) not in registry.elements
    # Another type's entry of the same name stays.
    assert registry.elements[(AI_PACKAGE_TYPE, _OLD)] == before[(AI_PACKAGE_TYPE, _OLD)]
    assert registry.id_counters == counters


@pytest.mark.parametrize(
    ("type_name", "old", "new"),
    [
        (FILE_TYPE, "missing.py", _NEW),
        (FILE_TYPE, _OLD, _OLD),
        (FILE_TYPE, _OLD, "taken.py"),
        (FILE_TYPE, _OLD, "bad\udcff.py"),
        ("software_Package", _OLD, _NEW),
    ],
    ids=["no-old-key", "same-key", "new-key-held", "unencodable", "other-type"],
)
def test_promote_alias_refuses_and_changes_nothing(
    type_name: str, old: str, new: str
) -> None:
    registry = _held()
    registry.register(FILE_TYPE, "taken.py")
    before, counters = entries_of(registry), dict(registry.id_counters)

    assert registry.promote_alias(type_name, old, new) is False

    assert entries_of(registry) == before
    assert registry.id_counters == counters


def test_promote_alias_takes_either_normalisation_form() -> None:
    registry = make_registry(
        {(FILE_TYPE, "café/x.py"): ("https://spdx.org/spdxdocs/test-1#File-1", None)}
    )

    assert registry.promote_alias(FILE_TYPE, "café/x.py", "src/café/x.py")

    assert list(registry.elements) == [(FILE_TYPE, "src/café/x.py")]


def test_a_promotion_is_a_change_a_save_replays(tmp_path: Path) -> None:
    """The moved key is saved, the id is not added again, and a rebase onto
    an untouched file keeps it."""
    path = tmp_path / "ids.json"
    registry = make_registry(
        {(FILE_TYPE, _OLD): ("https://spdx.org/spdxdocs/test-1#File-1", _HASH)},
        path=path,
    )
    registry = IdRegistry.load(path)
    assert registry.promote_alias(FILE_TYPE, _OLD, _NEW)

    rebase = registry.rebase()
    registry.save()

    assert rebase.added == 0 and rebase.refused == 0 and rebase.pending
    assert list(IdRegistry.load(path).elements) == [(FILE_TYPE, _NEW)]
