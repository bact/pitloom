# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The current directory, for resolving a path against it, with one coded
error when it is gone or not readable (:func:`current_dir`,
:func:`absolute_path`).

A ``Path.cwd()`` that raises would print a bare ``FileNotFoundError``; an
argparse default that calls it would fail every command while the parser
is built, so a default that needs the current directory is ``None``,
resolved inside the command through :func:`current_dir`. A path that may be
relative is made absolute through :func:`absolute_path` before
``Path.resolve()``, ``Path.absolute()`` or :func:`os.path.abspath`, which
read the current directory too and would raise the bare error.
"""

from __future__ import annotations

import os
from pathlib import Path

from pitloom.messages.files import current_dir_error

__all__ = ["absolute_path", "current_dir"]


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


def absolute_path(path: str | os.PathLike[str]) -> Path:
    """*path* joined to :func:`current_dir` when it is relative, as
    ``Path.absolute()`` makes it (lexically: no ``..`` collapsed, no link
    followed); an absolute *path* as it is, the current directory never
    read.

    Raises:
        pitloom.messages.CodedValueError: *path* is relative and the current
            directory is gone or not readable (``file-unreadable``,
            ``DIR=.``).
    """
    given = Path(path)
    return given if given.is_absolute() else current_dir() / given
