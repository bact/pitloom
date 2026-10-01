# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The small helpers of the wheel scan producer: the Zstandard error probe,
and the quiet copy removal.

See also: :mod:`tests.extract.scanner.test_scanner_wheel_limits`.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from pitloom.extract import scanner_wheel


class _ZstdError(Exception):
    pass


def _importer(result: object) -> Any:
    def import_module(_name: str) -> object:
        if isinstance(result, Exception):
            raise result
        return result

    return import_module


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (SimpleNamespace(ZstdError=_ZstdError), (_ZstdError,)),
        (SimpleNamespace(ZstdError="not a class"), ()),
        (SimpleNamespace(), ()),
        (ImportError("no compression.zstd"), ()),
    ],
    ids=["present", "not-a-class", "absent-name", "no-module"],
)
def test_the_zstd_error_is_used_only_when_the_module_defines_one(
    monkeypatch: pytest.MonkeyPatch, module: object, expected: tuple[type, ...]
) -> None:
    monkeypatch.setattr(
        scanner_wheel, "importlib", SimpleNamespace(import_module=_importer(module))
    )
    assert scanner_wheel._zstd_errors() == expected


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
