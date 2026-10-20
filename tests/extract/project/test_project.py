# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.read_project().

See also: tests/extract/project/test_project_resolve_lockfile.py
(resolve_project_with_lockfile()).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project import read_project


def test_read_project_uses_pyproject_when_present(tmp_path: Path) -> None:
    """pyproject.toml wins when present, regardless of setup.cfg/setup.py."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        """
[project]
name = "pyproject-pkg"
version = "1.0.0"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = setup-cfg-pkg\nversion = 2.0.0\n", encoding="utf-8"
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "pyproject-pkg"
    assert config_path == pyproject_path


def test_read_project_resolves_uv_build_backend_via_generic_pep621(
    tmp_path: Path,
) -> None:
    """``uv_build`` declares ``build-backend = "uv_build"`` but needs no
    dedicated extractor: ``read_project()`` never branches on build-backend
    for metadata, only :mod:`pitloom.core._models_wheel`'s file-discovery
    dispatch does (see ``non-hatchling-file-discovery.md``)."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "[build-system]\n"
        'requires = ["uv_build>=0.9,<0.10"]\n'
        'build-backend = "uv_build"\n\n'
        "[project]\n"
        'name = "pkg"\n'
        'version = "1.2.3"\n'
        'dependencies = ["requests>=2"]\n'
        'license = "MIT"\n'
        'authors = [{name = "A", email = "a@example.com"}]\n',
        encoding="utf-8",
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "pkg"
    assert metadata.version == "1.2.3"
    assert metadata.dependencies == ["requests>=2"]
    assert metadata.license_name == "MIT"
    assert metadata.authors == [{"name": "A", "email": "a@example.com"}]
    assert config_path == pyproject_path


def test_read_project_falls_back_past_build_system_only_pyproject(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``pyproject.toml`` declaring only ``[build-system]`` (a custom build
    backend, e.g. PyYAML 6.0.3's ``_pyyaml_pep517``) has no ``[project]`` table
    and no ``[tool.poetry]`` fallback, so ``read_pyproject()`` alone gives an
    empty, nameless stub. When ``setup.cfg``/``setup.py`` hold the real
    metadata, ``read_project()`` falls back to
    :func:`~pitloom.extract.project.setuptools.read_setuptools` with a
    ``WARNING:``."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert metadata.version == "1.2.3"
    assert config_path == setup_cfg
    assert "no usable [project] table" in caplog.text


def test_read_project_fallback_preserves_pyproject_pitloom_config(
    tmp_path: Path,
) -> None:
    """Falling back to ``read_setuptools()`` for metadata (previous test) keeps
    the ``[tool.pitloom]`` section resolved from ``pyproject.toml``, where it
    always lives."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n\n'
        "[tool.pitloom]\n"
        'sbom-basename = "custom-name"\n',
        encoding="utf-8",
    )
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )

    metadata, pitloom_config, _config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert pitloom_config.sbom_basename == "custom-name"


def test_read_project_fallback_still_applies_lock_cascade(tmp_path: Path) -> None:
    """The pyproject.toml-with-no-usable-metadata -> setup.cfg/setup.py fallback
    branch (previous two tests) applies `apply_locked_dependencies()`'s
    cascade to the setuptools-resolved metadata: the lock-cascade coverage of
    `read_project()`'s third directory-based resolution path."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )
    (tmp_path / "pylock.toml").write_text(
        'lock-version = "1.0"\ncreated-by = "test"\n'
        '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
        encoding="utf-8",
    )

    metadata, _pitloom_config, _config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert metadata.locked_dependencies == ["requests==2.31.0"]
    assert metadata.provenance["locked_dependencies"] == (
        "Source: pylock.toml | Method: resolved_lockfile"
    )


def test_read_project_fallback_preserves_already_resolved_poetry_lock(
    tmp_path: Path,
) -> None:
    """`_try_read_poetry()` can resolve `poetry.lock`'s data onto a name-less
    `ProjectMetadata` when `[tool.poetry]` fails to parse ("skipping Poetry
    gap-fill, but still applying poetry.lock's resolved dependencies"). The
    empty name triggers the setup.cfg/setup.py fallback, which keeps
    poetry.lock's `locked_dependencies` across the metadata swap (a
    lower-priority `pdm.lock` does not win)."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
        '[metadata]\nlock-version = "2.1"\n',
        encoding="utf-8",
    )
    (tmp_path / "setup.cfg").write_text(
        "[metadata]\nname = real-pkg\nversion = 1.2.3\n", encoding="utf-8"
    )
    (tmp_path / "pdm.lock").write_text(
        '[[package]]\nname = "httpx"\nversion = "0.28.1"\ngroups = ["default"]\n'
        '[metadata]\nlock_version = "4.5.1"\n',
        encoding="utf-8",
    )

    metadata, _pitloom_config, _config_path = read_project(tmp_path)

    assert metadata.name == "real-pkg"
    assert metadata.locked_dependencies == ["requests==2.31.0"]
    assert metadata.provenance["locked_dependencies"] == (
        "Source: poetry.lock | Method: resolved_lockfile"
    )


