# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_sdist`` names members by their install location, on every OS.

Both archive kinds go through the shared normaliser. Zip members are
written raw (:mod:`tests._raw_archive`), so the tests do not depend on the
runner's ``os.sep``.

See also: tests/core/test_archive_member_names.py (the normaliser),
tests/extract/project/test_sdist.py (sdist metadata).
"""

from __future__ import annotations

import logging
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.extract.project.sdist import read_sdist, sdist_config_source
from tests._raw_archive import (
    SDIST_FILES,
    SDIST_MEMBERS,
    SDIST_ROOT,
    SDIST_WARNED,
    mimic_windows_infolist,
    write_raw_member,
    write_raw_tar,
    write_raw_zip,
)


def _zip_sdist(tmp_path: Path) -> Path:
    return write_raw_zip(tmp_path / f"{SDIST_ROOT}.zip", SDIST_MEMBERS)


def _tar_sdist(tmp_path: Path) -> Path:
    return write_raw_tar(tmp_path / f"{SDIST_ROOT}.tar.gz", SDIST_MEMBERS)


@pytest.mark.parametrize("make", [_zip_sdist, _tar_sdist], ids=["zip", "tar"])
def test_read_sdist_normalises_member_names(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    make: Callable[[Path], Path],
) -> None:
    """Names are install locations; root members (``PKG-INFO``,
    ``pyproject.toml``) are found under a non-conforming spelling; unsafe
    members are skipped; one ``WARNING:`` each, quoting the raw name."""
    sdist = make(tmp_path)
    with caplog.at_level(logging.WARNING):
        contents = read_sdist(sdist)

    assert {f.distribution_path for f in contents.files} == SDIST_FILES
    assert (contents.metadata.name, contents.metadata.version) == ("demo", "1.0.0")
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == len(SDIST_WARNED), messages
    for raw in SDIST_WARNED:
        assert sum(f"ARCHIVE={sdist.name!r} ENTRY={raw}:" in m for m in messages) == 1


def test_sdist_config_source_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The ``--verbose`` root-only read does not repeat the full read's
    member-name warnings, and still finds the root ``pyproject.toml``."""
    sdist = _zip_sdist(tmp_path)
    with caplog.at_level(logging.WARNING):
        member, _ = sdist_config_source(sdist)
    assert member == "pyproject.toml"
    assert not caplog.records


def test_zip_sdist_same_on_windows_and_posix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same zip sdist gives the same files whether ``ZipInfo.filename``
    has Windows' conversion applied or not."""
    sdist = _zip_sdist(tmp_path)
    native = read_sdist(sdist)
    with zipfile.ZipFile(sdist) as zf:
        converted = {i.filename for i in mimic_windows_infolist(zf)}
    assert f"{SDIST_ROOT}/demo/mod.py" in converted  # the mimic changed a name

    monkeypatch.setattr(zipfile.ZipFile, "infolist", mimic_windows_infolist)
    windows = read_sdist(sdist)

    assert windows.files == native.files
    assert windows.metadata == native.metadata


def test_tar_sdist_dot_prefix_is_quiet(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A tar packed as ``./<root>/...`` (``tar -C dir -czf x .``) is
    ordinary: its names lose the ``./`` with no warning per member."""
    members = {f"./{n}": b"" for n in SDIST_FILES}
    sdist = write_raw_tar(tmp_path / f"{SDIST_ROOT}.tar.gz", members)
    with caplog.at_level(logging.WARNING):
        contents = read_sdist(sdist, read_config=False)
    assert {f.distribution_path for f in contents.files} == SDIST_FILES
    assert not caplog.records


def test_duplicate_root_member_last_wins(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Two copies of one root member: the last is read, as unpacking the
    archive leaves it, and the first warns as overwritten."""
    first = b"Metadata-Version: 2.1\nName: first\nVersion: 1.0.0\n"
    second = b"Metadata-Version: 2.1\nName: second\nVersion: 1.0.0\n"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # zipfile: duplicate name
        with zipfile.ZipFile(tmp_path / "d.zip", "w") as zf:
            write_raw_member(zf, f"{SDIST_ROOT}/PKG-INFO", first)
            write_raw_member(zf, f"{SDIST_ROOT}/PKG-INFO", second)
    with caplog.at_level(logging.WARNING):
        contents = read_sdist(tmp_path / "d.zip", read_config=False)
    assert contents.metadata.name == "second"
    assert [r.getMessage() for r in caplog.records] == [
        f"ARCHIVE='d.zip' ENTRY='{SDIST_ROOT}/PKG-INFO': overwritten by later"
        f" entry '{SDIST_ROOT}/PKG-INFO' -- skipped"
    ]
