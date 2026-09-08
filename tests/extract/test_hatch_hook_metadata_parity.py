# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: F403, F405
"""CLI-vs-Hatchling-build-hook metadata-parity tests -- both entry points
(``read_pyproject()`` and ``metadata_from_hatchling()``) must resolve the
same metadata for the same project, since a mismatch changes the
deterministic document UUID depending on which path generated the SBOM.
Split out of test_hatch_hook_metadata.py to keep that file under this
repo's file-size soft limit.

See also: test_hatch_hook_metadata.py for the rest of
metadata_from_hatchling()'s field-mapping and edge-case tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import hatchling.metadata.core as hatchling_metadata_core  # noqa: E402
from hatchling.plugin.manager import PluginManager  # noqa: E402

from pitloom.core.models import compute_doc_uuid  # noqa: E402
from pitloom.extract._pyproject import read_pyproject  # noqa: E402
from pitloom.extract.hatchling import metadata_from_hatchling  # noqa: E402

from .conftest import (
    CONFLICT_PYPROJECT,
    SYNTHETIC_NONCANONICAL_PYPROJECT,
    write_pyproject,
)


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
