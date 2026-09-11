# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.project.read_project() and
resolve_project_with_lockfile()."""

from __future__ import annotations

import io
import logging
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.extract._sdist import read_sdist
from pitloom.extract.project import (
    read_project,
    resolve_project_with_lockfile,
)


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


def test_read_project_falls_back_past_build_system_only_pyproject(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: a ``pyproject.toml`` declaring only ``[build-system]``
    (a custom/legacy build backend, e.g. real-world PyYAML 6.0.3's
    ``_pyyaml_pep517`` wrapper) has no ``[project]`` table and no
    ``[tool.poetry]`` fallback -- ``read_pyproject()`` alone resolves to
    an empty, nameless stub. When ``setup.cfg``/``setup.py`` hold the
    project's real metadata, ``read_project()`` must fall back to
    :func:`~pitloom.extract._setuptools.read_setuptools` instead of
    silently returning that empty stub -- logging a ``WARNING:``, not
    deviating silently."""
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
    """Regression: falling back to ``read_setuptools()`` for metadata
    (previous test) must not also discard a real ``[tool.pitloom]``
    section already resolved from ``pyproject.toml`` -- ``[tool.pitloom]``
    always lives there, never in ``setup.cfg``/``setup.py``, regardless
    of which source supplies the project metadata itself."""
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
    """Regression: the pyproject.toml-with-no-usable-metadata ->
    setup.cfg/setup.py fallback branch (previous two tests) must still
    get `apply_locked_dependencies()`'s cascade applied to the
    setuptools-resolved metadata, not skip it or apply it to a stale
    pre-fallback object -- this is the one of `read_project()`'s three
    directory-based resolution paths that had no dedicated coverage for
    the lock cascade."""
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
    """Regression: `_try_read_poetry()` can resolve `poetry.lock`'s data
    onto a name-less `ProjectMetadata` when `[tool.poetry]` itself fails
    to parse (its own "skipping Poetry gap-fill, but still applying
    poetry.lock's resolved dependencies" path). That empty name then
    triggers this same setup.cfg/setup.py fallback branch, which used to
    replace `metadata` wholesale via `read_setuptools()` -- silently
    discarding poetry.lock's already-resolved `locked_dependencies` and
    letting a lower-priority format (here `pdm.lock`) win the cascade in
    its place with no "supersedes" note. The prior result must survive
    the metadata swap."""
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
    """Regression: `include_locked_dependencies=False` used to only gate
    the pylock.toml/uv.lock/pdm.lock cascade -- `poetry.lock` was still
    read and attached to `locked_dependencies` regardless, since
    `read_pyproject()` never forwarded the flag to `_try_read_poetry()`.
    One flag must gate every lock source, `poetry.lock` included."""
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
        "pitloom.extract.project.read_sdist", wraps=read_sdist
    ) as mock_read_sdist:
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            sdist_path, None
        )

    assert metadata.name == "demo"
    mock_read_sdist.assert_called_once()


def test_resolve_project_with_lockfile_sdist_explicit_flag_warns_and_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: an explicit use_lockfile passed for an sdist archive has
    no effect (no lock/pin cascade support for archives yet) -- silently
    discarding it instead of warning would hide the no-op from the user."""
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
    assert "has no effect for an sdist archive target" in caplog.text


def test_resolve_project_with_lockfile_does_not_duplicate_poetry_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Regression: the peek-then-reread's `quiet` flag must reach every
    warning reachable during [tool.poetry] gap-fill metadata parsing, not
    just the PEP 621/pyproject-metadata path -- a git/path/url-sourced
    Poetry dependency (which cannot be represented as a PEP 508 specifier)
    logs its own WARNING: from a different module
    (pitloom.extract._poetry), reached via a different call chain than the
    PEP 639 case above."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry]\nname = "pkg"\nversion = "1.0.0"\n'
        "[tool.poetry.dependencies]\n"
        'python = "^3.10"\n'
        'mylib = {git = "https://example.com/mylib.git"}\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        metadata, _pitloom_config, _config_path = resolve_project_with_lockfile(
            tmp_path, None
        )

    assert metadata.name == "pkg"
    assert caplog.text.count("Skipping Poetry dependency") == 1


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
    own WARNING: from pitloom.extract._setuptools_py, reached only when
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
