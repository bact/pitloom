# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression: a declared, relative ``id_registry`` resolves against the
*current directory* for an sdist-archive target -- not against the
archive path itself (joining a relative path onto a file, rather than a
directory, would never find the file). ``pitloom.id_registry.resolve.
registry_base_dir()`` is the one shared helper every ``resolve_registry()``
call site now uses for this; this test is the drift guard that
:func:`pitloom.embed.embed_wheel_sbom` (``project_dir=<sdist>``) and
:func:`pitloom.assemble.generate_project_sbom` (target=<sdist>) resolve
to the exact same registry file for one shared fixture.

See also: :mod:`pitloom.id_registry.resolve` (the helper itself),
:mod:`tests.assemble.test_sdist_own_config` (sdist config-reading
parity generally).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist


def test_embed_wheel_sbom_sdist_project_dir_loads_registry_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``embed_wheel_sbom(wheel, project_dir=<sdist>, id_registry="reg.json")``
    from a cwd holding ``reg.json`` must load *that* file -- not fail, and
    not look for it relative to the sdist archive's own path."""
    sdist_path = _make_sdist(tmp_path)
    wheel_path = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    registry_path = cwd / "reg.json"
    IdRegistry.new("demo", path=registry_path).save()
    monkeypatch.chdir(cwd)

    real_load = IdRegistry.load.__func__  # type: ignore[attr-defined]
    spy = Mock(side_effect=real_load)
    monkeypatch.setattr(IdRegistry, "load", classmethod(spy))

    embed_wheel_sbom(wheel_path, project_dir=sdist_path, id_registry="reg.json")

    spy.assert_called_once()
    assert spy.call_args.args[-1] == registry_path


def test_embed_wheel_sbom_and_generate_project_sbom_agree_on_sdist_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    """Drift guard: :func:`embed_wheel_sbom` and
    :func:`generate_project_sbom` must resolve an sdist target's declared
    ``id_registry="reg.json"`` to the exact same path."""
    sdist_path = _make_sdist(tmp_path)
    wheel_path = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    registry_path = cwd / "reg.json"
    IdRegistry.new("demo", path=registry_path).save()
    monkeypatch.chdir(cwd)

    embed_wheel_sbom(wheel_path, project_dir=sdist_path, id_registry="reg.json")
    generate_project_sbom(sdist_path, id_registry="reg.json")

    assert len(load_spy) == 2
    assert load_spy[0] == load_spy[1] == registry_path
