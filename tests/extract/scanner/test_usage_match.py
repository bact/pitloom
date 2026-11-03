# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``model_usage``, ``_usage_table`` and ``_usage_match``.

Pure functions only -- no file I/O or AST parsing.

See also: :mod:`tests.extract.scanner.test_usage_ast` (AST visitor tests) and
:mod:`tests.extract.scanner.test_usage_unparseable` (unparseable file warnings).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pytest

from pitloom.core.model_usage import (
    ModelUsage,
    UsageAccess,
    combine_access,
    merge_usages,
)
from pitloom.extract._usage_match import UsageModel, matches
from pitloom.extract._usage_table import (
    access_of_mode,
    access_of_name,
    is_mention_call,
)

_MODEL = UsageModel("model.ftz", ("pkg/data/model.ftz", "src/pkg/data/model.ftz"))


# --- combine_access and merge_usages ----------------------------------------


@pytest.mark.parametrize(
    ("inputs", "expected"),
    [
        ([UsageAccess.READ], UsageAccess.READ),
        ([UsageAccess.WRITE], UsageAccess.WRITE),
        ([UsageAccess.UNKNOWN], UsageAccess.UNKNOWN),
        ([UsageAccess.READ_WRITE], UsageAccess.READ_WRITE),
        ([UsageAccess.READ, UsageAccess.WRITE], UsageAccess.READ_WRITE),
        ([UsageAccess.WRITE, UsageAccess.READ], UsageAccess.READ_WRITE),
        ([UsageAccess.READ, UsageAccess.UNKNOWN], UsageAccess.READ),
        ([UsageAccess.WRITE, UsageAccess.UNKNOWN], UsageAccess.WRITE),
        (
            [UsageAccess.READ, UsageAccess.WRITE, UsageAccess.UNKNOWN],
            UsageAccess.READ_WRITE,
        ),
        ([UsageAccess.READ_WRITE, UsageAccess.UNKNOWN], UsageAccess.READ_WRITE),
    ],
    ids=[
        "read",
        "write",
        "unknown",
        "rw",
        "r+w",
        "w+r",
        "r+u",
        "w+u",
        "r+w+u",
        "rw+u",
    ],
)
def test_combine_access(inputs: list[UsageAccess], expected: UsageAccess) -> None:
    assert combine_access(inputs) == expected


def test_combine_access_empty_raises() -> None:
    with pytest.raises(ValueError, match="no access"):
        combine_access([])


def test_merge_usages_sorts_and_combines_per_path() -> None:
    usages = [
        ModelUsage("pkg/b.py", UsageAccess.UNKNOWN),
        ModelUsage("pkg/a.py", UsageAccess.READ),
        ModelUsage("pkg/a.py", UsageAccess.WRITE),
        ModelUsage("pkg/b.py", UsageAccess.WRITE),
    ]
    assert merge_usages(usages) == [
        ModelUsage("pkg/a.py", UsageAccess.READ_WRITE),
        ModelUsage("pkg/b.py", UsageAccess.WRITE),
    ]


