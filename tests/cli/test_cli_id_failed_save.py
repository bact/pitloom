# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saving a registry reads the same on every surface. A save keeps what
another run saved meanwhile. A registry that cannot be saved is one
``ID registry: failed to save <path>: <reason>`` line, an ``ERROR:`` (exit
1) for ``id generate``/``id import``, whose output is the registry, a
``WARNING:`` (exit 0) for a run's auto-harvest; the file is left as it was.

See also: tests/id_registry/test_persist_registry.py (the ``WARNING:``
variant in-process), test_cli_id_namespace_root.py (a root that cannot be
stored).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom.id_registry import AI_PACKAGE_TYPE, IdRegistry, persist_registry
from pitloom.id_registry._counters import MAX_ID_NUMBER
from tests.id_registry.shared import _write_sample_sbom

#: Whether a read-only file refuses this process (root writes through 0o444).
_READ_ONLY_REFUSES = sys.platform == "win32" or os.geteuid() != 0
#: (surface, level of the failed-save line, exit code).
_SURFACES = (
    ("generate", "ERROR", 1),
    ("import", "ERROR", 1),
    ("project", "WARNING", 0),
)
_IDS = [surface for surface, _, _ in _SURFACES]


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str) -> Path:
    """A project, an empty saved registry for it, and *surface*'s argv set;
    returns the registry path."""
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    registry = tmp_path / "reg.json"
    IdRegistry.new("demo", path=registry, project_root=project).save()
    if surface == "generate":
        argv = ["id", "generate", str(project), "--project-dir", str(project)]
        argv += ["-o", str(registry)]
    elif surface == "import":
        _write_sample_sbom(tmp_path / "sample.spdx3.json")
        argv = ["id", "import", str(tmp_path / "sample.spdx3.json")]
        argv += ["-o", str(registry)]
    else:
        argv = ["project", str(project), "--id-registry", str(registry)]
        argv += ["-o", str(tmp_path / "out.spdx3.json"), "--offline"]
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return registry


def _assert_one_failed_save(err: str, level: str, registry: Path, reason: str) -> None:
    lines = err.splitlines()
    saves = [line for line in lines if "failed to save" in line]
    assert len(saves) == 1, lines
    assert saves[0].startswith(f"{level}: ID registry: failed to save {registry}: ")
    assert reason in saves[0]
    assert "Traceback" not in err
    errors = [line for line in lines if line.startswith("ERROR: ")]
    assert errors == (saves if level == "ERROR" else [])


@pytest.mark.skipif(not _READ_ONLY_REFUSES, reason="root writes a read-only file")
@pytest.mark.parametrize(("surface", "level", "code"), _SURFACES, ids=_IDS)
def test_a_read_only_registry_is_one_failed_save_line_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    level: str,
    code: int,
) -> None:
    registry = _prepare(tmp_path, monkeypatch, surface)
    before = registry.read_bytes()
    os.chmod(registry, 0o444)
    capsys.readouterr()
    try:
        rc = __main__.main()
    finally:
        os.chmod(registry, 0o644)

    assert rc == code
    _assert_one_failed_save(capsys.readouterr().err, level, registry, "")
    assert registry.read_bytes() == before


@pytest.mark.parametrize(("surface", "level", "code"), _SURFACES, ids=_IDS)
def test_a_failed_registry_write_is_one_failed_save_line_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    level: str,
    code: int,
) -> None:
    """The same with the write itself failing (every platform, root too)."""
    registry = _prepare(tmp_path, monkeypatch, surface)
    before = registry.read_bytes()
    capsys.readouterr()
    with patch(
        "pitloom.id_registry._format.replace_text_lf",
        autospec=True,
        side_effect=OSError("disk full"),
    ):
        rc = __main__.main()

    assert rc == code
    _assert_one_failed_save(capsys.readouterr().err, level, registry, "disk full")
    assert registry.read_bytes() == before


def test_id_generate_failing_before_the_save_is_not_a_failed_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No id left to mint: the error says so, not ``failed to save``."""
    registry = _prepare(tmp_path, monkeypatch, "generate")
    full = IdRegistry.load(registry)
    full.id_counters["File"] = MAX_ID_NUMBER
    full.save()
    before = registry.read_bytes()
    capsys.readouterr()

    assert __main__.main() == 1

    err = capsys.readouterr().err
    assert err.startswith("ERROR: ID registry: no File id left to mint")
    assert len(err.splitlines()) == 1
    assert registry.read_bytes() == before


#: The registry method each surface calls between its load and its save.
_MIDDLE = {"generate": "generate", "import": "import_sbom", "project": "harvest"}


@pytest.mark.parametrize(("surface", "level", "code"), _SURFACES, ids=_IDS)
def test_a_run_saving_meanwhile_is_kept_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    level: str,
    code: int,
) -> None:
    """A loom run saves while the command runs: its entry and its counter
    stay, so its id is never minted again (I8). Every surface re-reads the
    file before saving."""
    del level, code
    registry = _prepare(tmp_path, monkeypatch, surface)
    method = _MIDDLE[surface]
    real = getattr(IdRegistry, method)
    minted: list[str] = []

    def _meanwhile(self: IdRegistry, *args: object, **kwargs: object) -> object:
        result = real(self, *args, **kwargs)
        other = IdRegistry.load(registry)
        minted.append(other.register(AI_PACKAGE_TYPE, "model-a", sha256="1" * 64))
        persist_registry(other, 1, True)
        return result

    monkeypatch.setattr(IdRegistry, method, _meanwhile)
    assert __main__.main() == 0
    monkeypatch.undo()

    saved = IdRegistry.load(registry)
    assert saved.lookup(AI_PACKAGE_TYPE, ["model-a"]) == minted[0]
    assert saved.register(AI_PACKAGE_TYPE, "model-b") != minted[0]
