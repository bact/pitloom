# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A declared-but-bad registry must fail *before* any expensive/
irreversible work starts -- real ``--allow-build`` file discovery, the
Hatchling hook's document-model build, or ``loom.Run`` leaving a
half-initialized active run behind -- not just eventually, after that
work already ran.

Kept together (rather than filed under each surface's own test module)
since they share this one invariant across three different surfaces; the
plain "one ERROR:/raises ValueError" coverage for a declared-bad
registry lives in :mod:`tests.id_registry.test_surfaces_failures`'s
exhaustive sweeps instead.

See also: :mod:`tests.id_registry.test_surfaces_failures` (every other
surface's declared-bad-registry failure mode, swept across every
declaration mode), :mod:`tests.id_registry.test_surfaces` (the hook's
own "one ERROR:, no sbom_files" assertion).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import pitloom.plugins.hatch as hatch_module
from pitloom import loom
from pitloom.assemble import generate_project_sbom
from pitloom.core.models import get_wheel_files
from pitloom.embed import embed_wheel_sbom
from pitloom.extract.wheel import read_wheel
from tests.assemble.embed_surfaces_shared import demo_project, demo_wheel
from tests.extract.conftest import make_hook


def test_resolve_before_allow_build_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad declared registry must fail before file discovery (including
    a real ``--allow-build``) ever runs -- resolution is moved ahead of
    ``TerminationGuard``/discovery in ``_generators.py``."""
    project = demo_project(tmp_path, '\n[tool.pitloom]\nid-registry = "missing.json"\n')

    calls: list[object] = []
    real = get_wheel_files

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr("pitloom.assemble._generators.get_wheel_files", spy)

    with pytest.raises(ValueError, match="ID registry file"):
        generate_project_sbom(project, creation_metadata=None)

    assert not calls


def test_hook_resolves_registry_before_building_document_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad declared registry must fail before ``_build_document_model``
    (the metadata/file/AI-model scan) ever runs -- resolution moved ahead
    of it in ``initialize()``. Mirrors
    :func:`test_resolve_before_allow_build_discovery` above for the
    Hatchling-hook path."""
    registry_path = tmp_path / "missing.json"
    toml = f"\n[tool.pitloom]\nid-registry = {json.dumps(registry_path.as_posix())}\n"
    project = demo_project(tmp_path, toml)

    calls: list[object] = []
    # pylint: disable-next=protected-access
    real = hatch_module._build_document_model

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        return real(*args, **kwargs)

    monkeypatch.setattr(hatch_module, "_build_document_model", spy)

    hook = make_hook(str(project), {})
    with pytest.raises(ValueError, match=r"^ID registry file "):
        hook.initialize("standard", {})

    assert not calls


def test_embed_wheel_sbom_resolves_registry_before_reading_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad declared registry must fail before ``read_wheel()`` ever
    opens/parses the wheel archive -- resolution moved ahead of it in
    ``embed_wheel_sbom()``. Only applies when *sbom_path* is unset: an
    externally-supplied SBOM never consults the registry at all."""
    wheel = demo_wheel(tmp_path)

    calls: list[object] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(True)
        return read_wheel(*args, **kwargs)

    monkeypatch.setattr("pitloom.embed.read_wheel", spy)

    with pytest.raises(ValueError, match=r"^ID registry file "):
        embed_wheel_sbom(wheel, id_registry=tmp_path / "missing.json")

    assert not calls


def test_loom_run_raises_from_enter_leaves_no_active_run(tmp_path: Path) -> None:
    """A declared-but-bad registry raises from ``Run.__enter__`` before
    the module-global active run is set -- no half-initialized run is
    left behind for a later loom.* call to trip over."""
    # pylint: disable=protected-access
    assert loom._active_run is None

    with pytest.raises(ValueError, match="ID registry file"):
        with loom.run(
            tmp_path / "frag.spdx3.json", id_registry=tmp_path / "missing.json"
        ):
            pass

    assert loom._active_run is None
