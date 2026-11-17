# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saving a registry reads the same on every surface. A save keeps what
another run saved meanwhile. A registry that cannot be saved is one line,
what stopped the save with its code (``file-unwritable`` for a write the
system refused), naming the file once as typed: an ``ERROR:`` (exit 1) for
``id generate``/``id import``, whose output is the registry, its
``WARNING:`` twin (exit 0) for a run's auto-harvest; the file is left as
it was.

See also: tests/id_registry/test_persist_registry.py (the ``WARNING:``
variant in-process), test_cli_id_namespace_root.py (a root that cannot be
stored).
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__
from pitloom._sbom_io import replace_text_lf
from pitloom.cli.parser import command_frame
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    IdRegistry,
    persist_registry,
)
from pitloom.id_registry._counters import MAX_ID_NUMBER
from pitloom.messages import trusted_message
from pitloom.messages.files import FILE_UNWRITABLE
from tests.id_registry.shared import _write_sample_sbom

#: Whether a read-only file refuses this process (root writes through 0o444).
_READ_ONLY_REFUSES = sys.platform == "win32" or os.geteuid() != 0
#: (surface, level of the failed-save line, exit code).
_SURFACES = (
    ("generate", "ERROR", 1),
    ("import", "ERROR", 1),
    ("project", "WARNING", 0),
    ("sbom", "WARNING", 0),
)
_IDS = [surface for surface, _, _ in _SURFACES]


#: The registry as typed: from the project directory, the working one.
_TYPED = "../reg.json"


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str) -> Path:
    """A project, an empty saved registry for it, and *surface*'s argv set,
    the registry named as :data:`_TYPED`; returns the registry path."""
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
        argv += ["-o", _TYPED]
    elif surface == "import":
        _write_sample_sbom(tmp_path / "sample.spdx3.json")
        argv = ["id", "import", str(tmp_path / "sample.spdx3.json")]
        argv += ["-o", _TYPED]
    else:
        # "sbom": loom generate, which saves as loom project does.
        command = "project" if surface == "project" else "generate"
        argv = [command, str(project), "--id-registry", _TYPED]
        argv += ["-o", str(tmp_path / "out.spdx3.json"), "--offline"]
    monkeypatch.chdir(project)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    return registry


def _assert_one_failed_save(err: str, surface: str, level: str, reason: str) -> None:
    # Only an ERROR line is framed (``loom id import: ``); the project
    # surface says it as a WARNING.
    frame = command_frame(f"id {surface}") if level == "ERROR" else ""
    lines = err.splitlines()
    saves = [line for line in lines if "could not write" in line]
    assert len(saves) == 1, lines
    assert saves[0] == (
        f"{level}: {frame}FILE={_TYPED}: could not write for the ID registry; "
        f"{reason} [file-unwritable]"
    )
    assert trusted_message(saves[0]) is FILE_UNWRITABLE
    assert "failed to save" not in err
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
    _assert_one_failed_save(
        capsys.readouterr().err, surface, level, os.strerror(errno.EACCES)
    )
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
    _assert_one_failed_save(capsys.readouterr().err, surface, level, "disk full")
    assert registry.read_bytes() == before


@pytest.mark.parametrize("fails", [True, False], ids=["save-fails", "saved"])
def test_the_entity_key_info_waits_for_the_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fails: bool,
) -> None:
    """``-e ./demo/__init__.py`` is stored as ``demo/__init__.py``: that
    ``INFO:`` is said once the registry is written, never before the
    ``ERROR:`` of a save that writes nothing. The registry writer
    (patched where ``_format`` imported it, not on the shared ``os``)
    fails with a full disk."""
    _prepare(tmp_path, monkeypatch, "generate")
    argv = [*sys.argv, "-e", f"./demo/__init__.py:{FILE_TYPE}"]
    monkeypatch.setattr(sys, "argv", argv)
    real = replace_text_lf
    calls: list[str] = []

    def _write(path: Path | str, text: str) -> None:
        calls.append(str(path))
        if fails:
            raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), str(path))
        real(path, text)

    capsys.readouterr()
    monkeypatch.setattr("pitloom.id_registry._format.replace_text_lf", _write)
    rc = __main__.main()

    err = capsys.readouterr().err
    assert calls  # not vacuous: the save reached the writer
    assert rc == int(fails)
    stored = "INFO: ID registry: -e ./demo/__init__.py stored as demo/__init__.py\n"
    assert (stored in err) is not fails
    if fails:
        _assert_one_failed_save(err, "generate", "ERROR", os.strerror(errno.ENOSPC))


def test_a_repeated_entity_key_info_is_said_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _prepare(tmp_path, monkeypatch, "generate")
    entity = f"./demo/__init__.py:{FILE_TYPE}"
    monkeypatch.setattr(sys, "argv", [*sys.argv, "-e", entity, "-e", entity])
    capsys.readouterr()

    assert __main__.main() == 0

    stored = "INFO: ID registry: -e ./demo/__init__.py stored as demo/__init__.py"
    assert capsys.readouterr().err.splitlines().count(stored) == 1


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
    assert err.startswith(
        f"ERROR: {command_frame('id generate')}ID registry: FILE={_TYPED}: "
        "no File id left to mint"
    )
    assert len(err.splitlines()) == 1
    assert registry.read_bytes() == before


#: The registry method each surface calls between its load and its save.
_MIDDLE = {
    "generate": "generate",
    "import": "import_sbom",
    "project": "harvest",
    "sbom": "harvest",
}


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
