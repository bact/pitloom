# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`tests.warning_helpers.file_values`."""

from __future__ import annotations

from tests.warning_helpers import file_values


def test_file_values_keeps_a_windows_drive_letter() -> None:
    messages = [
        r"FORMAT=onnx FILE=C:\proj\src\m.onnx: failed to extract metadata; x",
        "FILE=pkg/use.py: could not read for usage scanning; y",
        "no file field here",
    ]
    assert file_values(messages) == [r"C:\proj\src\m.onnx", "pkg/use.py"]
