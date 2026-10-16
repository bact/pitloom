# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A run's auto-harvest of an element with no recorded key (a merged loom
fragment's): never a stale SHA-256 over a gated entry, and a hashed model
only under its own file's key.

See also: test_registry_harvest_content_gate.py (an unhashed element over
a gated entry), test_surfaces_stale_fragments.py (the loom runs end to
end), _registry_harvest_shared.py (helpers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

import pitloom.id_registry._harvest as ids_mod
from pitloom.id_registry import AI_PACKAGE_TYPE, FILE_TYPE
from tests.id_registry._registry_harvest_shared import (
    _NS,
    _SHA_A,
    _SHA_B,
    _element,
    _file,
)
from tests.registry_helpers import entries_of, make_registry

_SHA_C = "c" * 64
_OLD, _NEW = f"{_NS}#File-1", f"{_NS}#File-2"


def _model(name: str, spdx_id: str, sha256: str | None) -> spdx3.ai_AIPackage:
    return _element(spdx3.ai_AIPackage, name, spdx_id, sha256)


def _gate_infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.INFO and r.getMessage().startswith("ID registry: ")
    ]


def _stale(key: str, spdx_id: str, held: str, type_name: str = FILE_TYPE) -> str:
    return (
        f"ID registry: content gate kept for {type_name} {key!r}: element id "
        f"{spdx_id} with an older SHA-256 not recorded over {held}"
    )


