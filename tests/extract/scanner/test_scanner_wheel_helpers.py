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
from pathlib import Path
from unittest.mock import Mock

import pytest

from pitloom.extract import scanner_wheel


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
