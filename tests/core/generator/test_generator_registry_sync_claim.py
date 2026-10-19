# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Id-mint collisions, calling
``build()``/``build_deployed()`` directly (rather than the
``generate_*_sbom()`` string-returning wrappers) so every assertion runs
against the exporter's own ``object_set`` -- never the serialized JSON,
which can mask a real duplicate id (see
:mod:`tests.core.generator.test_generator_registry_sync_ai`'s
``_assert_ten_distinct_ai_package_ids`` docstring for why).

Covers: a stale registry entry from a file/dependency absent in one run
colliding with a later run's fresh mint (the harvest-time one-key-per-id
invariant, ``pitloom.id_registry._harvest._release_stale_keys_for_id``,
and the session's claim), and two elements in the *same* run legitimately
hitting one registered id (resolved by
``pitloom.id_registry.IdRegistrySession``'s first-claimant-wins).

See also: :mod:`tests.core.generator.test_generator_registry_sync` and
:mod:`tests.core.generator.test_generator_registry_sync_env` for the
same scenarios exercised through the public ``generate_wheel_sbom()``/
``generate_env_sbom()`` API instead.

See also: test_generator_registry_sync_claim_resolve.py (the resolve_*()
collision tests, called directly on the claimed dicts).
"""

from __future__ import annotations

import hashlib

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import IdRegistry
from tests.core.generator._generator_registry_sync_claim_shared import (
    _files_for,
)

from ...conftest import _assert_no_duplicate_spdx_ids


def _build_with(files: list[ProjectFile], registry: IdRegistry) -> Spdx3JsonExporter:
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0.0", files=files),
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    exporter = build(doc, registry=registry)
    _assert_no_duplicate_spdx_ids(exporter=exporter)
    registry.harvest(exporter.object_set, keys=exporter.registry_keys)
    return exporter


def test_stale_file_entry_no_longer_collides_across_three_runs() -> None:
    """run1 {a, b}: b registers some id N. run2 {a, c}: b isn't part of
    this run at all, so nothing reserves N, and c's fresh mint can
    coincidentally land on it too -- the stale b-entry must not survive
    to collide when b returns in run3 {a, b, c}."""
    registry = IdRegistry.new("demo")

    _build_with(_files_for({"a.py": "a\n", "b.py": "b\n"}), registry)
    _build_with(_files_for({"a.py": "a\n", "c.py": "c\n"}), registry)
    exporter3 = _build_with(
        _files_for({"a.py": "a\n", "b.py": "b\n", "c.py": "c\n"}), registry
    )

    files = [
        obj
        for obj in exporter3.object_set.objects
        if isinstance(obj, spdx3.software_File)
    ]
    by_name = {f.name: f.spdxId for f in files}
    assert by_name["demo/b.py"] != by_name["demo/c.py"]


def _init_py_files(*dirs: str) -> list[ProjectFile]:
    """One empty ``<dir>/__init__.py`` per *dirs*, all sharing one sha256
    (the empty-file hash) -- same content, unrelated paths."""
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    return sorted(
        (
            ProjectFile(
                physical_path=f"demo/{d}/__init__.py",
                distribution_path=f"demo/{d}/__init__.py",
                digest_sha256=empty_sha256,
            )
            for d in dirs
        ),
        key=lambda f: f.distribution_path,
    )


def test_same_content_unrelated_paths_do_not_alias_across_three_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """run1 {a, b}, run2 {b, c}, run3 {a, b, c}, all empty (identical
    content) ``__init__.py`` files: matching sha256 never makes two paths
    one id -- a (reappearing in run3) and c get distinct ids, with no
    warning, and c (present and unchanged since run2) keeps its id: its
    minted id is harvested under its own key (``record_key``)."""
    registry = IdRegistry.new("demo")

    _build_with(_init_py_files("a", "b"), registry)
    exporter2 = _build_with(_init_py_files("b", "c"), registry)
    c_id_after_run2 = {
        f.name: f.spdxId
        for f in exporter2.object_set.objects
        if isinstance(f, spdx3.software_File)
    }["demo/c/__init__.py"]

    with caplog.at_level("WARNING"):
        exporter3 = _build_with(_init_py_files("a", "b", "c"), registry)

    by_name = {
        f.name: f.spdxId
        for f in exporter3.object_set.objects
        if isinstance(f, spdx3.software_File)
    }
    assert by_name["demo/a/__init__.py"] != by_name["demo/c/__init__.py"]
    assert by_name["demo/c/__init__.py"] == c_id_after_run2
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert not warnings


def test_deployed_env_no_collision_across_four_runs() -> None:
    """run1 {requests} -> run2 {aaa, requests} -> run3 {bbb, requests} ->
    run4 {aaa, bbb, requests}: a dependency absent from one run (aaa
    missing in run3, bbb missing in run2) must not leave a stale entry
    that collides once it returns."""
    registry = IdRegistry.new("deployed-environment")

    def _run(keys: list[str]) -> Spdx3JsonExporter:
        project = ProjectMetadata(name="deployed-environment", version="0.0.0")
        doc = DocumentModel(
            project=project,
            creation_metadata=CreationMetadata(
                creation_datetime="2026-01-01T00:00:00+00:00"
            ),
        )
        env_tree = [
            {"package": {"key": k, "package_name": k, "installed_version": "1.0"}}
            for k in keys
        ]
        exporter = build_deployed(doc, env_tree, registry=registry)
        _assert_no_duplicate_spdx_ids(exporter=exporter)
        registry.harvest(exporter.object_set)
        return exporter

    _run(["requests"])
    _run(["aaa", "requests"])
    _run(["bbb", "requests"])
    exporter4 = _run(["aaa", "bbb", "requests"])

    packages = [
        obj
        for obj in exporter4.object_set.objects
        if isinstance(obj, spdx3.software_Package)
    ]
    by_name = {p.name: p.spdxId for p in packages}
    assert by_name["aaa"] != by_name["bbb"]


def test_ai_model_stem_collision_keeps_both_elements_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Two models legitimately sharing a file stem (the only lookup
    candidate left when neither has a name/physical_path) both hit the
    *same* pre-registered ``ai_AIPackage`` entity in one run -- unlike
    the stale-entry cases above, this is a genuine simultaneous collision
    the first-claimant-wins rule must resolve: the first model reuses the entry, the second mints its own
    id and logs exactly one warning, and *both* elements survive."""
    registry = IdRegistry.new("ai-project")
    registered_id = registry.register("ai_AIPackage", "weights")

    ai_models = [
        AiModelMetadata(
            format_info=AiModelFormatInfo(
                file_name="weights.npy",
                file_path_relative=f"{d}/weights.npy",
                model_format=AiModelFormat.NUMPY,
            ),
        )
        for d in ("a", "b")
    ]
    doc = DocumentModel(
        project=ProjectMetadata(name="ai-project", version="0.1.0"),
        creation_metadata=CreationMetadata(),
        ai_models=ai_models,
    )

    with caplog.at_level("WARNING"):
        exporter = build(doc, registry=registry)
    _assert_no_duplicate_spdx_ids(exporter=exporter)

    ai_pkgs = [
        obj
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.ai_AIPackage)
    ]
    assert len(ai_pkgs) == 2
    ids = {str(obj.spdxId) for obj in ai_pkgs}
    assert len(ids) == 2
    assert registered_id in ids

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "registered for both" in warnings[0].message
