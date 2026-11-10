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

__all__ = [
    "in_remote_clone",
    "reading_remote_clone",
    "remote_clone_root",
    "remote_clone_trusted",
]


class _Block:  # pylint: disable=too-few-public-methods
    """One open :func:`reading_remote_clone` block, known by identity."""

    __slots__ = ("root", "trust_model_files")

    def __init__(self, root: str | None, trust_model_files: bool) -> None:
        self.root = root
        self.trust_model_files = trust_model_files


#: The open blocks, the last entered last.
_BLOCKS: Final[contextvars.ContextVar[tuple[_Block, ...]]] = contextvars.ContextVar(
    "pitloom_remote_clone_blocks", default=()
)


@contextlib.contextmanager
def reading_remote_clone(
    root: str | None = None, *, trust_model_files: bool = False
) -> Iterator[None]:
    """Mark the reads within as those of a temporary clone whose root
    directory is *root* (``None``: not known), so the warning for a Git LFS
    pointer left unread tells the user to clone with Git LFS instead of to
    pull, and no file out of the clone is read (:func:`remote_clone_root`).
    With *trust_model_files* the user vouches for the clone's model files, so
    the model readers a hostile file could crash or hang are run on them
    (:func:`remote_clone_trusted`). On exit, by any route and in any order,
    only this block's entry is removed."""
    block = _Block(root, trust_model_files)
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


def remote_clone_trusted() -> bool:
    """Whether the last entered :func:`reading_remote_clone` block still
    open was entered with *trust_model_files*; ``False`` outside one. Only
    the innermost block decides."""
    blocks = _BLOCKS.get()
    return blocks[-1].trust_model_files if blocks else False
