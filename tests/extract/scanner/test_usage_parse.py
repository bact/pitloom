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

import _thread
import contextlib
import io
import logging
import sys
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.model_usage import UsageAccess
from pitloom.extract import _usage_parse
from pitloom.extract.scanner import UsageSource, attach_usage_references
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.models import USAGE_UNPARSEABLE
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


def _scan(chain: str) -> tuple[list[str], list[str]]:
    """Scan a script that reads ``model.onnx`` and holds *chain*; the
    accesses recorded and the codes of the warnings said."""
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
    attach_usage_references([meta], [source])
    return [u.access.value for u in meta.usage_files], handler.codes


def scan_on_a_small_stack(chain: str) -> tuple[list[str], list[str]]:
    """In a child: :func:`_scan` from a thread with a 512 KiB stack."""
    found: list[tuple[list[str], list[str]]] = []
    threading.stack_size(512 * 1024)
    worker = threading.Thread(target=lambda: found.append(_scan(chain)))
    worker.start()
    worker.join()
    return found[0]


def scan_with_no_parse_thread(chain: str) -> tuple[list[str], list[str]]:
    """In a child: :func:`_scan` when no parse thread can be started."""
    with patch.object(
        _usage_parse,
        "start_new_thread",
        autospec=True,
        side_effect=RuntimeError("can't start new thread"),
    ):
        return _scan(chain)


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


def test_no_other_thread_runs_while_the_parse_stack_size_is_set() -> None:
    # A thread the host starts while the size is set would get the parse
    # thread's stack (up to 255 MiB on Python 3.10). A watcher that reads the
    # size whenever it holds the interpreter, switched to as often as it
    # allows, must only ever see the size the host set. From Python 3.12
    # starting a thread raises an audit event, and a Python audit hook (one
    # an earlier test made Pitloom install, say) lets the watcher run while
    # the size is set: it may then see the floor, never more.
    before = threading.stack_size()
    seen: set[int] = set()
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            seen.add(threading.stack_size())

    interval = sys.getswitchinterval()
    watcher = threading.Thread(target=watch, daemon=True)
    sys.setswitchinterval(1e-6)
    try:
        watcher.start()
        for _ in range(200):
            _usage_parse.parse_python("x = 1\n")
    finally:
        stop.set()
        watcher.join()
        sys.setswitchinterval(interval)
    allowed = {before}
    if sys.version_info >= (3, 12):
        allowed.add(8 * _MIB)
    assert seen <= allowed
    assert before in seen


def test_the_parse_thread_runs_under_the_threading_profile_hook() -> None:
    # As a threading.Thread would: coverage and profilers hook in this way.
    threads: set[int] = set()

    def hook(*_: object) -> None:
        threads.add(threading.get_ident())

    previous = threading.getprofile()
    threading.setprofile(hook)
    try:
        _usage_parse.parse_python("x = 1\n")
    finally:
        threading.setprofile(previous)
    assert threads
    assert threading.get_ident() not in threads


@pytest.mark.parametrize("refused", ["stack-size", "thread"])
def test_a_refused_stack_or_thread_parses_on_the_callers_stack(
    refused: str, caplog: pytest.LogCaptureFixture
) -> None:
    sizes: list[int] = []

    def fake_stack_size(*size: int) -> int:
        if refused == "stack-size" and size and size[0]:
            raise ValueError("size not valid")
        sizes.extend(size)
        return 0

    with (
        patch.object(_usage_parse, "stack_size", side_effect=fake_stack_size),
        patch.object(
            _usage_parse,
            "start_new_thread",
            autospec=True,
            side_effect=RuntimeError("can't start new thread"),
        ) as start,
        caplog.at_level(logging.DEBUG, logger="pitloom.extract.scanner"),
    ):
        tree = _usage_parse.parse_python('open("model.onnx")\n')
    assert tree.body
    # The size the host had is put back, whichever step was refused.
    assert sizes == ([0] if refused == "stack-size" else [8 * _MIB, 0])
    assert start.call_count == (refused == "thread")
    assert len(caplog.records) == 1


def test_no_parse_thread_never_crashes_on_a_long_chain() -> None:
    # Python 3.10 would overflow the caller's stack (8 MiB holds about
    # 130,000 links); later ones raise there. Either way the scan says the
    # file is unparseable, once, and records nothing.
    chain = "a" + ".b" * 150_000
    found = run_bounded_in_child(f"{__name__}:scan_with_no_parse_thread", chain)
    assert found == ([], [USAGE_UNPARSEABLE.code])


@pytest.mark.parametrize("refused", ["wanted", "every"])
def test_a_text_beyond_the_floor_never_parses_on_the_callers_stack(
    refused: str,
) -> None:
    sizes: list[int] = []
    starts: list[int] = []

    def recorded_stack_size(*size: int) -> int:
        sizes.extend(size)
        return threading.stack_size(*size)

    def start(work: Callable[[], None], args: tuple[()]) -> int:
        starts.append(threading.stack_size())
        if refused == "every" or starts[-1] > 8 * _MIB:
            raise RuntimeError("can't start new thread")
        return _thread.start_new_thread(work, args)

    with (
        # What Python 3.10 wants for a text of 1 MiB.
        patch.object(_usage_parse, "stack_bytes", return_value=129 * _MIB),
        patch.object(_usage_parse, "stack_size", side_effect=recorded_stack_size),
        patch.object(_usage_parse, "start_new_thread", side_effect=start),
    ):
        if refused == "every":  # not parsed on the caller's stack either
            with pytest.raises(MemoryError):
                _usage_parse.parse_python("x = 1\n")
        else:
            assert _usage_parse.parse_python("x = 1\n").body
    # Tried at the floor after the wanted size, each size put back.
    assert starts == [129 * _MIB, 8 * _MIB]
    assert [size for size in sizes if size] == starts
    assert sizes[-1] == 0


def test_a_parse_error_on_the_thread_is_raised_in_the_caller() -> None:
    with pytest.raises(SyntaxError):
        _usage_parse.parse_python("x = (\n")
