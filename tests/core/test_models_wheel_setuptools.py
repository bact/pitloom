# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for setuptools-backed wheel file discovery
(:mod:`pitloom.core._models_wheel_setuptools`).

See also: tests/core/test_models_wheel_files.py for the facade-level
backend-dispatch/fallback-warning tests.
"""

import logging
from pathlib import Path

import pytest

from pitloom.core._models_wheel_setuptools import discover

FIXTURES = Path(__file__).parent.parent / "fixtures" / "projects"
PACKAGES_FIND_FIXTURE = FIXTURES / "sampleproject-setuptools"
PACKAGE_DATA_FIXTURE = FIXTURES / "sampleproject-setuptools-data"


def test_discover_packages_find_where_regression() -> None:
    """Regression for the documented bug: a ``[options.packages.find]
    where = src`` layout must resolve distribution paths without the
    ``src/``/``where=`` prefix leaking in -- previously (via the
    always-Hatchling-heuristic code path) this was reported as
    ``src/sampleproject_setuptools/__init__.py`` instead of the correct
    ``sampleproject_setuptools/__init__.py``."""
    result = discover(PACKAGES_FIND_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {"sampleproject_setuptools/__init__.py"}
    assert not any(p.startswith(("src/", "where")) for p in distribution_paths)


def test_discover_resolves_absolute_physical_paths() -> None:
    """``IncludedFile.path`` must be absolute, matching Hatchling's own
    ``IncludedFile.path`` contract -- the caller reads it after
    discovery's temporary chdir has already been undone."""
    result = discover(PACKAGES_FIND_FIXTURE)

    assert result is not None
    for included_file in result:
        assert Path(included_file.path).is_absolute()
        assert Path(included_file.path).is_file()


def test_discover_package_data_and_manifest_in() -> None:
    """``package_data`` (explicit glob) and ``include_package_data`` +
    ``MANIFEST.in`` (manifest-analysis path) are both resolved -- the
    ``.py`` module, the ``package_data``-globbed ``.json``, and the
    MANIFEST.in-only ``.txt`` (not matched by the ``*.json`` glob)."""
    result = discover(PACKAGE_DATA_FIXTURE)

    assert result is not None
    distribution_paths = {f.distribution_path for f in result}
    assert distribution_paths == {
        "sampleproject_setuptools_data/__init__.py",
        "sampleproject_setuptools_data/data.json",
        "sampleproject_setuptools_data/notes.txt",
    }


def test_discover_package_data_leaves_no_egg_info_behind() -> None:
    """The manifest-analysis path (``include_package_data``) must not
    mutate the fixture directory -- ``egg_base`` redirection to a temp
    directory is what makes this a safe, read-only discovery pass."""
    before = set(PACKAGE_DATA_FIXTURE.rglob("*"))

    result = discover(PACKAGE_DATA_FIXTURE)

    assert result is not None
    after = set(PACKAGE_DATA_FIXTURE.rglob("*"))
    assert after == before, "discovery must not leave any new file/dir behind"


def test_discover_returns_none_without_static_config(tmp_path: Path) -> None:
    """A setuptools project with neither ``[tool.setuptools]`` in
    ``pyproject.toml`` nor a ``setup.cfg`` (packages only resolvable by
    executing an imperative ``setup.py``) is out of scope -- ``None``
    signals the caller to fall back, not "found zero files"."""
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text(
        'from setuptools import setup\nsetup(name="pkg", version="1.0.0")\n',
        encoding="utf-8",
    )

    assert discover(tmp_path) is None


def test_discover_returns_none_and_logs_on_introspection_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Any setuptools-introspection failure is treated the same as "no
    static config" -- ``None``, plus a logged warning with the failure
    detail (the facade logs its own generic fallback warning on top)."""
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = pkg\nversion = 1.0.0\n\n[options]\npackages = find:\n",
        encoding="utf-8",
    )

    def _broken_finalize(self: object) -> None:
        del self
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "setuptools.command.build_py.build_py.finalize_options", _broken_finalize
    )

    with caplog.at_level(logging.WARNING):
        result = discover(tmp_path)

    assert result is None
    assert "boom" in caplog.text
