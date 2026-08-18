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


def test_read_wheel_skips_directory_entries(tmp_path: Path) -> None:
    """Directory entries in the archive (filenames ending in "/") are
    skipped by the file-collection loop -- they must not appear in
    project_files nor be hashed."""
    wheel_path = tmp_path / "pkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr("pkg-1.0.0.dist-info/METADATA", "Name: pkg\nVersion: 1.0.0\n")
        zf.writestr("pkg/subdir/", "")  # directory entry
        zf.writestr("pkg/__init__.py", "")

    _, project_files = read_wheel(wheel_path)

    distribution_paths = {pf.distribution_path for pf in project_files}
    assert "pkg/subdir/" not in distribution_paths
    assert "pkg/__init__.py" in distribution_paths


def test_read_wheel_summary_and_requires_python(tmp_path: Path) -> None:
    """Summary populates description and Requires-Python populates
    requires_python -- neither is provenance-tracked."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "Summary: A short description.\n"
        "Requires-Python: >=3.10\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.description == "A short description."
    assert metadata.requires_python == ">=3.10"
    assert "description" not in metadata.provenance
    assert "requires_python" not in metadata.provenance


def test_read_wheel_license_field_fallback_when_no_expression(
    tmp_path: Path,
) -> None:
    """When License-Expression is absent, the legacy License field is used
    instead (the elif branch)."""
    metadata_body = (
        "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0.0\nLicense: MIT License\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.license_name == "MIT License"
    assert metadata.provenance["license"] == (
        f"Source: wheel METADATA | File: {wheel_path.name}"
    )


def test_read_wheel_authors_name_and_email(tmp_path: Path) -> None:
    """Author and Author-email both populate a single authors dict entry."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "Author: Jane Doe\n"
        "Author-email: jane@example.com\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.authors == [{"name": "Jane Doe", "email": "jane@example.com"}]


def test_read_wheel_authors_email_only(tmp_path: Path) -> None:
    """Author-email alone (no Author name) still produces an authors entry
    with just the email key."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "Author-email: jane@example.com\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.authors == [{"email": "jane@example.com"}]


def test_read_wheel_no_authors_when_absent(tmp_path: Path) -> None:
    """Neither Author nor Author-email present -> authors stays empty."""
    metadata_body = "Metadata-Version: 2.1\nName: pkg\nVersion: 1.0.0\n"
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.authors == []


def test_read_wheel_urls_homepage_download_and_project_url(
    tmp_path: Path,
) -> None:
    """Home-page and Download-URL populate fixed URL keys; Project-URL
    entries are split on the first comma into label/url pairs."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "Home-page: https://example.com/home\n"
        "Download-URL: https://example.com/download\n"
        "Project-URL: Repository, https://example.com/repo\n"
        "Project-URL: Bug Tracker, https://example.com/issues\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.urls == {
        "Homepage": "https://example.com/home",
        "Download": "https://example.com/download",
        "Repository": "https://example.com/repo",
        "Bug Tracker": "https://example.com/issues",
    }


def test_read_wheel_project_url_without_comma_is_ignored(tmp_path: Path) -> None:
    """A Project-URL entry with no comma cannot be split into label/url and
    is silently skipped."""
    metadata_body = (
        "Metadata-Version: 2.1\n"
        "Name: pkg\n"
        "Version: 1.0.0\n"
        "Project-URL: https://example.com/no-label\n"
    )
    wheel_path = _make_wheel(tmp_path, "pkg", metadata_body)

    metadata, _ = read_wheel(wheel_path)

    assert metadata.urls == {}
