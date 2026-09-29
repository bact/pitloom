# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests: `embed-wheel` resolves its declared ``id_registry``
exactly once for the whole batch, not once per wheel -- both when
resolution fails (a missing declared registry must be a single
``ERROR:`` line, not one per wheel) and when it succeeds (``IdRegistry.load``
called exactly once for a multi-wheel batch), for both the standalone
(``--id-registry`` flag, no project) and project-backed
(``--project-dir``, the project's own ``[tool.pitloom] id-registry``
key) resolution paths.

See also: :mod:`tests.assemble.test_embed_cli` (the rest of `embed-wheel`'s
CLI tests), :mod:`tests.id_registry.test_registry` (``IdRegistry`` itself).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from pitloom import __main__
from pitloom.embed import embed_wheel_sbom
from pitloom.extract.project import read_project
from pitloom.id_registry import IdRegistry

from .conftest import _make_dummy_wheel, _make_sdist


def test_embed_wheel_missing_registry_is_one_error_line_for_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two wheels, a declared but missing ``--id-registry``: exactly one
    ``ERROR:`` line for the whole batch, not one per wheel -- the
    registry is resolved once, before the per-wheel loop."""
    dist_dir = tmp_path / "dist"
    _make_dummy_wheel(dist_dir, "pkg1", "1.0.0")
    _make_dummy_wheel(dist_dir, "pkg2", "1.0.0")
    missing_registry = tmp_path / "missing-registry.json"

    # No pyproject.toml here, so no incidental "no --project-dir given"
    # INFO line competes with the one ERROR: line under test.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(dist_dir / "*.whl"),
            "--id-registry",
            str(missing_registry),
        ],
    )
    exit_code = __main__.main()

    assert exit_code == 1
    err_lines = [line for line in capsys.readouterr().err.splitlines() if line]
    assert len(err_lines) == 1
    assert err_lines[0].startswith("ERROR: ")
    assert "ID registry file" in err_lines[0]


def test_embed_wheel_valid_registry_loads_once_for_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Two wheels, a declared and valid ``--id-registry``:
    ``IdRegistry.load`` is called exactly once for the whole batch, not
    once per wheel."""
    dist_dir = tmp_path / "dist"
    _make_dummy_wheel(dist_dir, "pkg1", "1.0.0")
    _make_dummy_wheel(dist_dir, "pkg2", "1.0.0")
    registry_path = tmp_path / "registry.json"
    IdRegistry.new("demo-1", path=registry_path).save()

    real_load = IdRegistry.load.__func__  # type: ignore[attr-defined]
    spy = Mock(side_effect=real_load)
    monkeypatch.setattr(IdRegistry, "load", classmethod(spy))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(dist_dir / "*.whl"),
            "--id-registry",
            str(registry_path),
        ],
    )
    exit_code = __main__.main()

    assert exit_code == 0
    spy.assert_called_once()


def test_embed_wheel_explicit_registry_skips_config_peek_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit ``id_registry=`` (library API) makes the project's own
    config irrelevant to registry resolution -- ``_resolve_embed_registry``
    must not peek-read it. With an sdist ``project_dir``, ``read_project()``
    is called exactly once in total (the real read inside
    ``_generate_embed_sbom_json``), not twice (peek + real)."""
    sdist = _make_sdist(tmp_path)
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    registry_path = tmp_path / "registry.json"
    IdRegistry.new("demo", path=registry_path).save()

    spy = Mock(side_effect=read_project)
    monkeypatch.setattr("pitloom.embed.read_project", spy)

    embed_wheel_sbom(wheel, project_dir=sdist, id_registry=registry_path)

    spy.assert_called_once()


def test_embed_wheel_project_dir_valid_registry_loads_once_for_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Same as above, with ``--project-dir`` (the project-backed
    resolution path, not the standalone one) and the registry declared
    via the project's own ``[tool.pitloom] id-registry`` key rather than
    a flag -- both must still resolve exactly once for the whole batch."""
    project = tmp_path / "proj"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "src" / "demo" / "__init__.py").write_text(
        "__version__ = '1.0.0'\n", encoding="utf-8"
    )
    registry_path = project / "registry.json"
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[tool.pitloom]\nid-registry = "registry.json"\n',
        encoding="utf-8",
    )
    IdRegistry.new("demo", path=registry_path).save()

    dist_dir = tmp_path / "dist"
    _make_dummy_wheel(dist_dir, "pkg1", "1.0.0")
    _make_dummy_wheel(dist_dir, "pkg2", "1.0.0")

    real_load = IdRegistry.load.__func__  # type: ignore[attr-defined]
    spy = Mock(side_effect=real_load)
    monkeypatch.setattr(IdRegistry, "load", classmethod(spy))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(dist_dir / "*.whl"),
            "--project-dir",
            str(project),
        ],
    )
    exit_code = __main__.main()

    assert exit_code == 0
    spy.assert_called_once()
