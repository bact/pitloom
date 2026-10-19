# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

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
from pitloom.extract.project.hatchling import metadata_from_hatchling  # noqa: E402
from pitloom.extract.project.pyproject import read_pyproject  # noqa: E402

from ..conftest import (
    CONFLICT_PYPROJECT,
    SYNTHETIC_NONCANONICAL_PYPROJECT,
    write_pyproject,
)


def test_metadata_from_hatchling_matches_read_pyproject_for_uuid() -> None:
    """Hook and CLI paths yield the same doc UUID for a static project.

    Hatchling's resolved metadata does not change the document identity of a
    project whose metadata is fully static (as Pitloom's own is).
    """
    root = Path(__file__).resolve().parent.parent.parent.parent
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
    """CLI and hook paths agree even when the name/deps are non-canonical.

    A project name with an uppercase letter, underscore and dot
    (``My_Package.Extra``) and dependency names with an underscore
    (``typing_extensions``) and a dot (``zope.interface``) must not give the
    same project two document UUIDs, whichever path generated the SBOM
    (Hatchling's own PEP 503 normalisation must not leak into one path).
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
    """CLI and hook paths agree on G2 when the declared license and an
    independently-detected LICENSE file disagree.

    Both paths resolve the same ``license_concluded`` value:
    :func:`~pitloom.extract.hatchling.metadata_from_hatchling` runs the
    independent directory scan that
    :func:`~pitloom.extract.project.pyproject.read_pyproject` runs.
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
