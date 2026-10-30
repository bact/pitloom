# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The messages the AI model scanner logs, on the scanner's logger: why a
confirmed model was not read (:func:`say_unread`), why a file is not one
(:func:`say_not_a_model`), and the text helpers they use.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import LFS_POINTER_REASON, NotAModel
from pitloom.extract.ai_model.limits import ModelLimitExceeded
from pitloom.extract.ai_model.reader_requirements import REQUIREMENTS
from pitloom.logging_config import escape_controls, loggable, one_line
from pitloom.messages import (
    LFS_POINTER_MALFORMED,
    LIBRARY_MISSING,
    MODEL_UNREADABLE,
    MODEL_WRONG_FORMAT,
    emit,
)

if TYPE_CHECKING:
    from pitloom.extract.scanner import ModelCandidate

#: The level of every line said here but a pointer's ``--debug`` one.
_WARNING = logging.WARNING


def _path_forms(path: Path) -> list[str]:
    """Every spelling of *path* an exception text may quote, longest first:
    as given and resolved, each raw, as ``repr`` escapes it (a Windows
    path's backslashes doubled) and with forward slashes."""
    real = os.path.realpath(path)
    forms = {path.as_posix(), Path(real).as_posix()}
    for spelling in (str(path), real):
        forms |= {
            spelling,
            repr(spelling)[1:-1],
            escape_controls(spelling),
            escape_controls(spelling).replace("'", "\\'"),
        }
    return sorted(filter(None, forms), key=len, reverse=True)


def scrub(text: str, path: Path | None, stable_path: str) -> str:
    """*text*, printable on one line (:func:`~pitloom.logging_config.one_line`),
    with the temporary *path* replaced by *stable_path*."""
    if path is not None:
        for form in _path_forms(path):
            text = text.replace(form, stable_path)
    return one_line(text)


def detail(exc: BaseException, path: Path | None, stable_path: str) -> str:
    """*exc*'s text, see :func:`scrub`; never empty: an exception with no
    message yields its class name."""
    return scrub(str(exc), path, stable_path) or type(exc).__name__


def say_unread(
    log: logging.Logger,
    fmt: AiModelFormat,
    candidate: ModelCandidate,
    exc: Exception,
    path: Path | None,
) -> None:
    """The one warning on *log* for a confirmed model whose read failed: a
    bound the file is over (``model-unreadable``, the closed reason), its
    library missing (``library-missing``: an import error of a format that
    needs one), else the reader's own error (``model-unreadable``, the text
    of :func:`detail`), an import error of a reader that needs no library
    included."""
    where = candidate.physical_path
    requirement = REQUIREMENTS.get(fmt)
    if isinstance(exc, ModelLimitExceeded):
        reason = exc.reason
        emit(log, MODEL_UNREADABLE, _WARNING, format=fmt, file=where, reason=reason)
    elif isinstance(exc, ImportError) and requirement is not None:
        spec = requirement.spec
        emit(log, LIBRARY_MISSING, _WARNING, format=fmt, file=where, requirement=spec)
    else:
        error = detail(exc, path, where)
        emit(log, MODEL_UNREADABLE, _WARNING, format=fmt, file=where, error=error)


def say_not_a_model(
    log: logging.Logger, refusal: NotAModel, candidate: ModelCandidate
) -> None:
    """The line on *log* for a file whose header contradicts its model
    suffix (``model-wrong-format``, naming the format the suffix names), or
    is a Git LFS pointer: a whole, valid one is said once for the run (the
    document build), so here only with ``--debug``; an opening whose rest
    does not parse is a defect (``lfs-pointer-malformed``). A pointer named
    ``x.bin`` has no format to name."""
    where, fmt = candidate.physical_path, refusal.model_format
    if refusal.reason != LFS_POINTER_REASON:
        emit(log, MODEL_WRONG_FORMAT, _WARNING, format=fmt, file=where)
    elif candidate.pointer is not None and candidate.pointer() is not None:
        key = "" if fmt is None else f"FORMAT={fmt} "
        log.debug(
            "%sFILE=%s: %s; not listed as an AI model",
            key,
            loggable(where),
            refusal.reason,
        )
    elif fmt is None:
        emit(log, LFS_POINTER_MALFORMED, _WARNING, file=where)
    else:
        emit(log, LFS_POINTER_MALFORMED, _WARNING, format=fmt, file=where)
