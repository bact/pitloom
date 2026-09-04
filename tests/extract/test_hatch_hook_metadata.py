# ruff: noqa: F403, F405
from __future__ import annotations

import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import hatchling.metadata.core as hatchling_metadata_core  # noqa: E402
import pytest
from hatchling.plugin.manager import PluginManager  # noqa: E402

from pitloom.core.models import compute_doc_uuid  # noqa: E402
from pitloom.extract._pyproject import read_pyproject  # noqa: E402
from pitloom.extract.hatchling import (  # noqa: E402
    _resolve_hatchling_license_files,
    metadata_from_hatchling,
)
from pitloom.plugins.hatch import (  # noqa: E402
    _check_hatchling_sbom_support,
)

from .conftest import (
    CONFLICT_PYPROJECT,
    MINIMAL_PYPROJECT,
    MISSING_LICENSE_FILE_PYPROJECT,
    MISSING_README_PYPROJECT,
    POETRY_GAP_FILL_PYPROJECT,
    SYNTHETIC_NONCANONICAL_PYPROJECT,
    _fake_hatch_metadata,
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


def test_metadata_from_hatchling_no_license_files() -> None:
    """Absent ``[project.license-files]`` must resolve to an empty list, not
    ``None`` or a missing field."""
    hatch_meta = _fake_hatch_metadata(core={"license_expression": "MIT"})
    metadata = metadata_from_hatchling(hatch_meta, Path("."))
    assert metadata.license_files == []
    assert "license_files" not in metadata.provenance


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


def test_metadata_from_hatchling_matches_read_pyproject_for_uuid() -> None:
    """Hook and CLI paths must yield the same doc UUID for a static project.

    Regression guard: switching the hook to Hatchling's resolved metadata
    must not change the document identity of a project whose metadata is
    fully static (as Pitloom's own is).
    """
    root = Path(__file__).resolve().parent.parent.parent
    cli_meta, _ = read_pyproject(root / "pyproject.toml")
    hatch_pm = hatchling_metadata_core.ProjectMetadata(str(root), PluginManager())
    hook_meta = metadata_from_hatchling(hatch_pm, root)

    assert hook_meta.name == cli_meta.name
    assert hook_meta.version == cli_meta.version
    assert hook_meta.dependencies == cli_meta.dependencies
    assert compute_doc_uuid(
        hook_meta.name, hook_meta.version or "x", hook_meta.dependencies
    ) == compute_doc_uuid(cli_meta.name, cli_meta.version or "x", cli_meta.dependencies)


def test_metadata_from_hatchling_matches_read_pyproject_for_noncanonical_name() -> None:
    """CLI and hook paths must agree even when the name/deps are non-canonical.

    Regression guard for the gap the earlier, name-only ``raw_name`` fix and
    the marker-only ``_normalize_dependencies`` helper both missed: a project
    name with an uppercase letter, underscore, and dot (``My_Package.Extra``)
    and dependency names with an underscore (``typing_extensions``) and a dot
    (``zope.interface``). Before this fix, Hatchling's own PEP 503
    normalisation made the hook report ``name == "my-package-extra"`` and
    canonicalised dependency names, while the CLI path left both untouched,
    giving the same project two different deterministic document UUIDs
    depending on which path generated the SBOM.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, SYNTHETIC_NONCANONICAL_PYPROJECT)

        cli_meta, _ = read_pyproject(tmp_path / "pyproject.toml")
        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        hook_meta = metadata_from_hatchling(hatch_pm, tmp_path)

        assert cli_meta.name == "My_Package.Extra"
        assert hook_meta.name == "My_Package.Extra"
        assert hook_meta.name == cli_meta.name

        expected_deps = ["typing-extensions>=4.0", "zope-interface>=5.0"]
        assert cli_meta.dependencies == expected_deps
        assert hook_meta.dependencies == expected_deps

        assert compute_doc_uuid(
            hook_meta.name, hook_meta.version or "x", hook_meta.dependencies
        ) == compute_doc_uuid(
            cli_meta.name, cli_meta.version or "x", cli_meta.dependencies
        )


def test_metadata_from_hatchling_matches_read_pyproject_for_license_conflict() -> None:
    """CLI and hook paths must agree on G2 when the declared license and an
    independently-detected LICENSE file disagree.

    Regression guard for the systemic gap ``resolve_license_concluded()``
    exists to close: the Hatchling build-hook path
    (:func:`~pitloom.extract.hatchling.metadata_from_hatchling`) originally
    called :func:`~pitloom.extract._license.detect_license_for_project`
    directly and never ran the independent directory scan at all, so G2
    only ever fired via the CLI's
    :func:`~pitloom.extract._pyproject.read_pyproject`. Both paths must now
    resolve the same ``license_concluded`` value for the same project.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, CONFLICT_PYPROJECT)
        (tmp_path / "LICENSE").write_text(
            "Apache License\nVersion 2.0" + "x" * 200, encoding="utf-8"
        )

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="Apache-2.0",
        ):
            cli_meta, _ = read_pyproject(tmp_path / "pyproject.toml")
            hatch_pm = hatchling_metadata_core.ProjectMetadata(
                str(tmp_path), PluginManager()
            )
            hook_meta = metadata_from_hatchling(hatch_pm, tmp_path)

        assert cli_meta.license_name == "MIT"
        assert hook_meta.license_name == "MIT"
        assert cli_meta.license_concluded == "Apache-2.0"
        assert hook_meta.license_concluded == cli_meta.license_concluded


