# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression: a build-flag "has no effect" ``WARNING:`` must precede any
project-metadata/lock-file ``WARNING:`` on a surface that reads metadata
before generation -- ``loom project``'s CLI handler and
``generate_project_sbom()`` both resolve a project's metadata (and its
lock/pin-file cascade) as one of their first steps, so without
:meth:`~pitloom.core.build_options.BuildOptions.settle` running first, a
user who passed e.g. ``--build-timeout`` but forgot ``--allow-build``
would see the build-flag warning only after unrelated metadata warnings,
easy to miss in a long run.

See also: :mod:`tests.test_build_flag_warnings` for the cross-surface
exact-count/reason matrix this change leaves unchanged; and
:mod:`tests.core.test_build_options` for the ``settle()`` unit tests.
"""

from __future__ import annotations

import logging
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core.build_options import BuildOptions
from tests.assemble.conftest import _make_dummy_wheel

_METADATA_WARNING_SUBSTRING = "conflicting versions"
_BUILD_WARNING_SUBSTRING = "--build-timeout has no effect"
_NON_PROJECT_BUILD_WARNING_SUBSTRING = "--build-timeout has no effect for this target"
_SDIST_MEMBER_METADATA_WARNING_SUBSTRING = (
    "Failed to parse pyproject.toml from sdist member"
)
_SIBLING_CONFIG_METADATA_WARNING_SUBSTRING = "could not read project config"


def _make_conflicting_pins_project(tmp_path: Path) -> Path:
    """A minimal Hatchling project whose ``requirements.txt`` pins
    ``requests`` to two different versions -- disqualifies the whole
    file and logs one ``WARNING:`` naming the conflict (see
    ``tests/extract/lock/test_requirements.py``'s sibling coverage of
    the extractor itself)."""
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text(
        "requests==2.31.0\nidna==3.7\nrequests==2.32.0\n", encoding="utf-8"
    )
    return project


def _make_sdist_with_malformed_member_pyproject(tmp_path: Path) -> Path:
    """A minimal sdist archive with no ``PKG-INFO`` and a malformed
    internal ``pyproject.toml`` -- ``read_sdist()``'s fallback parse
    (``_parse_pyproject_bytes()``) logs one ``WARNING:`` while resolving
    the archive's own metadata."""
    member_root = tmp_path / "sdist_src" / "demo-1.0.0"
    (member_root / "demo").mkdir(parents=True)
    (member_root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (member_root / "pyproject.toml").write_text("[project\nname = broken\n")
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tar:
        tar.add(member_root, arcname="demo-1.0.0")
    return sdist_path


def _make_sdist_with_malformed_sibling_pyproject(tmp_path: Path) -> Path:
    """A well-formed sdist archive placed next to a malformed *sibling*
    ``pyproject.toml`` on disk -- ``loom generate``'s non-fast-path
    ``_resolve_common_options()`` peek reads that sibling (never the
    archive's own internal metadata) and logs one ``WARNING:`` while
    resolving ``[tool.pitloom]`` config for it."""
    project_dir = tmp_path / "gendir"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text('[project\nname = "broken"\n')

    member_root = tmp_path / "sdist_src" / "demo-1.0.0"
    (member_root / "demo").mkdir(parents=True)
    (member_root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (member_root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    sdist_path = project_dir / "demo-1.0.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tar:
        tar.add(member_root, arcname="demo-1.0.0")
    return sdist_path


def _first_index(messages: list[str], substring: str) -> int:
    for index, message in enumerate(messages):
        if substring in message:
            return index
    raise AssertionError(f"no line containing {substring!r} in {messages}")


def test_cli_project_build_flag_warning_precedes_metadata_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom project`` on real argv: the stray ``--build-timeout``
    warning (no ``--allow-build`` given) must reach stderr before the
    ``requirements.txt`` conflict warning that
    ``_resolve_project_generation_settings()`` triggers while resolving
    metadata -- previously the reverse, since that resolution ran before
    ``generate_project_sbom()`` ever saw the build options.
    """
    project = _make_conflicting_pins_project(tmp_path)
    output = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["loom", "project", str(project), "--build-timeout", "5", "-o", str(output)],
    )

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert __main__.main() == 0

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert _first_index(messages, _BUILD_WARNING_SUBSTRING) < _first_index(
        messages, _METADATA_WARNING_SUBSTRING
    )

    stderr_lines = capsys.readouterr().err.splitlines()
    assert _first_index(stderr_lines, _BUILD_WARNING_SUBSTRING) < _first_index(
        stderr_lines, _METADATA_WARNING_SUBSTRING
    )


def test_library_generate_project_sbom_build_flag_warning_precedes_metadata_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Same regression, library API: ``generate_project_sbom()`` must
    settle/warn about a stray ``--build-timeout`` before its own
    ``resolve_project_with_lockfile()`` call, not after."""
    project = _make_conflicting_pins_project(tmp_path)

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        generate_project_sbom(
            project, offline=True, build_options=BuildOptions(timeout=5)
        )

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert _first_index(messages, _BUILD_WARNING_SUBSTRING) < _first_index(
        messages, _METADATA_WARNING_SUBSTRING
    )


def test_cli_project_sdist_build_flag_warning_precedes_metadata_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom project`` on an sdist archive target: the "has no effect
    for an sdist archive target" build-flag warning must reach stderr
    before the archive's own malformed-``pyproject.toml`` metadata
    warning that ``_resolve_project_generation_settings()`` triggers
    while resolving its metadata -- previously the reverse, since that
    resolution ran before the CLI handler ever settled the build options
    for this (file) target (``build_options_from_args()`` was called
    with ``subject=None`` for a file target, deferring entirely to
    ``generate_project_sbom()``, which only settles later still).
    """
    sdist_path = _make_sdist_with_malformed_member_pyproject(tmp_path)
    output = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "project",
            str(sdist_path),
            "--build-timeout",
            "5",
            "-o",
            str(output),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert __main__.main() == 0

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert _first_index(messages, _BUILD_WARNING_SUBSTRING) < _first_index(
        messages, _SDIST_MEMBER_METADATA_WARNING_SUBSTRING
    )

    stderr_lines = capsys.readouterr().err.splitlines()
    assert _first_index(stderr_lines, _BUILD_WARNING_SUBSTRING) < _first_index(
        stderr_lines, _SDIST_MEMBER_METADATA_WARNING_SUBSTRING
    )


def test_cli_generate_sdist_build_flag_warning_precedes_metadata_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom generate`` on an sdist archive target (the non-fast-path
    branch, since ``target_path.is_dir()`` is ``False`` for a file): the
    build-flag warning must reach stderr before the metadata warning
    ``_resolve_common_options()``'s own sibling-``pyproject.toml`` peek
    triggers -- previously the reverse, since that peek ran before
    ``generate()`` (via ``generate_project_sbom()``) ever settled the
    build options for this target.
    """
    sdist_path = _make_sdist_with_malformed_sibling_pyproject(tmp_path)
    output = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "generate",
            str(sdist_path),
            "--build-timeout",
            "5",
            "-o",
            str(output),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert __main__.main() == 0

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert _first_index(messages, _BUILD_WARNING_SUBSTRING) < _first_index(
        messages, _SIBLING_CONFIG_METADATA_WARNING_SUBSTRING
    )

    stderr_lines = capsys.readouterr().err.splitlines()
    assert _first_index(stderr_lines, _BUILD_WARNING_SUBSTRING) < _first_index(
        stderr_lines, _SIBLING_CONFIG_METADATA_WARNING_SUBSTRING
    )


def _make_wheel_with_malformed_sibling_pyproject(tmp_path: Path) -> Path:
    """A minimal wheel next to a malformed sibling ``pyproject.toml`` --
    ``loom generate``'s non-fast-path peek reads that sibling and logs one
    ``WARNING:`` while resolving ``[tool.pitloom]`` config."""
    wheel_dir = tmp_path / "wheeldir"
    wheel_dir.mkdir()
    (wheel_dir / "pyproject.toml").write_text('[project\nname = "broken"\n')
    wheel_path = wheel_dir / "demo-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("demo/__init__.py", "x = 1\n")
        zf.writestr(
            "demo-1.0.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n",
        )
        zf.writestr(
            "demo-1.0.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
            "Tag: py3-none-any\n",
        )
        zf.writestr("demo-1.0.0.dist-info/RECORD", "")
    return wheel_path


def test_cli_generate_wheel_build_flag_warning_precedes_metadata_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom generate`` on a non-project target (a wheel): the "no effect
    for this target" build-flag warning must reach stderr before the
    metadata warning ``_resolve_common_options()``'s sibling-config peek
    logs, and exactly once."""
    wheel_path = _make_wheel_with_malformed_sibling_pyproject(tmp_path)
    output = tmp_path / "out.spdx3.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "generate",
            str(wheel_path),
            "--build-timeout",
            "5",
            "-o",
            str(output),
        ],
    )

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        assert __main__.main() == 0

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert sum(_NON_PROJECT_BUILD_WARNING_SUBSTRING in m for m in messages) == 1
    assert _first_index(messages, _NON_PROJECT_BUILD_WARNING_SUBSTRING) < _first_index(
        messages, _SIBLING_CONFIG_METADATA_WARNING_SUBSTRING
    )

    stderr_lines = capsys.readouterr().err.splitlines()
    assert _first_index(
        stderr_lines, _NON_PROJECT_BUILD_WARNING_SUBSTRING
    ) < _first_index(stderr_lines, _SIBLING_CONFIG_METADATA_WARNING_SUBSTRING)


def test_cli_embed_wheel_project_dir_build_flag_warning_precedes_config_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom embed-wheel --project-dir``: the stray ``--build-timeout``
    warning is settled before the handler reads the project's
    ``[tool.pitloom]`` config -- so it still reaches stderr, first, when
    that read fails the command."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n\n'
        '[tool.pitloom]\npretty = "yes"\n',
        encoding="utf-8",
    )
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "loom",
            "embed-wheel",
            str(wheel),
            "--project-dir",
            str(project),
            "--build-timeout",
            "5",
        ],
    )

    assert __main__.main() == 1

    stderr_lines = capsys.readouterr().err.splitlines()
    assert _first_index(stderr_lines, _BUILD_WARNING_SUBSTRING) < _first_index(
        stderr_lines, "ERROR: "
    )
