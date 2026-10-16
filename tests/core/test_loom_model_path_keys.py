# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the registry key of a loom model (:mod:`pitloom._loom_model`): a
``path=`` below the registry root keys the model by that path, so its declared
name does not matter; no usable path, or one outside the root, keys by name.

See also: tests/core/test_loom_model.py (the lookup and the save),
tests/id_registry/test_keys.py (the key shape).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.core.config import PitloomConfig
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    IdRegistrySession,
    keys,
)
from tests.registry_helpers import Entries, entries_of, make_registry

_NS = "https://spdx.org/spdxdocs/test-1"
_V1, _V2 = b"weights v1", b"weights v2"


@pytest.fixture(name="project")
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An entered project: ``m.bin``, ``sub/``, ``a/model.npy`` and
    ``b/model.npy`` (other bytes); the calling script is not captured."""
    root = tmp_path / "proj"
    for folder in ("sub", "a", "b"):
        (root / folder).mkdir(parents=True)
    (root / "m.bin").write_bytes(_V1)
    (root / "a" / "model.npy").write_bytes(_V1)
    (root / "b" / "model.npy").write_bytes(_V2)
    monkeypatch.chdir(root)
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: None
    )
    return root


def _registry(root: Path, entries: Entries | None = None) -> Path:
    path = root / "reg.json"
    make_registry(entries, path=path)
    return path


def _model_ids(output: Path) -> list[str]:
    graph = json.loads(output.read_text(encoding="utf-8"))["@graph"]
    return [e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"]


def _declare(project: Path, registry: Path, name: str, **kwargs: Any) -> str:
    """One run declaring one model; its id."""
    out = project / f"out-{len(list(project.glob('out-*.json')))}.json"
    with loom.run(out, id_registry=registry):
        loom.set_model(name, **kwargs)
    (spdx_id,) = _model_ids(out)
    return spdx_id


def _keys(registry: Path) -> set[str]:
    return {
        key
        for type_name, key in IdRegistry.load(registry).elements
        if type_name == AI_PACKAGE_TYPE
    }


def test_one_file_under_two_names_is_one_id(project: Path) -> None:
    """The element keeps the declared name; the registry holds one entry,
    keyed by the path (declared names alone made two entities)."""
    registry = _registry(project)
    first = _declare(project, registry, "resnet", path="m.bin")
    second = _declare(project, registry, "resnet-final", path="m.bin")

    assert first == second
    assert _keys(registry) == {"m.bin"}
    graph = json.loads((project / "out-1.json").read_text(encoding="utf-8"))["@graph"]
    (model,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert model["name"] == "resnet-final"


def test_a_shared_stem_in_two_folders_is_two_ids(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Same declared name, ``a/model.npy`` and ``b/model.npy``: two entries,
    no collision, stable on a second run that writes nothing."""
    registry = _registry(project)
    out = project / "out.json"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(out, id_registry=registry):
            loom.set_model("model", path="a/model.npy")
            loom.use_model("model", path="b/model.npy")
        saved = registry.read_bytes()
        with loom.run(project / "again.json", id_registry=registry):
            loom.set_model("model", path="a/model.npy")
            loom.use_model("model", path="b/model.npy")

    ids = _model_ids(out)
    assert len(set(ids)) == 2
    assert _model_ids(project / "again.json") == ids
    assert registry.read_bytes() == saved
    assert _keys(registry) == {"a/model.npy", "b/model.npy"}
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_a_spelling_of_the_path_is_one_key(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``./m.bin``, ``sub/../m.bin``, the absolute path and a case variant
    (a hard link the listing hides) all key as ``m.bin``."""
    other = project / "M.BIN"
    try:
        os.link(project / "m.bin", other)
    except FileExistsError:  # case-insensitive: already the same file
        pass
    except OSError:
        pytest.skip("hard links unavailable on this file system")
    real = os.listdir
    monkeypatch.setattr(
        keys, "_listdir", lambda d: [n for n in real(d) if n != "M.BIN"]
    )
    registry = _registry(project)
    ids = {
        _declare(project, registry, "m", path=given)
        for given in ("m.bin", "./m.bin", "sub/../m.bin", project / "m.bin", other)
    }

    assert len(ids) == 1
    assert _keys(registry) == {"m.bin"}


def test_retrained_bytes_at_the_same_path_are_a_new_id(
    project: Path, caplog: pytest.LogCaptureFixture
) -> None:
    registry = _registry(project)
    first = _declare(project, registry, "m", path="m.bin")
    (project / "m.bin").write_bytes(_V2)
    with caplog.at_level(logging.INFO, logger="pitloom"):
        second = _declare(project, registry, "m", path="m.bin")

    assert first != second
    assert _keys(registry) == {"m.bin"}
    assert any("content changed" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("case", ["no-path", "missing", "outside"])
def test_no_usable_path_is_keyed_by_name(
    project: Path, tmp_path: Path, case: str
) -> None:
    """No ``path=``, a missing file (both ungated), or a file outside the
    root (hashed, so gated): the name is the key, as before path keys."""
    outside = tmp_path / "elsewhere.bin"
    outside.write_bytes(_V1)
    path = {"no-path": None, "missing": "gone.bin", "outside": outside}[case]
    registry = _registry(
        project, {(AI_PACKAGE_TYPE, "m"): (f"{_NS}#AIPackage-7", None)}
    )

    spdx_id = _declare(project, registry, "m", path=path)

    assert (spdx_id == f"{_NS}#AIPackage-7") is (case != "outside")
    assert _keys(registry) == {"m"}


@pytest.mark.parametrize(
    ("entries", "needle"),
    [
        ({}, "'m.bin' not found in registry"),
        ({(FILE_TYPE, "m.bin"): (f"{_NS}#File-1", "0" * 64)}, "untracked entity"),
        ({(AI_PACKAGE_TYPE, "m.bin"): (f"{_NS}#AIPackage-1", "0" * 64)}, "changed"),
    ],
    ids=["absent", "file-same-key", "retrained"],
)
def test_path_key_miss_warning_never_claims_another_type(
    project: Path,
    caplog: pytest.LogCaptureFixture,
    entries: Entries,
    needle: str,
) -> None:
    """With ``update-id-registry = false`` a miss warns once. A model's own
    ``software_File`` shares its path key, so "different type" would be
    noise: only untracked or content changed."""
    registry = _registry(project, entries)
    out = project / "out.json"
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        with loom.run(
            out,
            id_registry=registry,
            pitloom_config=PitloomConfig(update_id_registry=False),
        ):
            loom.set_model("m", path="m.bin")

    (warning,) = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert needle in warning
    assert "different type" not in warning
    assert entries_of(IdRegistry.load(registry)) == dict(entries)


def test_a_rejected_claim_on_register_mints_and_records_no_key(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``register_id`` returning ``None`` (its claim rejected): the model
    gets a minted id and no key is recorded for it."""
    monkeypatch.setattr(
        IdRegistrySession,
        "register_id",
        lambda *_args, **_kwargs: None,
    )
    registry = _registry(project)
    spdx_id = _declare(project, registry, "m", path="m.bin")

    assert not spdx_id.startswith(_NS)
    assert _keys(registry) == set()
