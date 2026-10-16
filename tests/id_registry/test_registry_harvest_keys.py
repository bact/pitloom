# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Harvest by recorded key: the key a run's lookup recorded wins over the
element's name, a recorded key promotes a held one, an unrecorded element
never re-keys a held id of its type (R-keep), ambiguity counts written keys,
and every skip still reserves the id.

See also: test_registry_harvest.py (I1, I4, R-keep at element level),
test_registry_harvest_content_gate.py (the content gate),
_registry_harvest_shared.py (shared helpers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.assemble._generators_shared import _sync_registry
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    IdRegistrySession,
    save_registry,
)
from pitloom.id_registry._ambiguous import _ambiguous_keys
from tests._license_graph import fragment_graph, write_fragment
from tests.id_registry._registry_harvest_shared import (
    _CI,
    _NS,
    _SHA_A,
    _SHA_B,
    _file,
    _object_set,
)
from tests.registry_helpers import entries_of, make_registry

_M = f"{_NS}#File-1"


def test_promotion_keeps_the_id_and_adds_none(tmp_path: Path) -> None:
    """``demo/x.py`` -> ``src/demo/x.py``: one key left, same id, no
    counter moved, nothing counted as added."""
    path = tmp_path / "ids.json"
    make_registry({(FILE_TYPE, "demo/x.py"): (_M, _SHA_A)}, namespace=_NS, path=path)
    registry = IdRegistry.load(path)
    counters = dict(registry.id_counters)
    keys = {_M: (FILE_TYPE, "src/demo/x.py")}

    result = registry.harvest(_object_set(_file("demo/x.py", _M, _SHA_A)), keys)

    assert result == (0, True)
    assert entries_of(registry) == {(FILE_TYPE, "src/demo/x.py"): (_M, _SHA_A)}
    assert registry.id_counters == counters
    assert save_registry(registry).added == 0
    assert entries_of(IdRegistry.load(path)) == entries_of(registry)


@pytest.mark.parametrize(
    "keys",
    [
        None,
        {},
        {_M: (AI_PACKAGE_TYPE, "m.bin")},
        {_M: (FILE_TYPE, "")},
        {f"{_NS}#File-2": (FILE_TYPE, "b.py")},
    ],
    ids=["none", "empty", "other-type", "empty-key", "other-id"],
)
def test_no_usable_recorded_key_writes_the_name(
    keys: dict[str, tuple[str, str]] | None,
) -> None:
    registry = IdRegistry.new("proj")

    registry.harvest(_object_set(_file("a.py", _M, _SHA_A)), keys)

    assert entries_of(registry) == {(FILE_TYPE, "a.py"): (_M, _SHA_A)}


@pytest.mark.parametrize(
    ("recorded", "written"),
    [
        (("src/a.py", "lib/a.py"), {"src/a.py", "lib/a.py"}),
        (("k.py", "k.py"), set()),
        (None, set()),
    ],
    ids=["distinct-keys", "equal-keys", "equal-names"],
)
def test_ambiguity_counts_written_keys(
    caplog: pytest.LogCaptureFixture,
    recorded: tuple[str, str] | None,
    written: set[str],
) -> None:
    """Equal names under distinct recorded keys are both harvested; equal
    written keys (recorded or names) skip both, in one DEBUG line."""
    ids = (f"{_NS}#File-1", f"{_NS}#File-2")
    names = ("b.py", "c.py") if recorded == ("k.py", "k.py") else ("a.py", "a.py")
    objects = [_file(n, i, _SHA_A) for n, i in zip(names, ids, strict=True)]
    keys = (
        {i: (FILE_TYPE, k) for i, k in zip(ids, recorded, strict=True)}
        if recorded
        else {}
    )
    registry = IdRegistry.new("proj")
    caplog.set_level(logging.DEBUG, logger="pitloom.id_registry")

    registry.harvest(_object_set(*objects), keys)

    assert {name for _, name in registry.elements} == written
    skipped = [r.getMessage() for r in caplog.records if "not harvested (" in r.message]
    assert len(skipped) == (not written)
    assert _ambiguous_keys(objects, keys) == (
        frozenset() if written else {(FILE_TYPE, (recorded or names)[0])}
    )


@pytest.mark.parametrize(
    ("first", "kept", "want"),
    [
        ("File-1", True, {"src/a.py": "File-1", "other.py": "File-2"}),
        ("File-3", False, {"other.py": "File-1"}),
    ],
    ids=["r-kept", "held-key-rewritten"],
)
def test_an_element_r_keep_skips_never_blocks_a_recorded_key(
    first: str, kept: bool, want: dict[str, str]
) -> None:
    """A recorded ``src/a.py`` and an unrecorded element named ``src/a.py``
    whose id is held under ``other.py``: R-keep skips the second, so the
    first is written. When the pass itself rewrites ``other.py`` first,
    the second is written too, and the key is ambiguous: neither."""
    recorded, named = f"{_NS}#{first}", f"{_NS}#File-2"
    registry = make_registry({(FILE_TYPE, "other.py"): (named, _SHA_A)}, namespace=_NS)
    # Equal SHA-256: not the stale rule (test_registry_harvest_stale.py).
    objects = [_file("a.py", recorded, _SHA_A), _file("src/a.py", named, _SHA_A)]
    if not kept:  # sorted before both: frees the id of "src/a.py"
        objects.append(_file("other.py", f"{_NS}#File-1", _SHA_A))
    keys = {recorded: (FILE_TYPE, "src/a.py")}

    registry.harvest(_object_set(*objects), keys)

    assert {k[1]: e.spdx_id for k, e in registry.elements.items()} == {
        name: f"{_NS}#{spdx_id}" for name, spdx_id in want.items()
    }


