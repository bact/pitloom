# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_wheel`` names each file by its install location, on every OS.

The wheels here are written with raw central-directory names
(:mod:`tests._raw_wheel`), so the tests do not depend on the runner's
``os.sep``.

See also: tests/core/test_wheel_member_names.py (the normaliser),
tests/test_wheel_member_name_surfaces.py (every wheel surface).
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_wheel_sbom
from pitloom.extract.wheel import read_wheel
from tests._raw_wheel import METADATA, mimic_windows_infolist, write_raw_wheel

_DIST_INFO = "demo-1.0.0.dist-info"
_MEMBERS = {
    f"{_DIST_INFO}/METADATA": METADATA,
    "demo/__init__.py": b"",
    "demo\\mod.py": b"mod = 1\n",
    "./demo/sub//deep.py": b"deep = 1\n",
    "../evil.py": b"evil = 1\n",
    "/abs/evil.py": b"evil = 2\n",
    "demo\\": b"",
}
_EXPECTED = {
    f"{_DIST_INFO}/METADATA",
    "demo/__init__.py",
    "demo/mod.py",
    "demo/sub/deep.py",
}


def _wheel(tmp_path: Path, members: dict[str, bytes] | None = None) -> Path:
    return write_raw_wheel(
        tmp_path / "demo-1.0.0-py3-none-any.whl",
        _MEMBERS if members is None else members,
    )


def _sbom(wheel: Path) -> str:
    return generate_wheel_sbom(wheel, offline=True)


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _file_names(sbom: str) -> dict[str, str]:
    """``software_File`` name -> fileKind for every file element."""
    return {
        e["name"]: e.get("software_fileKind", "")
        for e in _graph(sbom)
        if e["type"] == "software_File"
    }


def test_read_wheel_normalises_member_names(tmp_path: Path) -> None:
    """Regression: ``demo\\mod.py`` was recorded verbatim on POSIX (and as
    ``demo/mod.py`` on Windows). Every name is now the install location;
    unsafe members are skipped; siblings keep their real hashes."""
    _, files = read_wheel(_wheel(tmp_path))

    by_name = {f.distribution_path: f for f in files}
    assert set(by_name) == _EXPECTED
    assert all(f.physical_path == f.distribution_path for f in files)
    assert by_name["demo/mod.py"].digest_sha256 == (
        hashlib.sha256(b"mod = 1\n").hexdigest()
    )


def test_read_wheel_warns_once_per_non_conforming_member(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """One ``WARNING:`` per non-conforming or unsafe member, quoting the
    raw name; none for conforming members or directory entries."""
    with caplog.at_level(logging.WARNING):
        read_wheel(_wheel(tmp_path))

    messages = sorted(r.getMessage() for r in caplog.records)
    wheel = "demo-1.0.0-py3-none-any.whl"
    assert messages == sorted(
        [
            f"{wheel}: wheel entry 'demo\\\\mod.py' is non-conforming"
            " -- recorded as 'demo/mod.py'",
            f"{wheel}: wheel entry './demo/sub//deep.py' is non-conforming"
            " -- recorded as 'demo/sub/deep.py'",
            f"{wheel}: wheel entry '../evil.py' has no safe install location"
            " -- skipped",
            f"{wheel}: wheel entry '/abs/evil.py' has no safe install location"
            " -- skipped",
        ]
    )


def test_read_wheel_conforming_wheel_warns_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    members = dict.fromkeys(_EXPECTED, b"")
    with caplog.at_level(logging.WARNING):
        _, files = read_wheel(_wheel(tmp_path, members))
    assert {f.distribution_path for f in files} == _EXPECTED
    assert not caplog.records


def test_read_wheel_finds_metadata_under_backslash_dist_info(tmp_path: Path) -> None:
    """``METADATA`` is found by its normalised name, so a backslash
    ``.dist-info`` path is read on every OS, not only on Windows."""
    metadata, _ = read_wheel(_wheel(tmp_path, {f"{_DIST_INFO}\\METADATA": METADATA}))
    assert (metadata.name, metadata.version) == ("demo", "1.0.0")


def test_read_wheel_skips_unsafe_metadata(tmp_path: Path) -> None:
    """An unsafe ``../x.dist-info/METADATA`` is skipped, not parsed."""
    metadata, files = read_wheel(
        _wheel(tmp_path, {f"../{_DIST_INFO}/METADATA": METADATA})
    )
    assert metadata.name == "unknown"
    assert not files


def test_wheel_sbom_names_and_directory_chain(tmp_path: Path) -> None:
    """The SBOM's files are the install locations, and its directory
    elements (the ``contains`` chain) contain no ``..``, ``/`` or
    backslash-joined names."""
    names = _file_names(_sbom(_wheel(tmp_path)))

    files = {n for n, kind in names.items() if kind.endswith("file")}
    directories = {n for n, kind in names.items() if kind.endswith("directory")}
    assert files == _EXPECTED
    assert directories == {_DIST_INFO, "demo", "demo/sub"}


def test_wheel_sbom_identical_on_windows_and_posix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The same wheel gives the same SBOM bytes and warnings whether
    ``ZipInfo.filename`` has Windows' conversion applied or not."""
    wheel = _wheel(tmp_path)
    with caplog.at_level(logging.WARNING):
        native = _sbom(wheel)
    native_warnings = [r.getMessage() for r in caplog.records]
    caplog.clear()

    with zipfile.ZipFile(wheel) as zf:
        windows_names = {i.filename for i in mimic_windows_infolist(zf)}
    # Not vacuous: the mimicked listing has Windows' converted filename.
    assert "demo/mod.py" in windows_names
    monkeypatch.setattr(zipfile.ZipFile, "infolist", mimic_windows_infolist)
    with caplog.at_level(logging.WARNING):
        windows = _sbom(wheel)

    assert windows == native
    assert [r.getMessage() for r in caplog.records] == native_warnings
    assert len(native_warnings) == 4


def test_wheel_sbom_deterministic(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path)
    assert _sbom(wheel) == _sbom(wheel)
