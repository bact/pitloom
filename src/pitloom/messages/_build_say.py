# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the build lines: the error a failed build raises
(:class:`BuildFailedError`, built by :func:`build_error`), the line of each
case, and the check a surface's frame passes before it may say a
temporary directory or a signal (:func:`require_codes`).

See also: :mod:`pitloom.messages._build` (the entries).
"""

from __future__ import annotations

from collections.abc import Mapping

from pitloom.core.internal_error import InternalError
from pitloom.messages._build import (
    BUILD_FAILED,
    BUILD_TIMED_OUT_LINES,
    BUILD_TIMED_OUT_UNCONFIRMED_LINES,
    INTERRUPTED_AFTER_LINE,
    INTERRUPTED_DURING_LINE,
    UNSAFE_NO_MODULE_LINES,
    UNSAFE_NO_MODULE_SHARED_LINES,
    UNSAFE_STATIC_FAILED_LINES,
    UNSAFE_STATIC_FAILED_SHARED_LINES,
)
from pitloom.messages._frames import Frame
from pitloom.messages._surface import Twins
from pitloom.messages._types import Line


class BuildFailedError(Exception):
    """A build that gave no wheel to read: its text is a ``build-failed``
    line, written by :func:`build_error`, which the caller says again as a
    ``WARNING:`` from :attr:`said` (the line and its values).

    Its ``pitloom_code`` is ``build-failed``."""

    def __init__(self, text: str, line: Line, values: Mapping[str, object]) -> None:
        super().__init__(text)
        #: The catalogued code (:data:`~pitloom.logging_config.CODE_ATTR`).
        self.pitloom_code: str = BUILD_FAILED.code
        #: The line and the values it was written from.
        self.said: tuple[Line, dict[str, object]] = (line, dict(values))


def build_error(line: Line, **values: object) -> BuildFailedError:
    """The :class:`BuildFailedError` of *line*, one of ``build-failed``'s,
    written from *values*.

    Raises:
        ValueError: *line* is not one of its lines naming *values*, or a
            value does not have its field's shape.
    """
    shape = BUILD_FAILED.line_for(line.level, values, line)
    return BuildFailedError(shape.render(values), shape, values)


def unsafe_line(*, static_failed: bool, isolated: bool) -> Twins[Line]:
    """The ``build-code-unsafe`` line of a build run after the backend's own
    discoverer failed (*static_failed*), else for a backend with none, in a
    build environment of its own (*isolated*) or in Pitloom's, worded for
    each surface."""
    if static_failed:
        return (
            UNSAFE_STATIC_FAILED_LINES
            if isolated
            else UNSAFE_STATIC_FAILED_SHARED_LINES
        )
    return UNSAFE_NO_MODULE_LINES if isolated else UNSAFE_NO_MODULE_SHARED_LINES


def timeout_line(*, tree_terminated: bool) -> Twins[Line]:
    """The ``build-timeout`` line: the build's process tree stopped, or not
    confirmed to have, worded for each surface."""
    return (
        BUILD_TIMED_OUT_LINES if tree_terminated else BUILD_TIMED_OUT_UNCONFIRMED_LINES
    )


def interrupted_line(*, in_hold: bool) -> Line:
    """The ``interrupted`` line of a signal received during the activity
    (*in_hold*) or after it."""
    return INTERRUPTED_DURING_LINE if in_hold else INTERRUPTED_AFTER_LINE


def require_codes(frame: Frame | None, *codes: str) -> None:
    """Refuse *frame* unless a line of each of *codes* may follow it at
    ``WARNING`` and it takes no values: what a surface passes to a step
    that says those lines later, from a cleanup or a signal handler, where
    an error would be lost. ``None``: the lines are said with no frame.

    Raises:
        pitloom.core.internal_error.InternalError: It does not.
    """
    if frame is None:
        return
    refused = [code for code in codes if not frame.allows(code, "WARNING")]
    if refused or frame.fields:
        what = f"does not allow {refused}" if refused else "takes values"
        raise InternalError(f"the frame {frame.template!r} {what}")