def test_read_project_build_system_only_pyproject_no_setuptools_fallback(
    tmp_path: Path,
) -> None:
    """When a ``[build-system]``-only ``pyproject.toml`` has no
    ``setup.cfg``/``setup.py`` to fall back to either, ``read_project()``
    still returns ``read_pyproject()``'s (nameless) result -- no
    FileNotFoundError, matching prior behavior for this narrower case."""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "custom_pep517_wrapper"\n',
        encoding="utf-8",
    )

    metadata, _, config_path = read_project(tmp_path)

    assert not metadata.name
    assert config_path == pyproject_path


def test_read_project_falls_back_to_setup_cfg(tmp_path: Path) -> None:
    """setup.cfg is used when no pyproject.toml exists."""
    setup_cfg = tmp_path / "setup.cfg"
    setup_cfg.write_text(
        "[metadata]\nname = setup-cfg-pkg\nversion = 2.0.0\n", encoding="utf-8"
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "setup-cfg-pkg"
    assert config_path == setup_cfg


def test_read_project_falls_back_to_setup_py(tmp_path: Path) -> None:
    """setup.py is used when no pyproject.toml or setup.cfg exists."""
    setup_py = tmp_path / "setup.py"
    setup_py.write_text(
        "from setuptools import setup\nsetup(name='setup-py-pkg', version='3.0')\n",
        encoding="utf-8",
    )

    metadata, _, config_path = read_project(tmp_path)

    assert metadata.name == "setup-py-pkg"
    assert config_path == setup_py


def test_read_project_no_source_raises(tmp_path: Path) -> None:
    """Raises FileNotFoundError when no metadata source exists at all."""
    with pytest.raises(FileNotFoundError):
        read_project(tmp_path)


def test_read_project_malformed_pitloom_config_raises(tmp_path: Path) -> None:
    """A malformed [tool.pitloom] section propagates as ValueError, not
    silently discarded or falling back to a different source."""
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "x"

[tool.pitloom]
creator-name = 123
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        read_project(tmp_path)


def test_read_project_include_locked_dependencies_false_skips_cascade(
    tmp_path: Path,
) -> None:
    """`include_locked_dependencies=False` (used by build-stage/config-only
    callers like `embed-wheel` and the shared CLI options helper) must
    skip the lock/pin cascade entirely, not just discard its result --
    a sibling `pylock.toml` is present but must never reach
    `locked_dependencies`."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "pylock.toml").write_text(
        'lock-version = "1.0"\ncreated-by = "test"\n'
        '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
        encoding="utf-8",
    )

    metadata, _pitloom_config, _config_path = read_project(
        tmp_path, include_locked_dependencies=False
    )

    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance

    normal_metadata, _, _ = read_project(tmp_path)
    assert normal_metadata.locked_dependencies == ["requests==2.31.0"]


def test_read_project_include_locked_dependencies_false_also_skips_poetry_lock(
    tmp_path: Path,
) -> None:
    """`include_locked_dependencies=False` gates every lock source, `poetry.lock`
    included (`read_pyproject()` forwards the flag to `_try_read_poetry()`)."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
        '[metadata]\nlock-version = "2.1"\n',
        encoding="utf-8",
    )

    metadata, _pitloom_config, _config_path = read_project(
        tmp_path, include_locked_dependencies=False
    )

    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance

    normal_metadata, _, _ = read_project(tmp_path)
    assert normal_metadata.locked_dependencies == ["requests==2.31.0"]


@pytest.mark.parametrize(
    ("lock_file", "content"),
    [
        (
            "poetry.lock",
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n'
            '[metadata]\nlock-version = "2.1"\n',
        ),
        (
            "pylock.toml",
            'lock-version = "1.0"\ncreated-by = "test"\n'
            '[[packages]]\nname = "requests"\nversion = "2.31.0"\n',
        ),
        (
            "uv.lock",
            'version = 1\nrevision = 1\nrequires-python = ">=3.10"\n'
            '[[package]]\nname = "pkg"\nversion = "1.0.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "requests" }]\n\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        ),
        (
            "pdm.lock",
            '[metadata]\nlock_version = "4.5.1"\n'
            '[[package]]\nname = "requests"\nversion = "2.31.0"\n'
            'groups = ["default"]\n',
        ),
        (
            "Pipfile.lock",
            '{"_meta": {"pipfile-spec": 6}, '
            '"default": {"requests": {"version": "==2.31.0"}}}',
        ),
        (
            "requirements.txt",
            "requests==2.31.0\n",
        ),
    ],
)
def test_read_project_include_locked_dependencies_false_skips_all_lock_formats(
    tmp_path: Path, lock_file: str, content: str
) -> None:
    """`include_locked_dependencies=False` must skip every supported lock format."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "pkg"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / lock_file).write_text(content, encoding="utf-8")

    metadata, _pitloom_config, _config_path = read_project(
        tmp_path, include_locked_dependencies=False
    )

    assert metadata.locked_dependencies == []
    assert "locked_dependencies" not in metadata.provenance

    # Companion assertion: with include_locked_dependencies enabled (the default),
    # the lock file is discovered and resolved -- guarding against a vacuous pass.
    normal_metadata, _, _ = read_project(tmp_path)
    assert normal_metadata.locked_dependencies == ["requests==2.31.0"]
