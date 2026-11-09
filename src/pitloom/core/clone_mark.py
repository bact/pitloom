# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The mark of the reads of a temporary clone of a remote repository: whether
the run is within one (:func:`in_remote_clone`) and the clone's root
(:func:`remote_clone_root`), nothing out of which is read.

The mark is a stack of open blocks in a context variable: a block left out
of order (enter A, enter B, leave A) removes its own entry only, so the
block still open stays marked, with its own root. The mark belongs to the
calling thread's context alone.

See also: :mod:`pitloom.core.path_confine` (the reads it confines),
:mod:`pitloom.core.lfs_pointer` (the advice for a pointer left unread).
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from typing import Final

__all__ = ["in_remote_clone", "reading_remote_clone", "remote_clone_root"]


class _Block:  # pylint: disable=too-few-public-methods
    """One open :func:`reading_remote_clone` block, known by identity."""

    __slots__ = ("root",)

    def __init__(self, root: str | None) -> None:
        self.root = root


#: The open blocks, the last entered last.
_BLOCKS: Final[contextvars.ContextVar[tuple[_Block, ...]]] = contextvars.ContextVar(
    "pitloom_remote_clone_blocks", default=()
)


@contextlib.contextmanager
def reading_remote_clone(root: str | None = None) -> Iterator[None]:
    """Mark the reads within as those of a temporary clone whose root
    directory is *root* (``None``: not known), so the warning for a Git LFS
    pointer left unread tells the user to clone with Git LFS instead of to
    pull, and no file out of the clone is read (:func:`remote_clone_root`).
    On exit, by any route and in any order, only this block's entry is
    removed."""
    block = _Block(root)
    _BLOCKS.set((*_BLOCKS.get(), block))
    try:
        yield
    finally:
        _BLOCKS.set(tuple(open_ for open_ in _BLOCKS.get() if open_ is not block))


def in_remote_clone() -> bool:
    """Whether the run is within :func:`reading_remote_clone`: it reads a
    temporary clone of a remote repository, whose files were downloaded."""
    return bool(_BLOCKS.get())


def remote_clone_root() -> str | None:
    """The root directory of the clone of the last entered
    :func:`reading_remote_clone` block still open, nothing out of which is
    read; ``None`` outside one, or when not known (the folder read is the
    bound then)."""
    blocks = _BLOCKS.get()
    return blocks[-1].root if blocks else None
