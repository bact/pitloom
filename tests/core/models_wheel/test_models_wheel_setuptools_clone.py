# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a clone's setuptools configuration leaves out: a file pattern that
can reach out of the clone, and its own apply step when setuptools lacks it.

See also: :mod:`tests.core.models_wheel.test_models_wheel_outside_clone`
(the settings left out, end to end) and
:mod:`tests.core.models_wheel.test_models_wheel_clone_code` (the code).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pitloom.core import _models_wheel_setuptools_clone as setuptools_clone
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import reading_remote_clone


@pytest.mark.parametrize(
    ("pattern", "out"),
    [
        ("/etc/*", True),
        ("~/x", True),
        ("C:x", True),
        ("a/../../b", True),
        ("a\\..\\b", True),
        ("..", True),
        ("*.txt", False),
        ("data/**/*.bin", False),
        ("a..b/.c", False),
    ],
    ids=[
        "absolute",
        "home",
        "drive",
        "dotdot",
        "backslash",
        "up",
        "glob",
        "deep",
        "dots",
    ],
)
def test_a_pattern_that_can_reach_out_is_left_out(
    tmp_path: Path, pattern: str, out: bool
) -> None:
    with reading_remote_clone(str(tmp_path)):
        # pylint: disable-next=protected-access
        ignored = setuptools_clone._Ignored(tmp_path)
        assert ignored.pattern_outside(pattern) is out
    assert ignored.entries == ([pattern] if out else [])


def test_a_setuptools_without_its_apply_step_fails_the_discovery() -> None:
    """The step a clone's ``pyproject.toml`` is applied with is setuptools'
    own; one gone from setuptools is said, never guessed."""
    with pytest.raises(InternalError, match="_apply"):
        # pylint: disable-next=protected-access
        setuptools_clone._setuptools_apply(SimpleNamespace())