@pytest.mark.parametrize(
    ("element_id", "sha", "recorded", "imported", "want", "info"),
    [
        (_OLD, _SHA_A, False, False, (_NEW, _SHA_B), _stale("d.txt", _OLD, _NEW)),
        (_NEW, _SHA_A, False, False, (_NEW, _SHA_B), _stale("d.txt", _NEW, _NEW)),
        (_OLD, _SHA_B, False, False, (_OLD, _SHA_B), None),
        (_OLD, _SHA_A, True, False, (_OLD, _SHA_A), None),
        (_OLD, _SHA_A, False, True, (_OLD, _SHA_A), None),
    ],
    ids=["stale", "stale-same-id", "same-sha", "recorded", "import"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_unrecorded_stale_sha_never_replaces_a_gated_entry(
    caplog: pytest.LogCaptureFixture,
    element_id: str,
    sha: str,
    recorded: bool,
    imported: bool,
    want: tuple[str, str],
    info: str | None,
) -> None:
    """A merged fragment's file (no recorded key) with another SHA-256 than
    the entry keeps the entry, one INFO; this run's own lookup (recorded:
    a retrain) and ``id import`` replace it."""
    registry = make_registry({(FILE_TYPE, "d.txt"): (_NEW, _SHA_B)}, namespace=_NS)
    keys = {element_id: (FILE_TYPE, "d.txt")} if recorded else None
    caplog.set_level(logging.DEBUG, logger="pitloom.id_registry")

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(
        registry, [_file("d.txt", element_id, sha)], imported=imported, keys=keys
    )

    assert entries_of(registry) == {(FILE_TYPE, "d.txt"): want}
    assert _gate_infos(caplog) == ([info] if info else [])
    # The id is reserved, written or skipped.
    assert registry.id_counters["File"] == int(element_id.rpartition("-")[2])


@pytest.mark.parametrize("order", ["recorded-first", "stale-first"])
def test_stale_element_yields_to_this_runs_recorded_key(
    caplog: pytest.LogCaptureFixture, order: str
) -> None:
    """The project's file (recorded, new bytes) and a fragment's file of
    the same path (old bytes) in one document: not ambiguous; the
    recorded one is written, whichever id sorts first."""
    first, second = (_OLD, _NEW) if order == "recorded-first" else (_NEW, _OLD)
    registry = make_registry({(FILE_TYPE, "d.txt"): (second, _SHA_A)})
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")
    objects = sorted(
        [_file("d.txt", first, _SHA_B), _file("d.txt", second, _SHA_A)],
        key=lambda o: str(o.spdxId),
    )

    # pylint: disable-next=protected-access
    skipped = ids_mod._harvest_elements(
        registry, objects, imported=False, keys={first: (FILE_TYPE, "d.txt")}
    )

    assert not skipped
    assert entries_of(registry) == {(FILE_TYPE, "d.txt"): (first, _SHA_B)}
    assert _gate_infos(caplog) == [_stale("d.txt", second, first)]


_NO_FILE = "ID registry: model m not recorded: no unique file with its SHA-256"


@pytest.mark.parametrize(
    ("files", "recorded", "want", "info"),
    [
        ((("f/m.bin", _SHA_A),), None, "f/m.bin", None),
        ((), None, None, _NO_FILE),
        ((("f/m.bin", _SHA_B),), None, None, _NO_FILE),
        ((("f/a.bin", _SHA_A), ("f/b.bin", _SHA_A)), None, None, _NO_FILE),
        ((), "f/m.bin", "f/m.bin", None),
    ],
    ids=["file", "no-file", "other-sha", "twin-files", "recorded"],
)
def test_unrecorded_model_is_harvested_under_its_files_key_only(
    caplog: pytest.LogCaptureFixture,
    files: tuple[tuple[str, str], ...],
    recorded: str | None,
    want: str | None,
    info: str | None,
) -> None:
    """A hashed model with no recorded key (a fragment's ``set_model``) is
    written under the key of the one file of the document holding its
    SHA-256; with none, it is not harvested (one INFO; its id still
    reserved), never under its name."""
    spdx_id = f"{_NS}#AIPackage-7"
    objects: list[Any] = [
        _file(name, f"{_NS}#File-{n}", sha) for n, (name, sha) in enumerate(files, 1)
    ]
    objects.append(_model("m", spdx_id, _SHA_A))
    keys = {spdx_id: (AI_PACKAGE_TYPE, recorded)} if recorded else None
    registry = make_registry(namespace=_NS)
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, objects, imported=False, keys=keys)

    held = {k[1]: e.spdx_id for k, e in registry.elements.items()}
    models = {k[1] for k in registry.elements if k[0] == AI_PACKAGE_TYPE}
    assert models == ({want} if want else set())
    assert want is None or held[want] == spdx_id
    assert _gate_infos(caplog) == ([info] if info else [])
    assert registry.id_counters["AIPackage"] == 7


def test_unhashed_model_keeps_its_name_key() -> None:
    """Only a hashed model needs a file: an unhashed one (no gate) is
    written under its name, as before."""
    registry = make_registry(namespace=_NS)
    model = _model("m", f"{_NS}#AIPackage-1", None)

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, [model], imported=False)

    assert entries_of(registry) == {
        (AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-1", None)
    }


def test_fragment_model_over_a_retrained_entry_is_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A fragment's model and file of the old bytes, the entry the retrained
    ones: the model takes its file's key, then the stale rule keeps the
    entry for both."""
    held = {
        (FILE_TYPE, "f/m.bin"): (f"{_NS}#File-9", _SHA_C),
        (AI_PACKAGE_TYPE, "f/m.bin"): (f"{_NS}#AIPackage-9", _SHA_C),
    }
    registry = make_registry(held)
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")
    objects = [
        _file("f/m.bin", f"{_NS}#File-1", _SHA_A),
        _model("m", f"{_NS}#AIPackage-1", _SHA_A),
    ]

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, objects, imported=False)

    assert entries_of(registry) == held
    assert _gate_infos(caplog) == [
        _stale("f/m.bin", f"{_NS}#File-1", f"{_NS}#File-9"),
        _stale("f/m.bin", f"{_NS}#AIPackage-1", f"{_NS}#AIPackage-9", AI_PACKAGE_TYPE),
    ]


def test_fragment_model_never_unrecords_the_runs_own_file() -> None:
    """The run's own file (recorded, new bytes) and a fragment model of
    those bytes: the model takes the file's key and the file, still the
    run's lookup, replaces the older entry."""
    registry = make_registry(
        {(FILE_TYPE, "f/m.bin"): (f"{_NS}#File-9", _SHA_C)}, namespace=_NS
    )
    objects = [
        _file("f/m.bin", f"{_NS}#File-1", _SHA_A),
        _model("m", f"{_NS}#AIPackage-1", _SHA_A),
    ]
    keys = {f"{_NS}#File-1": (FILE_TYPE, "f/m.bin")}

    # pylint: disable-next=protected-access
    ids_mod._harvest_elements(registry, objects, imported=False, keys=keys)

    assert entries_of(registry) == {
        (AI_PACKAGE_TYPE, "f/m.bin"): (f"{_NS}#AIPackage-1", _SHA_A),
        (FILE_TYPE, "f/m.bin"): (f"{_NS}#File-1", _SHA_A),
    }
