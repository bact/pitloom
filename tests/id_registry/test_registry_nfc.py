# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Registry keys are NFC for every type: lookup, registration and the
file hit one entry whichever form a name is spelt in.

See also: test_registry_generate_promote.py (indexing files whose keys
clash), test_registry_format_load.py (other load failures).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)
from tests.id_registry.shared import REGISTRY_NS as _NS

_NFD = "café"
_NFC = "café"
_TYPES = [FILE_TYPE, PACKAGE_TYPE, AI_PACKAGE_TYPE]
_ID_SUFFIX = {FILE_TYPE: "File", PACKAGE_TYPE: "Package", AI_PACKAGE_TYPE: "AIPackage"}


def _write(path: Path, type_name: str, *names: str) -> None:
    """A registry file holding *names* under *type_name*, each with its own
    id, as written (no normalisation)."""
    records = {
        name: {"spdxId": f"{_NS}#{_ID_SUFFIX[type_name]}-{n}"}
        for n, name in enumerate(names, 1)
    }
    data = {
        "elements": {type_name: records},
        "id_counters": {_ID_SUFFIX[type_name]: len(names)},
        "namespace": _NS,
        "project_root": ".",
        "version": 3,
    }
    path.write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))


@pytest.mark.parametrize("type_name", _TYPES, ids=["file", "package", "model"])
@pytest.mark.parametrize(
    ("written", "asked"),
    [(_NFD, _NFC), (_NFC, _NFD)],
    ids=["nfd-file-nfc-ask", "nfc-file-nfd-ask"],
)
def test_lookup_hits_the_other_normalisation_form(
    tmp_path: Path, type_name: str, written: str, asked: str
) -> None:
    """A key written in either form is found by the other, by every
    entry point, and never minted again."""
    path = tmp_path / "ids.json"
    _write(path, type_name, written)
    registry = IdRegistry.load(path)
    spdx_id = f"{_NS}#{_ID_SUFFIX[type_name]}-1"
    counters = dict(registry.id_counters)

    assert asked != written  # not vacuous
    assert registry.get(type_name, asked) is not None
    assert registry.lookup(type_name, [asked]) == spdx_id
    assert registry.has_name(asked)
    assert registry.register(type_name, asked) == spdx_id
    assert len(registry.elements) == 1
    assert registry.id_counters == counters


@pytest.mark.parametrize("type_name", _TYPES, ids=["file", "package", "model"])
def test_a_file_with_two_spellings_of_one_key_is_rejected(
    tmp_path: Path, type_name: str
) -> None:
    path = tmp_path / "ids.json"
    _write(path, type_name, _NFC, _NFD)

    with pytest.raises(ValueError, match="ID registry file") as excinfo:
        IdRegistry.load(path)

    assert "two" in str(excinfo.value)


def test_a_key_written_in_nfd_loads_and_saves_as_nfc(tmp_path: Path) -> None:
    path = tmp_path / "ids.json"
    _write(path, FILE_TYPE, f"data/{_NFD}.txt")

    registry = IdRegistry.load(path)
    registry.save()

    assert list(registry.elements) == [(FILE_TYPE, f"data/{_NFC}.txt")]
    saved = json.loads(path.read_bytes())
    assert list(saved["elements"][FILE_TYPE]) == [f"data/{_NFC}.txt"]


def test_nfc_is_applied_after_the_package_name_canonicalisation() -> None:
    """The package form is still PEP 503, and nothing is case-folded."""
    registry = IdRegistry.new("p")
    first = registry.register(PACKAGE_TYPE, f"My_{_NFD}")

    assert registry.register(PACKAGE_TYPE, f"my-{_NFC}") == first
    assert registry.register(FILE_TYPE, "Data.TXT") != registry.register(
        FILE_TYPE, "data.txt"
    )
