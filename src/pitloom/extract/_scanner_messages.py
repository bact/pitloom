# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Text helpers for the messages the AI model scanner logs.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import os
from pathlib import Path

from pitloom.logging_config import one_line


def _path_forms(path: Path) -> list[str]:
    """Every spelling of *path* an exception text may quote, longest first:
    as given and resolved, each raw, as ``repr`` escapes it (a Windows
    path's backslashes doubled) and with forward slashes."""
    real = os.path.realpath(path)
    forms = {path.as_posix(), Path(real).as_posix()}
    for spelling in (str(path), real):
        forms |= {spelling, repr(spelling)[1:-1]}
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
