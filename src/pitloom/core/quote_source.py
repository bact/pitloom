# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Quote a path or file name for a log or stderr message.

Lives in ``core`` so core modules can use it without importing the
``pitloom.extract`` package (which imports ``core`` back).
"""

from __future__ import annotations

import os
import sys

from pitloom.logging_config import escape_controls

__all__ = ["quote_source"]


def quote_source(source: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> str:
    """*source* in quotes, written as the OS writes it, on one line.

    ``repr()`` of a :class:`~pathlib.Path` shows ``WindowsPath('D:/a/b')``
    (forward slashes) and of a ``str`` doubles each backslash; neither matches
    ``str(path)``, which a reader of the message looks for. What
    :func:`~pitloom.logging_config.escape_controls` escapes (control
    characters, line separators, display controls, lone surrogates) is
    written as an escape, so a name cannot split the message over two lines
    or reorder it; the rest stays as written. A real newline and a literal
    backslash and ``n`` both show as ``\\n``, as a path is shown, not parsed.
    A name holding a single quote is shown in double quotes (as ``repr``
    does), or with the quote escaped when it holds both, so it cannot close
    the quotes early and add text that reads as another field.
    """
    raw = os.fspath(source)
    if isinstance(raw, bytes):
        # Not os.fsdecode(): on Windows it is strict and raises on a byte
        # the file system encoding cannot decode.
        raw = raw.decode(sys.getfilesystemencoding(), "surrogateescape")
    text = escape_controls(raw)
    if "'" in text:
        if '"' not in text:
            return f'"{text}"'
        text = text.replace("'", "\\'")
    return f"'{text}'"
