# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the usage scan's parse on a stack sized to the text
(:mod:`pitloom.extract._usage_parse`): a long chain must not crash the
process, whatever stack the caller runs on.

See also: :mod:`tests.extract.scanner.test_usage_unparseable` (what a parse
failure says).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import contextlib
import io
import logging
import sys
import threading
from contextlib import AbstractContextManager
from unittest.mock import create_autospec, patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.model_usage import UsageAccess
from pitloom.extract import _usage_parse
from pitloom.extract.scanner import UsageSource, attach_usage_references
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import USAGE_UNPARSEABLE
from tests._bounded import run_bounded_in_child

_MIB = 1024 * 1024
#: Links of a chain the parse turns into a tree one C call per link: past
#: what a 512 KiB stack holds (about 8,000 on CPython 3.10).
_LINKS = 20_000


class _Codes(logging.Handler):
    """The code of each record it is given."""

    def __init__(self, level: int) -> None:
        super().__init__(level)
        self.codes: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.codes.append(str(getattr(record, CODE_ATTR, "")))


def scan_on_a_small_stack(chain: str) -> tuple[list[str], list[str]]:
    """In a child: scan a script that reads ``model.onnx`` and holds
    *chain*, from a thread with a 512 KiB stack; the accesses recorded and
    the codes of the warnings said."""
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="model.onnx",
            file_path_relative="pkg/model.onnx",
            physical_path="src/pkg/model.onnx",
        )
    )
    data = f'open("model.onnx")\nx = {chain}\n'.encode()

    def _open() -> AbstractContextManager[io.BytesIO]:
        return contextlib.nullcontext(io.BytesIO(data))

    source = UsageSource("pkg/deep.py", "src/pkg/deep.py", _open)
    handler = _Codes(logging.WARNING)
    logging.getLogger("pitloom").addHandler(handler)
    threading.stack_size(512 * 1024)
    worker = threading.Thread(target=attach_usage_references, args=([meta], [source]))
    worker.start()
    worker.join()
    return [u.access.value for u in meta.usage_files], handler.codes


@pytest.mark.parametrize(
    "chain",
    ["a" + ".b" * _LINKS, "f" + "()" * _LINKS, '"a"' + ' + "a"' * _LINKS],
    ids=["attribute", "call", "sum"],
)
def test_a_long_chain_does_not_crash_a_small_stack(chain: str) -> None:
    accesses, codes = run_bounded_in_child(f"{__name__}:scan_on_a_small_stack", chain)
    # Python 3.10 builds the tree on the parse thread's stack; later ones may
    # refuse it as too deep, which the scan says once and records nothing.
    if accesses:
        assert (accesses, codes) == ([UsageAccess.READ.value], [])
    else:
        assert sys.version_info >= (3, 11)
        assert codes == [USAGE_UNPARSEABLE.code]


@pytest.mark.parametrize(
    ("chars", "checks_depth", "expected"),
    [
        (0, False, 8 * _MIB),
        (_MIB, False, 128 * _MIB),
        (_MIB + 1, False, 129 * _MIB),
        (4 * _MIB, False, 255 * _MIB),
        (_MIB, True, 8 * _MIB),
    ],
    ids=["floor", "per-char", "whole-mib", "ceiling", "checked-depth"],
)
def test_the_parse_stack_grows_with_the_text_on_python_3_10(
    chars: int, checks_depth: bool, expected: int
) -> None:
    assert _usage_parse.stack_bytes(chars, checks_depth=checks_depth) == expected


def test_the_stack_size_is_restored_after_a_parse() -> None:
    before = threading.stack_size()
    assert _usage_parse.parse_python("x = 1\n").body
    assert threading.stack_size() == before


@pytest.mark.parametrize("refused", ["stack-size", "thread"])
def test_a_refused_stack_or_thread_parses_on_the_callers_stack(
    refused: str, caplog: pytest.LogCaptureFixture
) -> None:
    sizes: list[int] = []

    def fake_stack_size(size: int = 0) -> int:
        if refused == "stack-size" and size:
            raise ValueError("size not valid")
        sizes.append(size)
        return 0

    thread = create_autospec(threading.Thread, instance=True)
    thread.start.side_effect = RuntimeError("can't start new thread")
    with (
        patch.object(_usage_parse, "stack_size", side_effect=fake_stack_size),
        patch.object(_usage_parse, "Thread", return_value=thread),
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        tree = _usage_parse.parse_python('open("model.onnx")\n')
    assert tree.body
    # A size set is put back; the thread never ran, so it is never joined.
    assert sizes == ([] if refused == "stack-size" else [8 * _MIB, 0])
    thread.join.assert_not_called()
    assert len(caplog.records) == 1


def test_a_parse_error_on_the_thread_is_raised_in_the_caller() -> None:
    with pytest.raises(SyntaxError):
        _usage_parse.parse_python("x = (\n")
