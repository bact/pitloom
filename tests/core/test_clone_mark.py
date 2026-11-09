# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The mark of a temporary clone's reads: one entry per open block, so
blocks that are not strictly nested (enter A, enter B, leave A) leave the
open one marked, and none marked once all are left.

See also: :mod:`tests.extract.remote.test_git_fetch_confined` (the mark
:func:`~pitloom.extract.remote.fetch_git_project` sets).
"""

from __future__ import annotations

import pytest

from pitloom.core.clone_mark import (
    in_remote_clone,
    reading_remote_clone,
    remote_clone_root,
)


def test_blocks_left_out_of_order_leave_the_open_one_marked() -> None:
    first, second = reading_remote_clone("A"), reading_remote_clone("B")
    first.__enter__()  # pylint: disable=unnecessary-dunder-call
    second.__enter__()  # pylint: disable=unnecessary-dunder-call
    assert remote_clone_root() == "B"
    first.__exit__(None, None, None)
    assert in_remote_clone() and remote_clone_root() == "B"
    second.__exit__(None, None, None)
    assert not in_remote_clone() and remote_clone_root() is None


def test_nested_blocks_restore_the_outer_root() -> None:
    with reading_remote_clone("A"):
        with reading_remote_clone(None):
            assert in_remote_clone() and remote_clone_root() is None
        assert remote_clone_root() == "A"
        with reading_remote_clone("A"):
            assert remote_clone_root() == "A"
        assert in_remote_clone() and remote_clone_root() == "A"
    assert not in_remote_clone()


def test_a_block_left_by_an_exception_unmarks() -> None:
    with pytest.raises(LookupError):
        with reading_remote_clone("A"):
            raise LookupError
    assert not in_remote_clone() and remote_clone_root() is None
