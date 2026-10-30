# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The resolve_*() collision paths of the id-mint collisions,
called directly on the claimed dicts.

See also: test_generator_registry_sync_claim.py (the multi-run collision
tests), _generator_registry_sync_claim_shared.py (shared helper).
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble.spdx3._document_deployed import _resolve_deployed_package_hits
from pitloom.assemble.spdx3._document_file_hits import (
    _resolve_file_and_directory_hits,
)
from pitloom.assemble.spdx3.ai import resolve_ai_model_entity_hits
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.id_registry import FILE_TYPE, IdRegistry, IdRegistrySession, RegistryEntry
from tests.core.generator._generator_registry_sync_claim_shared import (
    _files_for,
)


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
    registry.elements[(FILE_TYPE, "demo/a.py")] = RegistryEntry(
        spdx_id=collided_id, sha256=hashlib.sha256(b"a\n").hexdigest()
    )
    registry.elements[(FILE_TYPE, "demo/b.py")] = RegistryEntry(
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
    collided_id = registry.register("software_Package", "aaa@1.0")
    registry.elements[("software_Package", "bbb@1")] = registry.elements[
        ("software_Package", "aaa@1")
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
    registered_id = registry.register("ai_AIPackage", "model")
    ai_models = [
        AiModelMetadata(
            format_info=AiModelFormatInfo(
                file_name="model.bin", model_format=AiModelFormat.FASTTEXT
            ),
        )
    ]

    hits = resolve_ai_model_entity_hits(ai_models, IdRegistrySession(registry))

    assert hits.ids == [registered_id]


def test_resolve_deployed_hits_shared_claimed_dict() -> None:
    """``_resolve_deployed_package_hits`` accepts a caller-supplied
    *session* (not a fresh one per call) -- ``build_deployed()`` doesn't
    currently share one across calls, since a deployed environment is a
    single, self-contained resolution pass, but the parameter exists for
    symmetry with the other resolvers and must behave the same way when
    a caller does pass one in."""
    registry = IdRegistry.new("deployed-environment")
    registered_id = registry.register("software_Package", "aaa@1.0")
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
    collided_id = registry.register("software_File", "dirA")
    registry.elements[("software_File", "dirB")] = registry.elements[
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
    for every later file under it (a directory whose hit was rejected is not
    recorded in ``dir_hits``, so it is memoised separately)."""
    registry = IdRegistry.new("demo")
    collided_id = registry.register("software_File", "demo")
    registry.elements[("software_File", "demo/sub")] = registry.elements[
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
    ``registry.lookup`` with the raw absolute path.

    Builds the absolute path from ``tempfile.gettempdir()`` at test-run
    time rather than a hardcoded POSIX literal, so this exercises the
    genuinely-absolute branch on Windows too."""
    registry = IdRegistry.new("demo")
    registered_id = registry.register(
        FILE_TYPE, "demo/pkg/mod.py", sha256=hashlib.sha256(b"mod\n").hexdigest()
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
        IdRegistry, "lookup", autospec=True, side_effect=IdRegistry.lookup
    ) as spy:
        _dir_hits, file_hits = _resolve_file_and_directory_hits(
            files, IdRegistrySession(registry)
        )

    assert file_hits["demo/pkg/mod.py"] == registered_id
    assert spy.call_args_list
    called_with_absolute = any(
        absolute_physical in call.args[2] for call in spy.call_args_list
    )
    assert not called_with_absolute


def test_ai_model_collision_warning_names_the_shown_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The collision warning labels each model by the name its SBOM shows
    (stripped), not the padded name read from the file."""
    registry = IdRegistry.new("ai-project")
    registry.register("ai_AIPackage", "BERT")
    ai_models = [
        AiModelMetadata(
            name=" BERT ",
            format_info=AiModelFormatInfo(model_format=AiModelFormat.GGUF),
        )
        for _ in range(2)
    ]
    with caplog.at_level(logging.WARNING):
        hits = resolve_ai_model_entity_hits(ai_models, IdRegistrySession(registry))
    assert hits.ids[0] is not None and hits.ids[1] is None
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "both BERT and BERT; BERT gets" in warnings[0]  # labels unpadded
