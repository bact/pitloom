# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A lookup miss never mints an id the registry holds for another key in
the document's namespace: every held id of a looked-up type is reserved,
claimed or not; an agent's or a model card dataset's own held id is not,
so it never renumbers.

See also: test_generator_registry_sync_claim.py (claimed ids),
tests/id_registry/test_surfaces_in_tree_registry.py (monorepo surfaces),
tests/id_registry/test_surfaces_model_held_ids.py (``loom model``/``enrich``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import (
    _ai_model_identity,
    build,
    build_deployed,
    build_model,
)
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from tests.id_registry.surfaces_base import _run_cli

_CREATED = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")
_Build = Callable[[IdRegistry | None], Spdx3JsonExporter]


def _model_meta(file_path: str | None = None) -> AiModelMetadata:
    return AiModelMetadata(
        format_info=AiModelFormatInfo(
            file_name="m.npy",
            file_path_relative=file_path,
            model_format=AiModelFormat.NUMPY,
        ),
        datasets=[DatasetReference("trainedOn", DatasetMetadata(name="imdb"))],
    )


def _model(registry: IdRegistry | None) -> Spdx3JsonExporter:
    return build_model(_model_meta(), _CREATED, registry=registry)


def _project(registry: IdRegistry | None) -> Spdx3JsonExporter:
    files = [
        ProjectFile(
            physical_path=f"demo/{name}",
            distribution_path=f"demo/{name}",
            digest_sha256=hashlib.sha256(name.encode()).hexdigest(),
        )
        for name in ("a.py", "m.npy")
    ]
    model = _model_meta("demo/m.npy")
    project = ProjectMetadata(
        name="demo", version="1.0.0", dependencies=["dep"], files=files
    )
    doc = DocumentModel(project=project, creation_metadata=_CREATED, ai_models=[model])
    return build(doc, registry=registry, offline=True)


def _deployed(registry: IdRegistry | None) -> Spdx3JsonExporter:
    tree = [{"package": {"key": "a", "package_name": "a", "installed_version": "1"}}]
    project = ProjectMetadata(name="env", version="1")
    doc = DocumentModel(project=project, creation_metadata=_CREATED)
    return build_deployed(doc, tree, registry=registry, offline=True)


def _ids(exporter: Spdx3JsonExporter) -> dict[str, set[str]]:
    """Each element type -> the ids of its elements."""
    found: dict[str, set[str]] = {}
    for obj in exporter.object_set.objects:
        if isinstance(obj, spdx3.Element):
            found.setdefault(str(obj.get_compact_type()), set()).add(str(obj.spdxId))
    return found


_ALL = ("ai_AIPackage", "dataset_DatasetPackage", "software_File", "software_Package")
_MODEL = ("ai_AIPackage", "dataset_DatasetPackage")


@pytest.mark.parametrize(
    ("build_one", "looked_up"),
    [(_project, _ALL), (_deployed, ("software_Package",)), (_model, _MODEL)],
    ids=["project", "env", "model"],
)
def test_a_miss_never_mints_an_id_the_registry_holds(
    build_one: _Build, looked_up: tuple[str, ...]
) -> None:
    """A registry holding each first-run id of a looked-up type under a
    key no element looks up (``foreign/<n>``): the next run of the same
    document (one namespace) mints none of them; agents and tools keep
    their own ids; the run is deterministic."""
    first = _ids(build_one(None))
    assert all(first.get(t) for t in looked_up)
    registry = IdRegistry.new("demo")
    for type_name in looked_up:
        for n, spdx_id in enumerate(sorted(first[type_name])):
            registry.elements[(type_name, f"foreign/{n}")] = RegistryEntry(spdx_id)

    second, again = _ids(build_one(registry)), _ids(build_one(registry))

    assert second == again
    for type_name in looked_up:
        assert not second[type_name] & first[type_name]
    for type_name in ("SoftwareAgent", "Tool"):
        assert second[type_name] == first[type_name]


@pytest.mark.parametrize("build_one", [_project, _model], ids=["project", "model"])
def test_model_card_dataset_keeps_its_own_held_id(build_one: _Build) -> None:
    """A model card's dataset, minted with no lookup, keeps the id held
    under its name (``id import``), never one held for a loom dataset."""
    (minted,) = _ids(build_one(None))["dataset_DatasetPackage"]
    assert minted.endswith("#DatasetPackage-1")
    own = minted.removesuffix("1") + "2"
    registry = IdRegistry.new("demo")
    registry.elements[(DATASET_PACKAGE_TYPE, "data/t.txt")] = RegistryEntry(minted)
    registry.elements[(DATASET_PACKAGE_TYPE, "imdb")] = RegistryEntry(own)

    assert _ids(build_one(registry))["dataset_DatasetPackage"] == {own}


@pytest.mark.parametrize("build_one", [_project, _model], ids=["project", "model"])
def test_enrichment_subject_is_the_base_documents_model_id(build_one: _Build) -> None:
    """``enrich``'s subject id (:func:`_ai_model_identity`) is the one its
    base document mints with the same registry, which holds the first-run
    id under the model's name: a ``loom model`` document's own (kept), a
    project's another key's (reserved)."""
    (first,) = _ids(build_one(None))["ai_AIPackage"]
    registry = IdRegistry.new("demo")
    registry.elements[(AI_PACKAGE_TYPE, "m")] = RegistryEntry(first)
    (base,) = _ids(build_one(registry))["ai_AIPackage"]
    tail = first.split("#")[0].rsplit("/", 1)[1]  # <doc name>-<doc uuid>
    project = build_one is _project
    identity = (tail[:-37], tail[-36:])

    _, _, subject = _ai_model_identity(
        _model_meta(), doc_identity=identity if project else None, registry=registry
    )

    assert subject == base
    assert (base != first) is project


def test_imported_sibling_id_is_never_handed_to_a_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The R4 repro, a registry rooted above the project: v2 (no
    registry) is imported, then v3 (v2's namespace) mints ``x.py``: never
    the id v2 gave ``__init__.py``, which the registry holds."""
    project = tmp_path / "pkgs" / "demo"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "__init__.py").write_bytes(b"")
    (project / "pyproject.toml").write_bytes(
        b'[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        b'[project]\nname = "demo"\nversion = "1.0.0"\n'
        b'[tool.hatch.build.targets.wheel]\npackages = ["src/demo"]\n'
    )
    reg = tmp_path / "reg.json"
    IdRegistry.new("root", project_root=tmp_path).save(reg)
    monkeypatch.chdir(tmp_path)

    def project_run(out: str, *registry: str) -> dict[str, str]:
        argv = ["project", str(project), "-o", out, *registry]
        assert _run_cli(monkeypatch, argv) == 0
        graph = json.loads((tmp_path / out).read_text(encoding="utf-8"))["@graph"]
        return {e["name"]: e["spdxId"] for e in graph if e["type"] == "software_File"}

    project_run("v1.json", "--id-registry", str(reg))
    (project / "src" / "demo" / "x.py").write_bytes(b"x = 1\n")
    v2 = project_run("v2.json")
    assert _run_cli(monkeypatch, ["id", "import", "v2.json", "-o", str(reg)]) == 0
    v3 = project_run("v3.json", "--id-registry", str(reg))

    assert v3["demo/x.py"] not in set(v2.values()) - {v2["demo/x.py"]}
    assert len(set(v3.values())) == len(v3)