def test_metadata_from_hatchling_matches_read_pyproject_for_license_agreement() -> None:
    """Same as above, but declared and detected agree: both paths must
    still populate ``license_concluded`` (equal to the declared value),
    not just leave it unset -- G2 records both sides regardless of
    agreement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, CONFLICT_PYPROJECT)
        (tmp_path / "LICENSE").write_text(
            "MIT License\n\nPermission" + "x" * 200, encoding="utf-8"
        )

        with patch(
            "pitloom.extract._license.detect_license_from_text",
            return_value="MIT",
        ):
            cli_meta, _ = read_pyproject(tmp_path / "pyproject.toml")
            hatch_pm = hatchling_metadata_core.ProjectMetadata(
                str(tmp_path), PluginManager()
            )
            hook_meta = metadata_from_hatchling(hatch_pm, tmp_path)

        assert cli_meta.license_concluded == "MIT"
        assert hook_meta.license_concluded == "MIT"


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


def test_metadata_from_hatchling_does_not_leak_poetry_lock_dependencies() -> None:
    """Regression: ``poetry.lock`` is a source-stage-only artifact (see
    ``pitloom.extract._poetry_lock``'s module docstring) -- the real wheel
    Hatchling builds never consults it, so the build hook's ``[tool.poetry]``
    gap-fill path must never populate ``locked_dependencies`` from a
    ``poetry.lock`` sitting next to a Hatchling-backed project, even though
    ``read_pyproject()`` (the CLI/source-stage path) legitimately does.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        write_pyproject(tmp_path, POETRY_GAP_FILL_PYPROJECT)
        (tmp_path / "poetry.lock").write_text(
            '[[package]]\nname = "requests"\nversion = "2.31.0"\ngroups = ["main"]\n',
            encoding="utf-8",
        )

        hatch_pm = hatchling_metadata_core.ProjectMetadata(
            str(tmp_path), PluginManager()
        )
        metadata = metadata_from_hatchling(hatch_pm, tmp_path)

        assert metadata.locked_dependencies == []
        assert "locked_dependencies" not in metadata.provenance

        # The CLI/source-stage path, by contrast, legitimately picks it up.
        cli_metadata, _config = read_pyproject(tmp_path / "pyproject.toml")
        assert cli_metadata.locked_dependencies == ["requests==2.31.0"]


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
