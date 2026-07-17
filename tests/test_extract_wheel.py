# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.extract.wheel.read_wheel()."""

import zipfile
from pathlib import Path

from pitloom.extract.wheel import read_wheel


def _make_wheel(tmp_path: Path, name: str, metadata_body: str | None) -> Path:
    """Build a minimal .whl containing just a METADATA file (or none)."""
    wheel_path = tmp_path / f"{name}-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        if metadata_body is not None:
            zf.writestr(f"{name}-1.0.0.dist-info/METADATA", metadata_body)
        zf.writestr(f"{name}/__init__.py", "")
    return wheel_path


def test_read_wheel_provenance_only_for_present_fields(tmp_path: Path) -> None:
    """Provenance is recorded only for fields METADATA actually supplies --
    Summary/Requires-Python/License/Requires-Dist are absent here, so only
    name/version get a provenance entry."""
    metadata_body = "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0.0\n"
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.name == "pkg"
    assert metadata.version == "1.0.0"
    assert metadata.license_name is None
    assert metadata.dependencies == []
    assert set(metadata.provenance) == {"name", "version"}
    assert "wheel METADATA" in metadata.provenance["name"]


def test_read_wheel_full_provenance(tmp_path: Path) -> None:
    """All four provenance-tracked fields (name, version, license,
    dependencies) are recorded when METADATA supplies them."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "License-Expression: MIT\n"
        "Requires-Dist: requests>=2.0\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.license_name == "MIT"
    assert metadata.dependencies == ["requests>=2.0"]
    assert set(metadata.provenance) == {"name", "version", "license", "dependencies"}


def test_read_wheel_no_metadata_file_has_no_provenance(tmp_path: Path) -> None:
    """A wheel with no .dist-info/METADATA at all must not claim any field
    was sourced from it -- name stays the "unknown" default with an empty
    provenance dict, not a false "Source: wheel METADATA" claim."""
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body=None)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.name == "unknown"
    assert not metadata.provenance
