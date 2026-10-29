# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The small helpers of the wheel scan producer: the quiet copy removal.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_limits`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import pytest

from pitloom.core.lfs_pointer import LFS_POINTER_MAX_BYTES
from pitloom.extract import scanner_wheel
from tests._lfs import lfs_pointer_bytes


def test_removing_a_copy_never_raises_and_never_names_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=scanner_wheel.__name__)
    target = tmp_path / "secret-dir" / "0.pt"
    unlink = Mock(spec=os.unlink)
    monkeypatch.setattr(os, "unlink", unlink)

    scanner_wheel._unlink_quietly(None)
    unlink.assert_not_called()

    unlink.side_effect = FileNotFoundError(2, "gone", str(target))
    scanner_wheel._unlink_quietly(target)
    assert not caplog.records  # already gone: silent

    unlink.side_effect = PermissionError(13, "Permission denied", str(target))
    scanner_wheel._unlink_quietly(target)
    (record,) = caplog.records
    assert record.levelno == logging.DEBUG
    assert "Permission denied" in record.getMessage()
    assert "secret-dir" not in record.getMessage()


def _info_with_flags(info: zipfile.ZipInfo, flag_bits: int) -> zipfile.ZipInfo:
    info.flag_bits |= flag_bits
    return info


@pytest.mark.parametrize(
    ("data", "flag_bits", "found"),
    [
        (lfs_pointer_bytes(b"w"), 0, True),
        (lfs_pointer_bytes(b"w") + b"\n" * LFS_POINTER_MAX_BYTES, 0, False),
        (lfs_pointer_bytes(b"w"), 0x1, False),  # encrypted: unreadable, no pointer
    ],
    ids=["pointer", "member-over-the-cut-off", "encrypted-member"],
)
def test_wheel_pointer_reader_reads_small_readable_members_only(
    tmp_path: Path, data: bytes, flag_bits: int, found: bool
) -> None:
    """A member at or over the cut-off is not opened; one that cannot be read
    is no pointer, and nothing raises."""
    wheel = tmp_path / "m-1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(zipfile.ZipInfo("pkg/m.gguf", (1980, 1, 1, 0, 0, 0)), data)
    with zipfile.ZipFile(wheel) as zf:
        info = _info_with_flags(zf.infolist()[0], flag_bits)
        with mock.patch.object(zf, "open", wraps=zf.open) as opened:
            pointer = scanner_wheel._pointer_reader(zf, info)()
    assert (pointer is not None) is found
    assert opened.called is (len(data) < LFS_POINTER_MAX_BYTES)
