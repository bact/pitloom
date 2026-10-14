# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.resolve_project_with_lockfile(): each
lock-file and fallback warning is logged once, an archive read once.

See also: tests/extract/project/test_project.py (read_project()).
"""

from __future__ import annotations

import io
import logging
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.extract.project.sdist import read_sdist


def test_resolve_project_with_lockfile_default_does_not_duplicate_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: with no explicit flag (use_lockfile=None) and the
    cascade on by default, resolve_project_with_lockfile() peeks the
    config and then re-reads for real -- both reads parse the same
    pyproject.toml, so a WARNING: its content triggers (here, the PEP 639
    transitional license/classifier conflict) must be emitted exactly
    once, not once per internal read."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n'
        'license = "MIT"\n'
        'classifiers = ["License :: OSI Approved :: MIT License"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.name == "pkg"
    assert caplog.text.count("PEP 639 transitional state") == 1


def test_resolve_project_with_lockfile_explicit_flag_reads_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An explicit use_lockfile bool skips the peek entirely -- only ever one
    read, so no dedup logic is even reachable."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n'
        'license = "MIT"\n'
        'classifiers = ["License :: OSI Approved :: MIT License"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        resolve_project_with_lockfile(tmp_path, False)

    assert caplog.text.count("PEP 639 transitional state") == 1


def test_resolve_project_with_lockfile_sdist_reads_archive_once(
    tmp_path: Path,
) -> None:
    """Regression: an sdist target must not be peeked-then-reread -- unlike
    a directory target, read_project() ignores include_locked_dependencies
    entirely for sdist archives (always returns a default PitloomConfig()),
    so a peek can never see the cascade as "off" and a second read would
    always run, re-extracting the archive for an identical result."""
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    pkg_info = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="demo-1.0.0/PKG-INFO")
        ti.size = len(pkg_info)
        tf.addfile(ti, io.BytesIO(pkg_info))

    with patch(
        "pitloom.extract.project.reader.read_sdist", wraps=read_sdist
    ) as mock_read_sdist:
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            sdist_path, None
        )

    assert metadata.name == "demo"
    mock_read_sdist.assert_called_once()


def test_sdist_explicit_use_lockfile_warns_once_and_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: an explicit use_lockfile passed for an sdist archive has
    no effect (no lock/pin cascade support for archives yet) -- silently
    discarding it instead of warning would hide the no-op from the user.
    The generator settles it once; the resolver itself stays silent."""
    sdist_path = tmp_path / "demo-1.0.0.tar.gz"
    pkg_info = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="demo-1.0.0/PKG-INFO")
        ti.size = len(pkg_info)
        tf.addfile(ti, io.BytesIO(pkg_info))

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            sdist_path, False
        )
    assert metadata.name == "demo"
    assert "has no effect" not in caplog.text

    with caplog.at_level(logging.WARNING):
        generate_project_sbom(sdist_path, use_lockfile=False)
    assert caplog.text.count("has no effect for an sdist archive target") == 1


def test_resolve_project_with_lockfile_does_not_duplicate_poetry_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: the peek-then-reread's `quiet` flag must reach every
    warning reachable during [tool.poetry] gap-fill metadata parsing, not
    just the PEP 621/pyproject-metadata path -- a path-sourced Poetry
    dependency logs its own WARNING: from a different module, reached via
    a different call chain than the PEP 639 case above."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n'
        "[tool.poetry.dependencies]\n"
        'python = "^3.10"\n'
        'mylib = {path = "../mylib"}\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.name == "pkg"
    assert caplog.text.count("Skipping dependency") == 1


def test_resolve_project_with_lockfile_poetry_parse_failure_warning_not_lost(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a malformed [tool.poetry] section (missing name) logs its
    own "metadata could not be parsed... still applying poetry.lock's
    resolved dependencies" WARNING: from _try_read_poetry() -- reachable only
    when locked_dependencies is not None (include_locked_dependencies=True).
    resolve_project_with_lockfile()'s peek always calls with
    include_locked_dependencies=False, so the peek itself can never reach
    this branch; the warning must therefore NOT be gated by `quiet` (unlike
    this function's other, genuinely peek-reachable warnings) -- gating it
    would silently drop it for the default/no-flag path, where the only
    real (include_locked_dependencies=True) call is the quiet=True reread."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
        '[metadata]\nlock-version = "2.1"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.locked_dependencies == ["requests==2.31.0"]
    assert caplog.text.count("metadata could not be parsed") == 1


def test_resolve_project_with_lockfile_does_not_duplicate_setuptools_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: same dedup requirement for the setup.py extraction path
    -- an unresolvable kwarg value (e.g. `version=get_version()`) logs its
    own WARNING: from pitloom.extract.project.setuptools_py, reached only when
    there's no pyproject.toml at all (a third, independent call chain from
    the two above)."""
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\n"
        "def get_version(): return '1.0.0'\n"
        "setup(name='pkg', version=get_version())\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.name == "pkg"
    assert caplog.text.count("statically resolvable literal") == 1


def test_resolve_project_with_lockfile_does_not_duplicate_fallback_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: the "no usable [project] table -- falling back to
    setup.cfg/setup.py" WARNING: (read_project()'s own, distinct from the
    pyproject-parsing and poetry/setuptools cases above) is reached via a
    third code path inside read_project() itself, gated on its own `quiet`
    check -- must dedup exactly like the others when the peek-then-reread
    goes through this specific fallback branch."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.name == "real-pkg"
    assert caplog.text.count("no usable [project] table") == 1


def test_resolve_project_with_lockfile_does_not_duplicate_flit_dynamic_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: prepare_dynamic_version() (called unconditionally by
    read_pyproject(), regardless of include_locked_dependencies) didn't
    forward `quiet` to resolve_flit_dynamic_metadata() -- a Flit-backend
    project with an unresolvable `dynamic = ["version"]` would log its
    "Flit dynamic metadata resolution failed" WARNING: twice on the
    peek-then-reread, the fifth independent call chain (after PEP 639,
    Poetry, setup.py, and the pyproject-fallback cases above) reaching a
    warning-emitting parse path."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["flit_core>=3.9"]\n'
        'build-backend = "flit_core.buildapi"\n\n'
        '[project]\nname = "nonexistent_pkg"\ndynamic = ["version"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.version is None
    assert caplog.text.count("Flit dynamic metadata resolution failed") == 1