# --- _usage_table -----------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("r", UsageAccess.READ),
        ("rb", UsageAccess.READ),
        ("rt", UsageAccess.READ),
        ("w", UsageAccess.WRITE),
        ("wb", UsageAccess.WRITE),
        ("wt", UsageAccess.WRITE),
        ("a", UsageAccess.WRITE),
        ("ab", UsageAccess.WRITE),
        ("x", UsageAccess.WRITE),
        ("xb", UsageAccess.WRITE),
        ("r+", UsageAccess.READ_WRITE),
        ("rb+", UsageAccess.READ_WRITE),
        ("w+", UsageAccess.READ_WRITE),
        ("a+b", UsageAccess.READ_WRITE),
        ("r:xz", UsageAccess.READ),
        ("r|gz", UsageAccess.READ),
        ("w:xz", UsageAccess.WRITE),
        ("", UsageAccess.UNKNOWN),
        ("b", UsageAccess.UNKNOWN),
        ("readonly", UsageAccess.UNKNOWN),
    ],
)
def test_access_of_mode(mode: str, expected: UsageAccess) -> None:
    assert access_of_mode(mode) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("load", UsageAccess.READ),
        ("load_model", UsageAccess.READ),
        ("load_file", UsageAccess.READ),
        ("read_bytes", UsageAccess.READ),
        ("read_text", UsageAccess.READ),
        ("from_pretrained", UsageAccess.READ),
        ("restore", UsageAccess.READ),
        ("InferenceSession", UsageAccess.READ),
        ("Booster", UsageAccess.READ),
        ("Interpreter", UsageAccess.READ),
        ("Llama", UsageAccess.READ),
        ("safe_open", UsageAccess.READ),
        ("save", UsageAccess.WRITE),
        ("save_model", UsageAccess.WRITE),
        ("save_file", UsageAccess.WRITE),
        ("save_pretrained", UsageAccess.WRITE),
        ("write_bytes", UsageAccess.WRITE),
        ("write_text", UsageAccess.WRITE),
        ("dump", UsageAccess.WRITE),
        ("export", UsageAccess.WRITE),
        ("to_onnx", UsageAccess.WRITE),
        ("exists", UsageAccess.UNKNOWN),
        ("stat", UsageAccess.UNKNOWN),
    ],
)
def test_access_of_name(name: str, expected: UsageAccess) -> None:
    assert access_of_name(name) == expected


@pytest.mark.parametrize(
    ("name", "mention"),
    [
        ("print", True),
        ("info", True),
        ("warning", True),
        ("warn", True),
        ("error", True),
        ("debug", True),
        ("FileNotFoundError", True),
        ("ValueError", True),
        ("RuntimeWarning", True),
        ("SystemExit", True),
        ("load", False),
        ("open", False),
    ],
)
def test_is_mention_call(name: str, mention: bool) -> None:
    assert is_mention_call(name) is mention


# --- _usage_match -----------------------------------------------------------


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("model.ftz", True),
        ("./model.ftz", True),
        ("data/model.ftz", True),
        ("pkg/data/model.ftz", True),
        ("src/pkg/data/model.ftz", True),
        ("data\\model.ftz", True),
        ("pkg\\data\\model.ftz", True),
        ("/abs/checkout/pkg/data/model.ftz", True),
        ("C:\\work\\src\\pkg\\data\\model.ftz", True),
        ("~/work/pkg/data/model.ftz", True),
        ("../data/model.ftz", True),
        ("data/sub/../model.ftz", True),
        ("%s/model.ftz", True),
        ("{}/data/model.ftz", True),
        ("wrong/{}/../data/model.ftz", True),
        ("other/model.ftz", False),
        ("pkg/other/model.ftz", False),
        ("extra/src/pkg/data/model.ftz", False),
        ("{}/extra/src/pkg/data/model.ftz", False),
        ("wrong/{}/../other/model.ftz", False),
        ("/abs/other/model.ftz", False),
        ("C:\\work\\other\\model.ftz", False),
        ("/model.ftz", False),
        ("C:\\model.ftz", False),
        ("{}/other/model.ftz", False),
        ("my_model.ftz", False),
        ("model.ftz.bak", False),
        ("saved model.ftz to disk", False),
        ("model.ftz/extra", False),
        ("model.ftz/", False),
        ("", False),
        ("/", False),
    ],
)
def test_matches_path_shapes_and_directory_suffixes(
    literal: str, expected: bool
) -> None:
    assert matches(literal, _MODEL) is expected


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("model.ftz", True),
        ("/model.ftz", True),
        ("C:\\model.ftz", True),
        ("other/model.ftz", False),
        ("/abs/other/model.ftz", False),
        ("C:\\other\\model.ftz", False),
    ],
)
def test_matches_root_level_model(literal: str, expected: bool) -> None:
    root_model = UsageModel("model.ftz", ("model.ftz",))
    assert matches(literal, root_model) is expected
