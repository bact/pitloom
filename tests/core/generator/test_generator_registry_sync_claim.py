# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the id-mint-collision fixes ([#234]), calling
``build()``/``build_deployed()`` directly (rather than the
``generate_*_sbom()`` string-returning wrappers) so every assertion runs
against the exporter's own ``object_set`` -- never the serialized JSON,
which can mask a real duplicate id (see
:mod:`tests.core.generator.test_generator_registry_sync_ai`'s
``_assert_ten_distinct_ai_package_ids`` docstring for why).

Covers: a stale registry entry from a file/dependency absent in one run
colliding with a later run's fresh mint (fixed by
``pitloom.id_registry._harvest._release_stale_keys_for_id``, the harvest-time one-key-
per-id invariant), and two elements in the *same* run legitimately
hitting one registered id (fixed by
``pitloom.id_registry.IdRegistrySession``'s first-claimant-wins).

See also: :mod:`tests.core.generator.test_generator_registry_sync` and
:mod:`tests.core.generator.test_generator_registry_sync_env` for the
same scenarios exercised through the public ``generate_wheel_sbom()``/
``generate_env_sbom()`` API instead.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._document_deployed import _resolve_deployed_package_hits
from pitloom.assemble.spdx3._document_files import _resolve_file_and_directory_hits
from pitloom.assemble.spdx3.ai import resolve_ai_model_entity_hits
from pitloom.assemble.spdx3.document import build, build_deployed
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import ProjectFile, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.id_registry import IdRegistry, IdRegistrySession
from pitloom.id_registry._types import FileEntry

from ...conftest import _assert_no_duplicate_spdx_ids


def _files_for(contents: dict[str, str]) -> list[ProjectFile]:
    """One ``ProjectFile`` per ``{name: content}`` entry, sorted by name
    for deterministic iteration order."""
    return [
        ProjectFile(
            physical_path=f"demo/{name}",
            distribution_path=f"demo/{name}",
            digest_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )
        for name, content in sorted(contents.items())
    ]


def _build_with(files: list[ProjectFile], registry: IdRegistry) -> Spdx3JsonExporter:
    doc = DocumentModel(
        project=ProjectMetadata(name="demo", version="1.0.0", files=files),
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
    )
    exporter = build(doc, registry=registry)
    _assert_no_duplicate_spdx_ids(exporter=exporter)
    registry.harvest(exporter.object_set)
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
    (the empty-file hash) -- same content, unrelated paths, so none of
    them are the legitimate physical-path/distribution-path alias
    :func:`pitloom.id_registry._harvest._is_files_path_alias` recognises."""
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
    content) ``__init__.py`` files: matching sha256 alone must not be
    treated as the physical/distribution-path alias -- c (present and
    unchanged since run2) must keep its id, and a (reappearing in run3)
    gets a fresh mint instead of colliding with c's, with no warning."""
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
    assert by_name["demo/c/__init__.py"] == c_id_after_run2
    assert by_name["demo/a/__init__.py"] != c_id_after_run2
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
    the stale-entry cases above, this is not a bug to clean up, it's a
    genuine simultaneous collision the first-claimant-wins rule must
    resolve: the first model reuses the entry, the second mints its own
    id and logs exactly one warning, and *both* elements survive."""
    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity("weights", "ai_AIPackage")

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


def test_resolve_file_hits_default_claimed_dict_collision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Direct unit coverage of ``_resolve_file_and_directory_hits`` called
    with no shared *claimed* dict (its default, ``None``): two distinct
    files whose registry entries happen to hold the identical id (a stale
    registry, constructed directly rather than via a multi-run harvest)
    must not both claim it -- the second falls back to a miss, logging
    one warning."""
    registry = IdRegistry.new("demo")
    files = _files_for({"a.py": "a\n", "b.py": "b\n"})
    collided_id = f"{registry.namespace}#File-1"
    registry.files["demo/a.py"] = FileEntry(
        spdx_id=collided_id, sha256=hashlib.sha256(b"a\n").hexdigest()
    )
    registry.files["demo/b.py"] = FileEntry(
        spdx_id=collided_id, sha256=hashlib.sha256(b"b\n").hexdigest()
    )

    with caplog.at_level("WARNING"):
        _dir_hits, file_hits = _resolve_file_and_directory_hits(
            files, IdRegistrySession(registry)
        )

    assert len(file_hits) == 1
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


def test_resolve_deployed_hits_default_claimed_dict_collision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Direct unit coverage of ``_resolve_deployed_package_hits`` called
    with no shared *claimed* dict (its default, ``None``): two distinct
    dependencies whose registry entries hold the identical id must not
    both claim it."""
    registry = IdRegistry.new("deployed-environment")
    collided_id = registry.register_entity("aaa", "software_Package")
    registry.entities[("software_Package", "bbb")] = registry.entities[
        ("software_Package", "aaa")
    ]
    env_tree = [
        {"package": {"key": "aaa", "package_name": "aaa", "installed_version": "1.0"}},
        {"package": {"key": "bbb", "package_name": "bbb", "installed_version": "1.0"}},
    ]

    with caplog.at_level("WARNING"):
        hits = _resolve_deployed_package_hits(env_tree, IdRegistrySession(registry))

    assert len(hits) == 1
    assert collided_id in hits.values()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


def test_resolve_ai_model_hits_default_claimed_dict() -> None:
    """Direct unit coverage of ``resolve_ai_model_entity_hits`` called
    with a fresh, unshared session."""
    registry = IdRegistry.new("ai-project")
    registered_id = registry.register_entity("model", "ai_AIPackage")
    ai_models = [
        AiModelMetadata(
            format_info=AiModelFormatInfo(
                file_name="model.bin", model_format=AiModelFormat.FASTTEXT
            ),
        )
    ]

    hits = resolve_ai_model_entity_hits(ai_models, IdRegistrySession(registry))

    assert hits == [registered_id]


def test_resolve_deployed_hits_shared_claimed_dict() -> None:
    """``_resolve_deployed_package_hits`` accepts a caller-supplied
    *session* (not a fresh one per call) -- ``build_deployed()`` doesn't
    currently share one across calls, since a deployed environment is a
    single, self-contained resolution pass, but the parameter exists for
    symmetry with the other resolvers and must behave the same way when
    a caller does pass one in."""
    registry = IdRegistry.new("deployed-environment")
    registered_id = registry.register_entity("aaa", "software_Package")
    env_tree = [
        {"package": {"key": "aaa", "package_name": "aaa", "installed_version": "1.0"}}
    ]

    hits = _resolve_deployed_package_hits(env_tree, IdRegistrySession(registry))

    assert hits == {"aaa": registered_id}


def test_resolve_deployed_hits_no_registry_is_noop() -> None:
    """``_resolve_deployed_package_hits(env_tree, IdRegistrySession(None))``
    returns ``{}`` without touching *env_tree* at all -- the no-registry
    branch every other resolver's docstring documents too."""
    env_tree = [
        {"package": {"key": "aaa", "package_name": "aaa", "installed_version": "1.0"}}
    ]

    assert not _resolve_deployed_package_hits(env_tree, IdRegistrySession(None))


def test_resolve_directory_hits_collision(caplog: pytest.LogCaptureFixture) -> None:
    """Two distinct directories whose registry entries hold the identical
    id must not both claim it."""
    registry = IdRegistry.new("demo")
    collided_id = registry.register_entity("dirA", "software_File")
    registry.entities[("software_File", "dirB")] = registry.entities[
        ("software_File", "dirA")
    ]
    files = [
        ProjectFile(
            physical_path="dirA/a.py",
            distribution_path="dirA/a.py",
            digest_sha256=hashlib.sha256(b"a\n").hexdigest(),
        ),
        ProjectFile(
            physical_path="dirB/b.py",
            distribution_path="dirB/b.py",
            digest_sha256=hashlib.sha256(b"b\n").hexdigest(),
        ),
    ]

    with caplog.at_level("WARNING"):
        dir_hits, _file_hits = _resolve_file_and_directory_hits(
            files, IdRegistrySession(registry)
        )

    assert len(dir_hits) == 1
    assert collided_id in dir_hits.values()


def test_resolve_directory_hits_collision_warns_once_across_many_files(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stale registry with ``demo`` and ``demo/sub`` sharing one id,
    with several files under ``demo/sub``: the collision on ``demo/sub``
    is resolved once, on the first file, not re-looked-up and re-warned
    for every later file under it (regression for a directory whose hit
    was rejected -- not recorded in ``dir_hits`` -- being memoized only
    by ``dir_hits`` membership)."""
    registry = IdRegistry.new("demo")
    collided_id = registry.register_entity("demo", "software_File")
    registry.entities[("software_File", "demo/sub")] = registry.entities[
        ("software_File", "demo")
    ]
    files = [
        ProjectFile(
            physical_path=f"demo/sub/{name}",
            distribution_path=f"demo/sub/{name}",
            digest_sha256=hashlib.sha256(name.encode()).hexdigest(),
        )
        for name in ("a.py", "b.py", "c.py", "d.py", "e.py")
    ]

    with caplog.at_level("WARNING"):
        dir_hits, file_hits = _resolve_file_and_directory_hits(
            files, IdRegistrySession(registry)
        )

    warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "registered for both" in r.message
    ]
    assert len(warnings) == 1
    assert dir_hits["demo"] == collided_id
    assert "demo/sub" not in dir_hits
    assert len(file_hits) == 0
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


def test_resolve_file_hits_absolute_physical_path_falls_back_to_distribution_path() -> (
    None
):
    """An ``--allow-build`` discovered file's ``physical_path`` is an
    *absolute* path into a temp extraction directory (see
    ``ProjectFile.physical_path``'s docstring), not project-relative --
    looking the registry up under it directly can never hit an entry
    keyed by the project-relative path. :func:`_resolve_file_and_directory_hits`
    must use :func:`~pitloom.core.project.project_relative_or_fallback` (which
    falls back to ``distribution_path`` for an absolute ``physical_path``)
    for the first lookup, so the file still hits, and must never call
    ``registry.lookup_file`` with the raw absolute path.

    Builds the absolute path from ``tempfile.gettempdir()`` at test-run
    time rather than a hardcoded POSIX literal, so this exercises the
    genuinely-absolute branch on Windows too."""
    registry = IdRegistry.new("demo")
    registered_id = registry.register_file(
        "demo/pkg/mod.py", hashlib.sha256(b"mod\n").hexdigest()
    )
    absolute_physical = str(
        Path(tempfile.gettempdir()) / "pitloom-build-xyz" / "mod.py"
    )
    files = [
        ProjectFile(
            physical_path=absolute_physical,
            distribution_path="demo/pkg/mod.py",
            digest_sha256=hashlib.sha256(b"mod\n").hexdigest(),
        )
    ]

    with patch.object(
        IdRegistry, "lookup_file", autospec=True, side_effect=IdRegistry.lookup_file
    ) as spy:
        _dir_hits, file_hits = _resolve_file_and_directory_hits(
            files, IdRegistrySession(registry)
        )

    assert file_hits["demo/pkg/mod.py"] == registered_id
    called_with_absolute = any(
        call.args[1] == absolute_physical for call in spy.call_args_list
    )
    assert not called_with_absolute


def test_ai_model_collision_warning_names_the_shown_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The collision warning labels each model by the name its SBOM shows
    (stripped), not the padded name read from the file."""
    registry = IdRegistry.new("ai-project")
    registry.register_entity("BERT", "ai_AIPackage")
    ai_models = [
        AiModelMetadata(
            name=" BERT ",
            format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        )
        for _ in range(2)
    ]
    with caplog.at_level(logging.WARNING):
        hits = resolve_ai_model_entity_hits(ai_models, IdRegistrySession(registry))
    assert hits[0] is not None and hits[1] is None
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "both BERT and BERT; BERT gets" in warnings[0]  # labels unpadded
