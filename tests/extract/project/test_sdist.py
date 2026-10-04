# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for sdist archive metadata extraction."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import hashlib
import io
import logging
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import generate_project_sbom
from pitloom.core import wheel_dist_info
from pitloom.extract.project import read_project
from pitloom.extract.project.sdist import _parse_pkg_info, read_sdist
from tests._raw_archive import write_raw_tar, write_raw_zip
from tests.assemble.conftest import _make_sdist


@pytest.fixture
def sample_pkg_info() -> str:
    return (
        "Metadata-Version: 2.1\n"
        "Name: demo-sdist-pkg\n"
        "Version: 1.2.3\n"
        "Summary: A demo package for sdist testing\n"
        "Author: Alice Developer\n"
        "Author-email: alice@example.com\n"
        "License: Apache-2.0\n"
        "Requires-Dist: requests>=2.28.0\n"
    )


def test_read_tar_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.tar.gz"

    with tarfile.open(sdist_path, "w:gz") as tf:
        # PKG-INFO
        pkg_bytes = sample_pkg_info.encode("utf-8")
        ti = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

        # pyproject.toml
        pyproj_bytes = b'[project]\nname = "demo-sdist-pkg"\nversion = "1.2.3"\n'
        ti2 = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/pyproject.toml")
        ti2.size = len(pyproj_bytes)
        tf.addfile(ti2, io.BytesIO(pyproj_bytes))

        # source file
        src_bytes = b'print("hello from sdist")\n'
        ti3 = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/src/main.py")
        ti3.size = len(src_bytes)
        tf.addfile(ti3, io.BytesIO(src_bytes))

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    assert metadata.description == "A demo package for sdist testing"
    assert metadata.authors == [{"name": "Alice Developer"}]
    assert metadata.dependencies == ["requests>=2.28.0"]
    assert len(files) == 3


def test_read_zip_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.zip"

    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr("demo-sdist-pkg-1.2.3/PKG-INFO", sample_pkg_info)
        zf.writestr("demo-sdist-pkg-1.2.3/src/main.py", 'print("hello zip")\n')

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    assert len(files) == 2