@pytest.mark.parametrize(
    "case", ["ambiguous", "r-keep", "gate-kept", "unencodable-key"]
)
def test_every_skip_reserves_the_id(
    caplog: pytest.LogCaptureFixture, case: str
) -> None:
    """The skipped element's id is never minted next."""
    skipped = f"{_NS}#File-9"
    held = (
        {(FILE_TYPE, "src/a.py"): (skipped if case == "r-keep" else _M, _SHA_A)}
        if case in ("r-keep", "gate-kept")
        else {}
    )
    registry = make_registry(held, namespace=_NS)
    objects = [_file("a.py", skipped, None if case == "gate-kept" else _SHA_B)]
    keys = {skipped: (FILE_TYPE, "src/a.py")}
    if case == "ambiguous":
        objects.append(_file("a.py", f"{_NS}#File-3", _SHA_B))
        keys = {}
    elif case == "r-keep":
        keys = {}
    elif case == "unencodable-key":
        keys = {skipped: (FILE_TYPE, "a\udcff.py")}
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")

    registry.harvest(_object_set(*objects), keys)

    assert entries_of(registry) == {
        key: (spdx_id, sha) for key, (spdx_id, sha) in held.items()
    }
    assert registry.register(FILE_TYPE, "n") == f"{_NS}#File-10"
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
    expected = {
        "gate-kept": [
            "ID registry: content gate kept for software_File 'src/a.py': "
            f"harvested id {skipped} not recorded over {_M}"
        ],
        "unencodable-key": ["ID registry: key 'a\\udcff.py' "],
    }.get(case, [])
    assert len(messages) == len(expected)
    assert all(m.startswith(e) for m, e in zip(messages, expected, strict=True))


@pytest.mark.parametrize("recorded", [True, False], ids=["recorded", "none"])
def test_sync_registry_harvests_by_the_exporter_keys(
    tmp_path: Path, recorded: bool
) -> None:
    registry = make_registry(
        {(FILE_TYPE, "demo/x.py"): (_M, _SHA_A)},
        namespace=_NS,
        path=tmp_path / "ids.json",
    )
    exporter = Spdx3JsonExporter()
    exporter.add_creation_info(_CI)
    exporter.add_file(_file("x.py", _M, _SHA_A))
    if recorded:
        exporter.registry_keys[_M] = (FILE_TYPE, "src/demo/x.py")

    _sync_registry(exporter, registry, True)

    key = "src/demo/x.py" if recorded else "demo/x.py"
    assert entries_of(IdRegistry.load(tmp_path / "ids.json")) == {
        (FILE_TYPE, key): (_M, _SHA_A)
    }


_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "demo"
version = "1.0.0"
[tool.pitloom.fragment]
files = ["loom.spdx3.json"]
"""


@pytest.mark.parametrize("surface", ["project", "id-import"])
def test_merged_loom_model_keeps_its_path_key(tmp_path: Path, surface: str) -> None:
    """K17: a loom fragment's model, named ``sentimentdemo``, keeps the id
    the registry holds under its path key, through a project run's harvest
    and an ``id import`` of the merged SBOM alike."""
    model = f"{_NS}#AIPackage-1"
    path_key = (AI_PACKAGE_TYPE, "models/sentimentdemo.bin")
    registry_path = tmp_path / "loom-id-registry.json"
    make_registry(
        {path_key: (model, _SHA_A)},
        namespace=_NS,
        path=registry_path,
        project_root=tmp_path,
    )
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_bytes(b"")
    element = {
        "type": "ai_AIPackage",
        "spdxId": model,
        "name": "sentimentdemo",
        "verifiedUsing": [{"type": "Hash", "algorithm": "sha256", "hashValue": _SHA_A}],
    }
    write_fragment(tmp_path / "loom.spdx3.json", fragment_graph([element]))

    sbom = generate_project_sbom(
        tmp_path,
        offline=True,
        id_registry=registry_path,
        update_id_registry=surface == "project",
    )
    graph = json.loads(sbom)["@graph"]
    assert any(e.get("spdxId") == model for e in graph)  # non-vacuous: merged
    if surface == "id-import":
        (tmp_path / "sbom.json").write_text(sbom, encoding="utf-8")
        registry = IdRegistry.load(registry_path)
        registry.import_sbom(tmp_path / "sbom.json")
        registry.save()

    held = {
        key: value
        for key, value in entries_of(IdRegistry.load(registry_path)).items()
        if key[0] == AI_PACKAGE_TYPE
    }
    assert held == {path_key: (model, _SHA_A)}


def test_recorded_key_written_for_an_element_of_any_name() -> None:
    """The recorded key is written even when the element's own name is
    held by another id: that key is left alone."""
    registry = make_registry(
        {(FILE_TYPE, "a.py"): (f"{_NS}#File-5", _SHA_B)}, namespace=_NS
    )

    registry.harvest(
        _object_set(_file("a.py", _M, _SHA_A)), {_M: (FILE_TYPE, "src/a.py")}
    )

    assert entries_of(registry) == {
        (FILE_TYPE, "a.py"): (f"{_NS}#File-5", _SHA_B),
        (FILE_TYPE, "src/a.py"): (_M, _SHA_A),
    }


@pytest.mark.parametrize("deployed", [False, True], ids=["build", "deployed"])
def test_build_copies_the_session_keys_into_the_exporter(deployed: bool) -> None:
    recorded = {_M: (FILE_TYPE, "src/a.py")}
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0.0"),
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    registry = IdRegistry.new("demo")

    with patch.object(
        IdRegistrySession, "recorded_keys", autospec=True, return_value=recorded
    ):
        exporter = (
            build_deployed(doc, [], registry=registry)
            if deployed
            else build(doc, registry=registry)
        )

    assert exporter.registry_keys == recorded
