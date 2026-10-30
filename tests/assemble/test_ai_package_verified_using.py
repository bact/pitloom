# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A scanned or named model's ``ai_AIPackage`` carries its file's SHA-256
(``verifiedUsing``), and every model registry lookup is gated by it: other
bytes at the same path get a new id on each surface.

See also: :mod:`tests.id_registry.test_lookup_table` (the gate per surface),
:mod:`tests.id_registry.test_typed_ids_round_trip` (an ``id generate``
entry hit by unchanged bytes) and
:mod:`tests.core.generator.test_generator_registry_harvestable` (what is
harvested).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import errno
import hashlib
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import (
    enrich_model,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3.document import build
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.hashes import sha256_of
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import MESSAGES
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.registry_helpers import make_registry

_MODEL = "m.safetensors"
_OLD, _NEW = safetensors_bytes(), safetensors_bytes(extra=1)
_GATE_INFO = "no registry entry records its SHA-256; a new id is used"
_PIN = "https://spdx.org/spdxdocs/pins#AIPackage-1"
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n'
)
_README = "---\nlicense: mit\ndatasets:\n  - squad\n---\n# M\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _graph(sbom: str) -> list[dict[str, Any]]:
    return list(json.loads(sbom)["@graph"])


def _package(sbom: str) -> dict[str, Any]:
    (package,) = [e for e in _graph(sbom) if e["type"] == "ai_AIPackage"]
    return package


def _package_sha(sbom: str) -> str | None:
    hashes = _package(sbom).get("verifiedUsing", [])
    return next((h["hashValue"] for h in hashes if h["algorithm"] == "sha256"), None)


def _file_sha(sbom: str) -> str:
    (node,) = [e for e in _graph(sbom) if e.get("name") == f"demo/{_MODEL}"]
    return str(node["verifiedUsing"][0]["hashValue"])


def _registry(tmp: Path) -> Path | None:
    """``tmp/ids.json`` when the test wrote one, else no registry."""
    path = tmp / "ids.json"
    return path if path.is_file() else None


def _project(tmp: Path, data: bytes) -> str:
    root = tmp / "proj"
    (root / "demo").mkdir(parents=True, exist_ok=True)
    (root / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "demo" / _MODEL).write_bytes(data)
    (root / "pyproject.toml").write_bytes(_PYPROJECT.encode())
    return generate_project_sbom(
        root, creation_metadata=None, id_registry=_registry(tmp), offline=True
    )


def _wheel(tmp: Path, data: bytes) -> str:
    wheel = write_model_wheel(tmp / "dist", {f"demo/{_MODEL}": data})
    return generate_wheel_sbom(wheel, id_registry=_registry(tmp), offline=True)


def _model_file(tmp: Path, data: bytes) -> Path:
    path = tmp / "hub" / _MODEL
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    (path.parent / "README.md").write_bytes(_README.encode())
    return path


def _model(tmp: Path, data: bytes) -> str:
    return generate_model_sbom(_model_file(tmp, data), id_registry=_registry(tmp))


def _enrich(tmp: Path, data: bytes) -> str:
    return enrich_model(_model_file(tmp, data), id_registry=_registry(tmp))


def _model_id(sbom: str) -> str:
    """The model's id: its package's, or what a fragment's relationships
    start from (it names the package without defining it)."""
    if any(e["type"] == "ai_AIPackage" for e in _graph(sbom)):
        return str(_package(sbom)["spdxId"])
    (origin,) = {e["from"] for e in _graph(sbom) if e["type"] == "Relationship"}
    return str(origin)


_ROUTES: dict[str, Callable[[Path, bytes], str]] = {
    "project": _project,
    "wheel": _wheel,
    "model": _model,
    "enrich": _enrich,
}
#: The model's registry key on each route: its file's path from the root
#: (``tmp``, the registry's directory).
_KEYS = {
    "project": f"proj/demo/{_MODEL}",
    "wheel": f"demo/{_MODEL}",
    "model": f"hub/{_MODEL}",
    "enrich": f"hub/{_MODEL}",
}


@pytest.mark.parametrize("route", ["project", "wheel", "model"])
def test_the_package_carries_its_model_files_sha256(route: str, tmp_path: Path) -> None:
    sbom = _ROUTES[route](tmp_path, _OLD)
    assert _package_sha(sbom) == _sha(_OLD)
    if route != "model":  # the same hash as the model's own software_File
        assert _file_sha(sbom) == _sha(_OLD)


