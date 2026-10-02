# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a wheel file name and a ``.dist-info`` directory name say, compared
as the ecosystem does.

See also: tests/core/test_wheel_dist_info.py (which directory is the wheel's
own).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest
from packaging.version import Version

from pitloom.core.wheel_dist_info import is_dist_info_of, wheel_name_version
from tests._wheel_damage import WHEEL


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (WHEEL, ("demo", "1.0")),
        ("My.Pkg-1.0.0-1-py3-none-any.whl", ("my-pkg", "1.0.0")),
        ("demo-1.0-py3-none-.whl", ("demo", "1.0")),
        ("demo-1.0-3x-none-any.whl", ("demo", "1.0")),
        ("demo-1.0-py3..py2-none-any.whl", ("demo", "1.0")),
        ("demo-1.0-py3-none-any", None),
        ("demo-1.0-none-any.whl", None),
        ("a-1.0-1-py3-none-any-x.whl", None),
        ("de__mo-1.0-py3-none-any.whl", None),
        ("de mo-1.0-py3-none-any.whl", None),
        ("-1.0-py3-none-any.whl", None),
        ("demo-one-py3-none-any.whl", None),
    ],
    ids=[
        "plain",
        "build-tag",
        "empty-tag",
        "bad-interpreter",
        "empty-tag-component",
        "no-suffix",
        "too-few-parts",
        "too-many-parts",
        "double-underscore",
        "space",
        "no-name",
        "bad-version",
    ],
)
def test_a_wheel_file_name_gives_its_name_and_version_and_nothing_else(
    filename: str, expected: tuple[str, str] | None
) -> None:
    parsed = wheel_name_version(filename)

    assert parsed == (None if expected is None else (expected[0], Version(expected[1])))


@pytest.mark.parametrize(
    ("directory", "name", "version", "expected"),
    [
        ("demo-1.0.dist-info", "demo", "1.0", True),
        ("My.Pkg-1.0.dist-info", "my-pkg", "1.0.0", True),
        # Either may hold a dash: ``foo-bar``, and ``1-2`` is ``1.post2``.
        ("foo-bar-1.0.dist-info", "foo-bar", "1.0", True),
        ("foo_bar-1.0.dist-info", "foo-bar", "1.0", True),
        ("foo-1-2.dist-info", "foo", "1.post2", True),
        ("foo-bar-1.0.dist-info", "foo", "1.0", False),
        ("demo-1.0.dist-info", "demo", "2.0", False),
        ("demo-x.dist-info", "demo", "1.0", False),
        ("demo.dist-info", "demo", "1.0", False),
        ("demo-1.0.egg-info", "demo", "1.0", False),
    ],
)
def test_a_directory_is_the_dist_info_of_a_name_and_version(
    directory: str, name: str, version: str, expected: bool
) -> None:
    assert is_dist_info_of(directory, name, Version(version)) is expected
