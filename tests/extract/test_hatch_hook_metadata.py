# ruff: noqa: F403, F405
"""Tests for metadata_from_hatchling()'s field-mapping and edge-case
behavior.

See also: test_hatch_hook_metadata_parity.py for the CLI-vs-hook
metadata-parity tests, split out to keep this file under this repo's
file-size soft limit.
"""

from __future__ import annotations

import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import hatchling.metadata.core as hatchling_metadata_core  # noqa: E402
import pytest
from hatchling.plugin.manager import PluginManager  # noqa: E402

from pitloom.extract.hatchling import (  # noqa: E402
    _hatchling_field_declared,
    _resolve_hatchling_license_files,
    metadata_from_hatchling,
)
from pitloom.plugins.hatch import (  # noqa: E402
    _check_hatchling_sbom_support,
)

from .conftest import (
    MINIMAL_PYPROJECT,
    MISSING_LICENSE_FILE_PYPROJECT,
    MISSING_README_PYPROJECT,
    POETRY_GAP_FILL_PYPROJECT,
    _fake_hatch_metadata,
    assert_declared_empty_authors_no_copyright_text,
    write_pyproject,
)


def test_metadata_from_hatchling_maps_resolved_version() -> None:
    """The resolved (possibly dynamic) version must be used as-is."""
    hatch_meta = _fake_hatch_metadata(version="9.9.9")
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.version == "9.9.9"
    assert metadata.provenance["version"] == (
        "Source: Hatchling build backend | Field: project.version"
    )


def test_metadata_from_hatchling_maps_dependencies() -> None:
    """Resolved dependencies (including dynamic ones) must be carried over."""
    hatch_meta = _fake_hatch_metadata(core={"dependencies": ["requests>=2.0", "click"]})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.dependencies == ["requests>=2.0", "click"]
    assert metadata.provenance["dependencies"] == (
        "Source: Hatchling build backend | Field: project.dependencies"
    )


