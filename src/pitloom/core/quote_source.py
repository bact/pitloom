# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Quote a path or file name for a log or stderr message.

Lives in ``core`` so core modules can use it without importing the
``pitloom.extract`` package (which imports ``core`` back);
``pitloom.extract._extract_utils`` re-exports it.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["quote_source"]

_UNPRINTABLE = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff]")


def quote_source(source: str | Path) -> str:
    """*source* in quotes, written as the OS writes it, on one line.

    ``repr()`` of a :class:`~pathlib.Path` shows ``WindowsPath('D:/a/b')``
    (forward slashes) and of a ``str`` doubles each backslash; neither matches
    ``str(path)``, which a reader of the message looks for. Only control
    characters and lone surrogates are escaped (``\\n``-style), so a name with
    a newline cannot split the message over two lines.
    """
    text = _UNPRINTABLE.sub(lambda match: ascii(match.group())[1:-1], str(source))
    return f"'{text}'"
