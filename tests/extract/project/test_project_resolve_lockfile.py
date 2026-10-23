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
    """With no explicit flag (use_lockfile=None) and the cascade on by default,
    resolve_project_with_lockfile() peeks the config and re-reads for real;
    a WARNING: the content triggers (here, the PEP 639 transitional
    license/classifier conflict) is emitted once, not once per read."""
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
    """An sdist target is not peeked-then-reread: read_project() ignores
    include_locked_dependencies for sdist archives (always a default
    PitloomConfig()), so a peek never sees the cascade "off" and a second
    read would re-extract the archive for an identical result."""
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
    """An explicit use_lockfile for an sdist archive has no effect (an archive
    has no lock/pin cascade); it is warned about, not silently discarded. The
    generator settles it once; the resolver stays silent."""
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
    """The peek-then-reread's `quiet` flag reaches every warning reachable during
    [tool.poetry] gap-fill metadata parsing, not just the PEP 621 path: a
    path-sourced Poetry dependency logs its own WARNING: from a different
    module than the PEP 639 case above."""
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
    """A malformed [tool.poetry] section (missing name) logs its own "metadata
    could not be parsed... still applying poetry.lock's resolved dependencies"
    WARNING: from _try_read_poetry(), reachable only when
    locked_dependencies is not None. The peek always calls with
    include_locked_dependencies=False and never reaches it, so the warning is
    not gated by `quiet` (that would drop it on the default path, where the
    only real call is the quiet=True reread)."""
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
    """Same dedup for the setup.py extraction path: an unresolvable kwarg value
    (e.g. `version=get_version()`) logs its own WARNING: from
    pitloom.extract.project.setuptools_py, reached only with no
    pyproject.toml at all."""
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
    """The "no usable [project] table -- falling back to setup.cfg/setup.py"
    WARNING: (read_project()'s own, gated on its own `quiet` check) is
    emitted once when the peek-then-reread goes through this fallback
    branch."""
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
    """prepare_dynamic_version() (called unconditionally by read_pyproject())
    forwards `quiet` to resolve_flit_dynamic_metadata(): a Flit-backend
    project with an unresolvable `dynamic = ["version"]` logs its "Flit
    dynamic metadata resolution failed" WARNING: once on the
    peek-then-reread."""
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