def test_read_project_with_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.tar.gz"

    with tarfile.open(sdist_path, "w:gz") as tf:
        pkg_bytes = sample_pkg_info.encode("utf-8")
        ti = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

    metadata, _, path_used = read_project(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    # No pyproject.toml/setup.cfg member: no config file was used.
    assert path_used is None


def test_read_sdist_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_sdist(tmp_path / "non_existent.tar.gz")


# ---------------------------------------------------------------------------
# _parse_pkg_info -- field-by-field provenance and edge cases
# ---------------------------------------------------------------------------


def test_parse_pkg_info_minimal_fields_absent() -> None:
    """A PKG-INFO with only ``Name``: every optional field (version,
    summary, license, requires-python, urls, author, requires-dist) stays
    unset and none of their provenance keys are populated."""
    metadata = _parse_pkg_info("Metadata-Version: 2.1\nName: bare-pkg\n", "src")
    assert metadata.name == "bare-pkg"
    assert metadata.version is None
    assert metadata.description is None
    assert metadata.license_name is None
    assert metadata.requires_python is None
    assert metadata.urls == {}
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert metadata.authors == []
    assert metadata.dependencies == []
    assert metadata.provenance == {"name": "src"}


def test_parse_pkg_info_requires_python_provenance() -> None:
    """A present ``Requires-Python`` field is recorded with its own
    provenance entry."""
    metadata = _parse_pkg_info(
        "Metadata-Version: 2.1\nName: pkg\nRequires-Python: >=3.10\n", "src"
    )
    assert metadata.requires_python == ">=3.10"
    assert metadata.provenance["requires_python"] == "src"


def test_parse_pkg_info_project_urls_mixed_valid_invalid() -> None:
    """``Project-URL`` entries without a comma are skipped; valid
    ``label, url`` entries are kept."""
    pkg_info = (
        "Metadata-Version: 2.1\n"
        "Name: url-pkg\n"
        "Project-URL: Homepage, https://example.com\n"
        "Project-URL: no-comma-here\n"
        "Project-URL: Repository, https://example.com/repo\n"
    )
    metadata = _parse_pkg_info(pkg_info, "src")
    assert metadata.urls == {
        "Homepage": "https://example.com",
        "Repository": "https://example.com/repo",
    }
    assert metadata.provenance["urls"] == "src"


def test_parse_pkg_info_project_urls_all_invalid_leaves_urls_empty() -> None:
    """When every ``Project-URL`` entry lacks a comma, no ``urls`` end up
    populated and the ``urls`` provenance key is never set."""
    pkg_info = "Metadata-Version: 2.1\nName: url-pkg\nProject-URL: no-comma-here\n"
    metadata = _parse_pkg_info(pkg_info, "src")
    assert metadata.urls == {}
    assert "urls" not in metadata.provenance


def test_parse_pkg_info_author_unknown_is_skipped() -> None:
    """``Author: UNKNOWN`` (setuptools' placeholder for an absent author)
    must not be recorded as a real author."""
    pkg_info = "Metadata-Version: 2.1\nName: pkg\nAuthor: UNKNOWN\n"
    metadata = _parse_pkg_info(pkg_info, "src")
    # pylint: disable-next=use-implicit-booleaness-not-comparison
    assert metadata.authors == []
    assert "authors" not in metadata.provenance


# ---------------------------------------------------------------------------
# _read_tar_sdist -- directory entries, unreadable members, pyproject-only
# fallback, and the "found nothing" default
# ---------------------------------------------------------------------------


def test_read_tar_sdist_skips_directory_entries(tmp_path: Path) -> None:
    """Directory entries in the tarball are not hashed or listed as files."""
    sdist_path = tmp_path / "dirpkg-1.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tf:
        dir_info = tarfile.TarInfo(name="dirpkg-1.0/src")
        dir_info.type = tarfile.DIRTYPE
        tf.addfile(dir_info)

        pkg_bytes = b"Metadata-Version: 2.1\nName: dirpkg\nVersion: 1.0\n"
        ti = tarfile.TarInfo(name="dirpkg-1.0/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "dirpkg"
    assert len(files) == 1
    assert files[0].distribution_path == "dirpkg-1.0/PKG-INFO"


def test_read_tar_sdist_skips_member_when_extractfile_returns_none(
    tmp_path: Path,
) -> None:
    """A tar member that passes ``isfile()`` but whose ``extractfile()``
    still returns ``None`` (defensive edge case) is skipped rather than
    crashing."""
    sdist_path = tmp_path / "oddpkg-1.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tf:
        pkg_bytes = b"Metadata-Version: 2.1\nName: oddpkg\nVersion: 1.0\n"
        ti = tarfile.TarInfo(name="oddpkg-1.0/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

        src_bytes = b"print('hi')\n"
        ti2 = tarfile.TarInfo(name="oddpkg-1.0/skip-me.py")
        ti2.size = len(src_bytes)
        tf.addfile(ti2, io.BytesIO(src_bytes))

    original_extractfile = tarfile.TarFile.extractfile

    def fake_extractfile(
        self: tarfile.TarFile, member: str | tarfile.TarInfo
    ) -> object:
        name = member if isinstance(member, str) else member.name
        if name == "oddpkg-1.0/skip-me.py":
            return None
        return original_extractfile(self, member)

    with patch.object(tarfile.TarFile, "extractfile", fake_extractfile):
        metadata, files, *_ = read_sdist(sdist_path)

    assert metadata.name == "oddpkg"
    distribution_paths = [f.distribution_path for f in files]
    assert "oddpkg-1.0/PKG-INFO" in distribution_paths
    assert "oddpkg-1.0/skip-me.py" not in distribution_paths


def test_read_tar_sdist_pyproject_only_fallback(tmp_path: Path) -> None:
    """No ``PKG-INFO``: metadata is built from ``pyproject.toml``'s
    ``[project]`` table instead."""
    sdist_path = tmp_path / "pyprojpkg-1.0.tar.gz"
    pyproj_bytes = (
        b'[project]\nname = "pyprojpkg"\nversion = "1.0"\n'
        b'description = "Built from pyproject.toml"\n'
        b'dependencies = ["click>=8.0"]\n'
    )
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="pyprojpkg-1.0/pyproject.toml")
        ti.size = len(pyproj_bytes)
        tf.addfile(ti, io.BytesIO(pyproj_bytes))

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "pyprojpkg"
    assert metadata.version == "1.0"
    assert metadata.description == "Built from pyproject.toml"
    assert metadata.dependencies == ["click>=8.0"]
    assert len(files) == 1


def test_read_tar_sdist_pyproject_malformed_falls_back_to_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No ``PKG-INFO`` and an unparsable ``pyproject.toml``: degrades to the
    ``name="unknown"`` default rather than raising (with the config not
    read; read, it raises as for a directory) -- and logs the failure
    at ``WARNING`` level, since it drops project metadata from the SBOM."""
    sdist_path = tmp_path / "badpkg-1.0.tar.gz"
    bad_bytes = b"this is not valid toml [[["
    with tarfile.open(sdist_path, "w:gz") as tf:
        ti = tarfile.TarInfo(name="badpkg-1.0/pyproject.toml")
        ti.size = len(bad_bytes)
        tf.addfile(ti, io.BytesIO(bad_bytes))

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract.project.sdist"):
        metadata, files, *_ = read_sdist(sdist_path, read_config=False)
    assert metadata.name == "unknown"
    assert len(files) == 1
    assert "Failed to parse pyproject.toml" in caplog.text


def test_read_tar_sdist_neither_pkg_info_nor_pyproject(tmp_path: Path) -> None:
    """Neither ``PKG-INFO`` nor ``pyproject.toml`` present: metadata stays
    at its ``name="unknown"`` default, but files are still listed."""
    sdist_path = tmp_path / "plainpkg-1.0.tar.gz"
    with tarfile.open(sdist_path, "w:gz") as tf:
        src_bytes = b"print('hello')\n"
        ti = tarfile.TarInfo(name="plainpkg-1.0/src/main.py")
        ti.size = len(src_bytes)
        tf.addfile(ti, io.BytesIO(src_bytes))

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "unknown"
    assert len(files) == 1


# ---------------------------------------------------------------------------
# _read_zip_sdist -- directory entries, pyproject-only fallback, and the
# "found nothing" default
# ---------------------------------------------------------------------------


def test_read_zip_sdist_skips_directory_entries(tmp_path: Path) -> None:
    """Directory entries in the zip archive are not hashed or listed."""
    sdist_path = tmp_path / "dirpkg-1.0.zip"
    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr("dirpkg-1.0/src/", "")
        zf.writestr(
            "dirpkg-1.0/PKG-INFO",
            "Metadata-Version: 2.1\nName: dirpkg\nVersion: 1.0\n",
        )

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "dirpkg"
    assert len(files) == 1
    assert files[0].distribution_path == "dirpkg-1.0/PKG-INFO"


def test_read_zip_sdist_pyproject_only_fallback(tmp_path: Path) -> None:
    """No ``PKG-INFO`` in the zip: metadata is built from
    ``pyproject.toml``'s ``[project]`` table."""
    sdist_path = tmp_path / "pyprojpkg-1.0.zip"
    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr(
            "pyprojpkg-1.0/pyproject.toml",
            '[project]\nname = "pyprojpkg"\nversion = "2.0"\n'
            'description = "Zip-sourced"\n',
        )

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "pyprojpkg"
    assert metadata.version == "2.0"
    assert metadata.description == "Zip-sourced"
    assert len(files) == 1


def test_read_zip_sdist_pyproject_malformed_falls_back_to_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No ``PKG-INFO`` and an unparsable ``pyproject.toml`` in the zip:
    degrades to the ``name="unknown"`` default rather than raising (with the config not
    read; read, it raises as for a directory) -- and
    logs the failure at ``WARNING`` level (regression test: the zip path
    used to duplicate ``_parse_pyproject_bytes()``'s logic inline with no
    logging at all, unlike the tar path, which already called the shared,
    now-logging helper)."""
    sdist_path = tmp_path / "badpkg-1.0.zip"
    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr("badpkg-1.0/pyproject.toml", "not [[[ valid toml")

    with caplog.at_level(logging.DEBUG, logger="pitloom.extract.project.sdist"):
        metadata, files, *_ = read_sdist(sdist_path, read_config=False)
    assert metadata.name == "unknown"
    assert len(files) == 1
    assert "Failed to parse pyproject.toml" in caplog.text


def test_read_zip_sdist_neither_pkg_info_nor_pyproject(tmp_path: Path) -> None:
    """Neither ``PKG-INFO`` nor ``pyproject.toml`` present in the zip:
    metadata stays at its ``name="unknown"`` default, but files are still
    listed."""
    sdist_path = tmp_path / "plainpkg-1.0.zip"
    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr("plainpkg-1.0/src/main.py", "print('hello')\n")

    metadata, files, *_ = read_sdist(sdist_path)
    assert metadata.name == "unknown"
    assert len(files) == 1


@pytest.mark.parametrize("suffix", [".tar.gz", ".zip"])
def test_member_order_does_not_change_the_sbom(
    tmp_path: Path, suffix: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids are minted in file order, so archive order must not reach them."""
    # Three runs: an unpinned clock can tick between them and change `created`.
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    members = {
        "demo-1.0/PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        "demo-1.0/pyproject.toml": b"[project]\nname = 'demo'\n",
        "demo-1.0/demo/__init__.py": b"",
        "demo-1.0/demo/mod.py": b"x = 1\n",
        "demo-1.0/README.md": b"# demo\n",
    }
    names = list(members)
    outputs = set()
    orders = set()
    for number, order in enumerate((names, names[::-1], names[2:] + names[:2])):
        (tmp_path / str(number)).mkdir()
        sdist = tmp_path / str(number) / f"demo-1.0{suffix}"
        ordered = {name: members[name] for name in order}
        if suffix == ".zip":
            write_raw_zip(sdist, ordered)
        else:
            write_raw_tar(sdist, ordered)
        orders.add(tuple(_archive_names(sdist)))
        outputs.add(generate_project_sbom(sdist, offline=True))

    assert len(orders) == 3
    assert len(outputs) == 1


def _archive_names(sdist: Path) -> list[str]:
    """The archive's member names in the order the archive lists them."""
    if sdist.suffix == ".zip":
        with zipfile.ZipFile(sdist) as zf:
            return zf.namelist()
    with tarfile.open(sdist) as tf:
        return tf.getnames()


_PKG_INFO_HEAD = b"Metadata-Version: 2.1\nName: big\nVersion: 9.9\nLicense: MIT\n"


@pytest.mark.parametrize(
    ("extra", "limits", "pyproject", "status"),
    [
        (b"", {"MAX_METADATA_HEADERS": 4}, True, None),  # headers at cap
        (b"X-A: b\n", {"MAX_METADATA_HEADERS": 4}, True, "degraded"),
        (b"X-A: b\n", {"MAX_METADATA_BYTES": len(_PKG_INFO_HEAD)}, False, "skipped"),
        # The description after the headers may be any size.
        (b"\n" + b"x" * 70_000, {"MAX_METADATA_BYTES": 64 * 1024}, False, None),
    ],
    ids=["headers-at-cap", "headers-over-cap", "bytes-over-cap", "big-body"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_pkg_info_header_block_over_cap_is_not_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    extra: bytes,
    limits: dict[str, int],
    pyproject: bool,
    status: str | None,
) -> None:
    """``PKG-INFO`` is read as a wheel's ``METADATA`` is: its header block
    alone, capped in bytes and headers. Over a cap: one ``WARNING:`` names
    the archive, and the metadata comes from ``pyproject.toml`` as with no
    ``PKG-INFO``. The member is still hashed whole."""
    for cap, value in limits.items():
        monkeypatch.setattr(wheel_dist_info, cap, value)
    pkg_info = _PKG_INFO_HEAD + extra
    members = {"PKG-INFO": pkg_info, **({} if pyproject else {"pyproject.toml": None})}
    sdist = _make_sdist(tmp_path, members=members)

    with caplog.at_level(logging.WARNING):
        contents = read_sdist(sdist)

    (entry,) = [f for f in contents.files if f.distribution_path.endswith("PKG-INFO")]
    assert entry.digest_sha256 == hashlib.sha256(pkg_info).hexdigest()
    expected = "big" if status is None else ("demo" if pyproject else "unknown")
    assert contents.metadata.name == expected
    assert (contents.metadata.license_name == "MIT") is (status is None)
    warnings = [r.getMessage() for r in caplog.records]
    if status is None:
        assert not warnings
        return
    (message,) = warnings
    assert "PKG-INFO" in message and sdist.name in message
    assert "header block over" in message
    assert f"Field(s) affected ({status}): name" in message
