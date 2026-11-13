# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying the option families: the code of ``argparse``'s own refusal
(:func:`usage_code`), and the one line for an option that has no effect
(:func:`warn_option_no_effect`).

See also: :mod:`pitloom.messages._options` (the entries).
"""

from __future__ import annotations

import logging

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import escape_controls
from pitloom.messages._emit import emit
from pitloom.messages._lines import says
from pitloom.messages._options import (
    BUILD_NO_EFFECT_LINE,
    OPTION_INVALID,
    OPTION_MISSING,
    OPTION_NO_EFFECT,
    OPTIONS_NO_EFFECT_INFO_LINE,
    OPTIONS_NO_EFFECT_LINE,
)


def usage_code(text: str) -> str | None:
    """The code of ``argparse``'s refusal *text* (an
    :meth:`argparse.ArgumentParser.error` message): ``option-missing`` or
    ``option-invalid`` when *text*, as the line prints it, is one of that
    entry's lines, else ``None``: a wording a later Python changes carries no
    code it would not be trusted with."""
    shown = escape_controls(text)
    return next(
        (
            entry.code
            for entry in (OPTION_MISSING, OPTION_INVALID)
            if says(entry, "ERROR", shown)
        ),
        None,
    )


# pylint: disable-next=too-many-arguments
def warn_option_no_effect(
    log: logging.Logger,
    *,
    build: bool,
    subject: str,
    option: str,
    when: str,
    level: int = logging.WARNING,
) -> None:
    """The one line on *log*, ``option-no-effect``, for *option* (as the
    command or the library names it) given for *subject* (the target, as
    shown: masked and escaped by the caller) that has no effect *when*
    (``without --allow-build``; no trailing punctuation). *build*: a build
    flag (``Build: ``), else ``Options: ``. *level*: ``logging.INFO`` for a
    setting the surface never acts on (``Options:`` only).

    Raises:
        pitloom.core.internal_error.InternalError: *level* is neither
            ``WARNING`` nor ``INFO``, or ``INFO`` with *build*.
    """
    if level == logging.WARNING:
        line = BUILD_NO_EFFECT_LINE if build else OPTIONS_NO_EFFECT_LINE
    elif level == logging.INFO and not build:
        line = OPTIONS_NO_EFFECT_INFO_LINE
    else:
        raise InternalError(f"no option-no-effect line at level {level} ({build=})")
    emit(
        log,
        OPTION_NO_EFFECT,
        level,
        line=line,
        name=subject,
        option=option,
        when=when,
    )
