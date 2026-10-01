# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Deterministic ``KeyboardInterrupt`` injection, one statement at a time.

An interrupt is raised (through ``sys.settrace``) before the *n*-th line of a
function's source that lies in a window, so a context manager's entry or undo
can be cut short at every step, in turn. ``with`` lines are skipped: the lock
handling they compile to is not ours to interrupt.
"""

from __future__ import annotations

import inspect
import linecache
import sys
from collections.abc import Callable
from types import CodeType, FrameType
from typing import Any


def statement_lines(
    fn: Callable[..., Any], first: str, last: str
) -> tuple[CodeType, range]:
    """The code of *fn* and the lines from the one starting with *first* up
    to the one starting with *last*, as written in the source."""
    code = inspect.unwrap(fn).__code__
    lines, start = inspect.getsourcelines(code)
    texts = [line.strip() for line in lines]
    begin = next(i for i, t in enumerate(texts) if t.startswith(first))
    end = next(i for i, t in enumerate(texts) if t.startswith(last))
    return code, range(start + begin, start + end + 1)


def run_interrupted(
    block: Callable[[], None], target: tuple[CodeType, range], n: int
) -> bool:
    """Run *block* with a ``KeyboardInterrupt`` before the *n*-th statement of
    *target*; ``False`` when *target* has fewer than *n* statements (the
    block then ran to the end)."""
    code, window = target
    hit: list[int] = []
    count = 0

    previous = sys.gettrace()  # put back, so that coverage keeps tracing

    def local(frame: FrameType, event: str, _arg: Any) -> Any:
        nonlocal count
        text = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
        if (
            event == "line"
            and frame.f_lineno in window
            and not text.startswith("with ")
        ):
            count += 1
            if count == n:
                hit.append(frame.f_lineno)
                raise KeyboardInterrupt
        return local

    def trace(frame: FrameType, event: str, _arg: Any) -> Any:
        return local(frame, event, _arg) if frame.f_code is code else None

    sys.settrace(trace)
    try:
        block()
    except KeyboardInterrupt:
        pass
    finally:
        sys.settrace(previous)
    return bool(hit)