@pytest.mark.parametrize("route", list(_ROUTES))
@pytest.mark.parametrize(
    ("pinned", "data", "hit"),
    [(_sha(_OLD), _OLD, True), (_sha(_OLD), _NEW, False), (None, _OLD, False)],
    ids=["same-bytes", "retrained", "pin-without-hash"],
)
def test_the_model_lookup_is_gated_by_its_bytes(
    route: str,
    pinned: str | None,
    data: bytes,
    hit: bool,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An entry under the model's key hits only the bytes it records; a
    miss is a new id and one ``INFO:``."""
    make_registry(
        {(AI_PACKAGE_TYPE, _KEYS[route]): (_PIN, pinned)}, path=tmp_path / "ids.json"
    )
    with caplog.at_level(logging.INFO):
        sbom = _ROUTES[route](tmp_path, data)
    assert (_model_id(sbom) == _PIN) is hit
    infos = [r for r in caplog.records if _GATE_INFO in r.getMessage()]
    assert len(infos) == (0 if hit else 1)
    assert all(r.levelno == logging.INFO for r in infos)


@pytest.mark.parametrize("route", ["project", "wheel"])
def test_a_hashed_model_is_harvested_once(route: str, tmp_path: Path) -> None:
    """The first run writes the model's entry with its SHA-256; a second run
    hits it and leaves the registry's bytes as they were."""
    registry = tmp_path / "ids.json"
    IdRegistry.new("demo").save(registry)
    first = _ROUTES[route](tmp_path, _OLD)
    entry = IdRegistry.load(registry).get(AI_PACKAGE_TYPE, _KEYS[route])
    assert entry is not None
    assert (entry.spdx_id, entry.sha256) == (_model_id(first), _sha(_OLD))
    saved = registry.read_bytes()

    second = _ROUTES[route](tmp_path, _OLD)

    assert _model_id(second) == entry.spdx_id
    assert registry.read_bytes() == saved


def _doc(files: list[ProjectFile]) -> DocumentModel:
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name=_MODEL,
            file_path_relative=f"demo/{_MODEL}",
            model_format=AiModelFormat.SAFETENSORS,
        )
    )
    project = ProjectMetadata(name="demo", version="1.0.0", files=files)
    return DocumentModel(project=project, ai_models=[model])


@pytest.mark.parametrize("listed", [True, False], ids=["listed", "not-listed"])
def test_only_a_model_listed_among_the_files_is_hashed_and_gated(
    listed: bool,
) -> None:
    files = [ProjectFile(_MODEL, f"demo/{_MODEL}", digest_sha256=_sha(_OLD))]
    registry = make_registry()
    with patch.object(IdRegistry, "lookup", autospec=True, return_value=None) as spy:
        exporter = build(_doc(files if listed else []), registry=registry)
    objects = exporter.object_set.objects
    (package,) = [o for o in objects if isinstance(o, spdx3.ai_AIPackage)]
    gates = [
        call.kwargs["sha256"]
        for call in spy.call_args_list
        if call.args[1] == AI_PACKAGE_TYPE
    ]
    assert gates == [_sha(_OLD) if listed else None]
    if not listed:
        assert not package.verifiedUsing
        return
    assert sha256_of(package) == _sha(_OLD)
    (file,) = [
        o
        for o in objects
        if isinstance(o, spdx3.software_File) and o.name == f"demo/{_MODEL}"
    ]
    # Equal values, never one shared Hash object.
    assert package.verifiedUsing[0] is not file.verifiedUsing[0]


@pytest.mark.parametrize(
    "error",
    [
        PermissionError(errno.EACCES, "Permission denied"),
        FileNotFoundError(errno.ENOENT, "No such file"),
    ],
    ids=["refused", "gone-since-read"],
)
@pytest.mark.parametrize("route", ["model", "enrich"])
def test_an_unreadable_model_file_is_neither_hashed_nor_gated(
    route: str, error: OSError, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A model file refused at the hash: ``file-unreadable``, no hash, the
    lookup ungated; one gone since it was read is absent: the same, quietly."""
    make_registry(
        {(AI_PACKAGE_TYPE, _KEYS[route]): (_PIN, None)}, path=tmp_path / "ids.json"
    )
    # The SBOM route reads both digests at once, the gate-only route SHA-256.
    reader = "file_digests" if route == "model" else "sha256_digest"
    with patch(
        f"pitloom.assemble._model_generator.{reader}",
        autospec=True,
        side_effect=error,
    ):
        sbom = _ROUTES[route](tmp_path, _OLD)
    assert _model_id(sbom) == _PIN  # ungated: the hash-less entry hits
    if route == "model":
        assert _package_sha(sbom) is None
    # What follows (no verifiedUsing, the lookup not gated) is the entry's.
    unread = [r for r in caplog.records if "for the model hash" in r.getMessage()]
    if isinstance(error, FileNotFoundError):
        assert not unread
        return
    (warning,) = unread
    assert warning.levelno == logging.WARNING
    assert warning.getMessage().endswith(
        "could not read for the model hash; Permission denied"
    )
    assert getattr(warning, CODE_ATTR) == "file-unreadable"
    assert "verifiedUsing" in MESSAGES["file-unreadable"].did


def test_enrich_without_a_registry_hashes_nothing(tmp_path: Path) -> None:
    """The fragment has no package to verify: the hash only gates a lookup."""
    with (
        patch(
            "pitloom.assemble._model_generator.sha256_digest", autospec=True
        ) as digest,
        patch(
            "pitloom.assemble._model_generator.file_digests", autospec=True
        ) as digests,
    ):
        enrich_model(_model_file(tmp_path, _OLD))
    digest.assert_not_called()
    digests.assert_not_called()