def test_metadata_from_hatchling_maps_license_files() -> None:
    """PEP 639 ``[project.license-files]`` -- resolved by Hatchling itself
    to a root-relative path list -- must be carried over verbatim."""
    hatch_meta = _fake_hatch_metadata(
        core={"license_expression": "MIT", "license_files": ["LICENSE"]}
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.license_files == ["LICENSE"]
    assert metadata.provenance["license_files"] == (
        "Source: Hatchling build backend | Field: project.license-files"
    )


def test_metadata_from_hatchling_declared_empty_authors_no_copyright_text() -> None:
    """An explicitly declared but empty ``authors`` (``authors_data`` with
    no names or emails) must still record provenance for ``authors``, but
    with no authors to derive a name from, no ``copyright_text`` is
    inferred."""
    hatch_meta = _fake_hatch_metadata(core={"authors_data": {"name": [], "email": []}})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert_declared_empty_authors_no_copyright_text(metadata)


def test_metadata_from_hatchling_empty_declared_dependencies_gets_provenance() -> None:
    """An explicitly declared but empty ``[project.dependencies]`` must
    still record provenance -- merge_project_metadata() relies on that
    presence to treat the empty list as authoritative, not absent. Guards
    _hatchling_field_declared() against regressing to a truthiness check
    (``if dependencies:``) on the resolved list."""
    hatch_meta = _fake_hatch_metadata(core={"dependencies": []})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.dependencies == []
    assert "dependencies" in metadata.provenance


def test_metadata_from_hatchling_no_license_files() -> None:
    """Absent ``[project.license-files]`` must resolve to an empty list, not
    ``None`` or a missing field."""
    hatch_meta = _fake_hatch_metadata(core={"license_expression": "MIT"})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.license_files == []
    assert "license_files" not in metadata.provenance


def test_metadata_from_hatchling_explicit_empty_requires_python_gets_provenance() -> (
    None
):
    """An explicit `requires-python = ""` (PEP 621's equivalent of Poetry's
    `python = "*"`) resolves to None but must still record provenance --
    merge_project_metadata() relies on that presence to treat the None as
    an authoritative "no constraint", not absent."""
    hatch_meta = _fake_hatch_metadata(core={"requires_python": ""})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.requires_python is None
    assert metadata.provenance["requires_python"] == (
        "Source: Hatchling build backend | Field: project.requires-python"
    )


def test_metadata_from_hatchling_no_requires_python_declared() -> None:
    """No ``[project.requires-python]`` key: resolves to None, and no
    provenance is recorded -- distinct from an explicit empty string."""
    hatch_meta = _fake_hatch_metadata()
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.requires_python is None
    assert "requires_python" not in metadata.provenance


def test_metadata_from_hatchling_no_license_files_with_real_core(
    tmp_path: Path,
) -> None:
    """Regression test against real Hatchling ``CoreMetadata`` (not the
    ``_fake_hatch_metadata`` mock): its ``license_files`` property has its
    own default-glob fallback (``LICEN[CS]E*``/``COPYING*``/``NOTICE*``/
    ``AUTHORS*``, the same convention `setuptools` and the `wheel` package
    document) when ``[project.license-files]`` is entirely absent -- a
    mock's ``_FAKE_CORE_DEFAULTS`` can't reproduce that lazy, config-driven
    behavior. A project with a root ``LICENSE`` file but no declared
    ``license-files`` key must still resolve to an empty list -- treating
    Hatchling's auto-bundling default as an explicit declaration would
    diverge from ``read_pyproject()``'s ``pyproject_metadata``-based
    extraction, which has no such default (see
    ``_resolve_hatchling_license_files``'s docstring)."""
    write_pyproject(tmp_path)
    (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")

    hatch_pm = hatchling_metadata_core.ProjectMetadata(str(tmp_path), PluginManager())
    metadata = metadata_from_hatchling(hatch_pm, tmp_path)

    assert metadata.license_files == []
    assert "license_files" not in metadata.provenance


def test_metadata_from_hatchling_declared_license_files_with_real_core(
    tmp_path: Path,
) -> None:
    """Companion to the "no license-files" real-core regression test above:
    an explicitly declared ``[project.license-files]`` must still resolve
    correctly through real Hatchling ``CoreMetadata``."""
    write_pyproject(
        tmp_path,
        MINIMAL_PYPROJECT + '\nlicense = "MIT"\nlicense-files = ["LICENSE"]\n',
    )
    (tmp_path / "LICENSE").write_text("MIT License", encoding="utf-8")

    hatch_pm = hatchling_metadata_core.ProjectMetadata(str(tmp_path), PluginManager())
    metadata = metadata_from_hatchling(hatch_pm, tmp_path)

    assert metadata.license_files == ["LICENSE"]
    assert metadata.provenance["license_files"] == (
        "Source: Hatchling build backend | Field: project.license-files"
    )


def test_resolve_hatchling_license_files_tolerates_oserror() -> None:
    """A declared ``license-files`` field whose ``core.license_files``
    property access raises ``OSError`` must degrade to an empty list, not
    propagate -- mirroring every other ``core.X`` property read in this
    module (readme, license), each of which is lazily evaluated by
    Hatchling and can raise a bare ``OSError`` for the same class of
    reason (e.g. a filesystem error resolving a referenced path)."""

    class _RaisingCore:
        config = {"license-files": ["LICENSE"]}

        @property
        def license_files(self) -> list[str]:
            raise OSError("simulated filesystem error")

    assert _resolve_hatchling_license_files(_RaisingCore()) == []


def test_hatchling_field_declared_tolerates_oserror_on_config_access() -> None:
    """A ``core.config`` property access that raises ``OSError`` must
    resolve to "not declared" (``False``), not propagate -- mirroring the
    same class of lazily-evaluated Hatchling property failure every other
    ``core.X`` read in this module tolerates."""

    class _RaisingCore:
        @property
        def config(self) -> dict[str, object]:
            raise OSError("simulated filesystem error")

    assert _hatchling_field_declared(_RaisingCore(), "dependencies") is False


def test_metadata_from_hatchling_canonicalises_dependency_markers() -> None:
    """Dependency specifiers are normalised to ``packaging`` canonical form.

    Hatchling exposes markers with source quoting (single quotes); the CLI
    path (``read_pyproject`` via ``pyproject-metadata``) stringifies through
    ``packaging.Requirement`` (double quotes).  Canonicalising here keeps the
    hook and CLI dependency lists -- and thus the deterministic document
    UUID -- identical for the same source tree.
    """
    hatch_meta = _fake_hatch_metadata(
        core={"dependencies": ["tomli>=2.0.0; python_version<'3.11'"]}
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.dependencies == ['tomli>=2.0.0; python_version < "3.11"']


def test_metadata_from_hatchling_maps_urls() -> None:
    """Resolved project URLs must be carried over verbatim."""
    hatch_meta = _fake_hatch_metadata(
        core={"urls": {"Homepage": "https://example.com"}}
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.urls == {"Homepage": "https://example.com"}


def test_metadata_from_hatchling_maps_authors() -> None:
    """``authors_data`` (name-only and email entries) must map to
    ``[{name, email?}, ...]``."""
    hatch_meta = _fake_hatch_metadata(
        core={
            "authors_data": {
                "name": ["Bob"],
                "email": ["Alice Smith <alice@example.com>", "carol@example.com"],
            }
        }
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert {"name": "Bob"} in metadata.authors
    assert {"name": "Alice Smith", "email": "alice@example.com"} in metadata.authors
    assert {"email": "carol@example.com"} in metadata.authors
    assert metadata.provenance["authors"] == (
        "Source: Hatchling build backend | Field: project.authors"
    )


def test_metadata_from_hatchling_authors_skip_blank_name_and_email() -> None:
    """A blank name-only entry is skipped (loop continues to the next
    entry); an email entry that parses to a display name but no address
    (e.g. ``"Alice <>"``) keeps only the name; an entry that parses to
    neither name nor address (e.g. an empty string) is dropped entirely."""
    hatch_meta = _fake_hatch_metadata(
        core={
            "authors_data": {
                "name": ["", "Bob"],
                "email": ["Alice <>", "", "carol@example.com"],
            }
        }
    )
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert {"name": "Bob"} in metadata.authors
    assert {"name": "Alice"} in metadata.authors
    assert {"email": "carol@example.com"} in metadata.authors
    assert len(metadata.authors) == 3


def test_metadata_from_hatchling_no_version_skips_provenance() -> None:
    """A falsy resolved version leaves ``provenance["version"]`` unset."""
    hatch_meta = _fake_hatch_metadata(version="")
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.version is None
    assert "version" not in metadata.provenance


def test_metadata_from_hatchling_tolerates_none_authors_data() -> None:
    """``authors_data=None`` must not crash ``metadata_from_hatchling``.

    Every sibling field is defended with ``or []``/``or {}``; a duck-typed
    stand-in (or a future Hatchling release) returning ``None`` for
    ``authors_data`` must degrade to "no authors" rather than raising
    ``AttributeError`` from ``None.get(...)``.
    """
    hatch_meta = _fake_hatch_metadata(core={"authors_data": None})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert not metadata.authors
    assert "authors" not in metadata.provenance


def test_metadata_from_hatchling_license_expression_used_directly() -> None:
    """A resolved SPDX license expression needs no fallback detection."""
    hatch_meta = _fake_hatch_metadata(core={"license_expression": "Apache-2.0"})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.license_name == "Apache-2.0"
    assert metadata.provenance["license"] == (
        "Source: Hatchling build backend | Field: project.license"
    )


def test_metadata_from_hatchling_license_fallback_to_project_dir() -> None:
    """When neither ``license`` nor ``license_expression`` is set, fall back
    to :func:`~pitloom.extract._license.detect_license_for_project`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        hatch_meta = _fake_hatch_metadata()
        metadata = metadata_from_hatchling(hatch_meta, tmp_path)
        assert metadata.license_name == "MIT"
        assert "LICENSE" in (metadata.provenance.get("license") or "")


def test_metadata_from_hatchling_tolerates_missing_readme_file() -> None:
    """A declared readme file that does not exist must not crash the hook.

    Hatchling's ``core.readme`` / ``core.readme_path`` are lazily evaluated
    and raise a bare ``OSError`` (not ``FileNotFoundError``) when the file is
    missing; ``metadata_from_hatchling`` must catch it and degrade to
    ``readme=None`` rather than propagate it, mirroring
    ``read_pyproject()``'s existing tolerance for the same situation.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, MISSING_README_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.readme is None


def test_metadata_from_hatchling_tolerates_missing_license_file() -> None:
    """A declared license *file* that does not exist must not crash the hook.

    Mirrors :func:`test_metadata_from_hatchling_tolerates_missing_readme_file`
    for ``core.license`` / ``core.license_expression``, which raise the same
    bare ``OSError`` for a missing ``project.license.file``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, MISSING_LICENSE_FILE_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        # Should not raise; falls through to license detection (finds nothing).
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.license_name is None


def test_metadata_from_hatchling_fills_gaps_from_poetry() -> None:
    """``[tool.poetry]`` fills authors/keywords missing from ``[project]``.

    ``read_pyproject`` (the CLI path) already recovers these fields from
    ``[tool.poetry]`` via ``_try_read_poetry()``/``_merge_with_poetry()``;
    the Hatchling hook path must do the same so a project relying on this
    gap-fill is not silently incomplete when built via the hook.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, POETRY_GAP_FILL_PYPROJECT)

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        # [project] fields are untouched.
        assert metadata.name == "testpkg"
        assert metadata.description == "Test package."
        # Fields absent from [project] are recovered from [tool.poetry].
        assert metadata.authors == [
            {"name": "Poetry Author", "email": "poetry@example.com"}
        ]
        assert metadata.keywords == ["from-poetry", "gap-fill"]


def test_check_hatchling_sbom_support_raises_when_metadata_missing() -> None:
    """If Hatchling's version can't be determined, raise a clear
    ``RuntimeError`` rather than letting a raw ``PackageNotFoundError``
    escape (e.g. a vendored copy or zipapp bundle without dist-info)."""
    with patch(
        "pitloom.plugins.hatch._pkg_version",
        side_effect=PackageNotFoundError("hatchling"),
    ):
        with pytest.raises(RuntimeError, match="version unknown"):
            _check_hatchling_sbom_support()
