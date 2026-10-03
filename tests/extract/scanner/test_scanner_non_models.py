# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A candidate whose header does not confirm a model gives no entry: silent
when it is simply not one, one ``WARNING:`` when the header contradicts a
model suffix. The reader is never run.

See also: :mod:`tests.extract.scanner.test_scanner` (the rest of the policy)
and :mod:`tests.extract.scanner.test_scanner_path_config` (``.pth`` text).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.scanner import ModelCandidate, discover_ai_models
from tests.warning_helpers import logged_warnings

_LOGGER_NAME = "pitloom.extract.scanner"
_READ = "pitloom.extract.scanner.read_ai_model"
_GGUF = AiModelFormat.GGUF.magic or b""


def _cand(dist: str, phys: str | None = None, header: bytes = b"") -> ModelCandidate:
    return ModelCandidate(
        distribution_path=dist,
        physical_path=phys or dist,
        sniff=Mock(return_value=header),
        materialize=lambda: contextlib.nullcontext(Path("unused")),
    )


_LFS = b"version https://git-lfs.github.com/spec/v1\n"
_LFS_WARNING = "%sFILE=src/%s: header is a Git LFS pointer; "
_NOT_FMT_WARNING = "FORMAT=gguf FILE=src/m.gguf: header is not gguf; "


@pytest.mark.parametrize(
    ("dist", "header", "warns"),
    [
        # simply not a model: silent (``.pth`` text is path configuration)
        ("pkg/notes.bin", b"plain text", None),
        ("pkg/a.zip", b"PK\x03\x04", None),
        ("pkg/a.bin", b"", None),
        ("pkg/a.bin", _GGUF[:-1], None),
        ("m.onnx", b"", None),  # absent, empty or a directory
        ("m.gguf", b"", None),
        ("m.bin", b"text", None),
        ("m.pth", b"import os\n", None),
        # the header contradicts the suffix: one WARNING
        ("m.gguf", b"plain text", _NOT_FMT_WARNING),
        # a Git LFS pointer is no model under any candidate suffix: a magic
        # one, one that admits any header, PyTorch's, and one that names no
        # format (no FORMAT= to give)
        ("m.gguf", _LFS, _LFS_WARNING % ("FORMAT=gguf ", "m.gguf")),
        ("m.onnx", _LFS, _LFS_WARNING % ("FORMAT=onnx ", "m.onnx")),
        ("m.pt", _LFS, _LFS_WARNING % ("FORMAT=pytorch ", "m.pt")),
        ("m.bin", _LFS, _LFS_WARNING % ("", "m.bin")),
        ("m.zip", _LFS, _LFS_WARNING % ("", "m.zip")),
    ],
)
def test_discover_lists_no_entry_for_a_non_model_and_warns_only_on_a_contradiction(
    caplog: pytest.LogCaptureFixture, dist: str, header: bytes, warns: str | None
) -> None:
    with patch(_READ, autospec=True) as reader:
        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            found = discover_ai_models([_cand(dist, f"src/{dist}", header=header)])
    assert not found
    reader.assert_not_called()
    messages = logged_warnings(caplog)
    assert len(messages) == (warns is not None)
    if warns is not None:
        assert messages[0] == warns + "not listed as an AI model"
