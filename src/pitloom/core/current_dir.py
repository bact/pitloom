# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The current directory, for resolving a path against it, with one coded
error when it is gone or not readable (:func:`current_dir`).

A ``Path.cwd()`` that raises would print a bare ``FileNotFoundError``; an
argparse default that calls it would fail every command while the parser
is built, so a default that needs the current directory is ``None``,
resolved inside the command through :func:`current_dir`.
"""

from __future__ import annotations

from pathlib import Path

from pitloom.messages.files import current_dir_error

__all__ = ["current_dir"]


def current_dir() -> Path:
    """``Path.cwd()``.

    Raises:
        pitloom.messages.CodedValueError: The current directory is gone or
            not readable (``file-unreadable``, ``DIR=.``).
    """
    try:
        return Path.cwd()
    except OSError as exc:
        raise current_dir_error(exc) from exc
