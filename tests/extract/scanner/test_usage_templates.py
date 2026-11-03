# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge cases of ``str.format`` / ``%`` templates, path joining and matching
(:mod:`pitloom.extract._usage_match`) and ``usage_models`` found by
mutation testing.

See also: :mod:`tests.extract.scanner.test_usage_match` (the main cases) and
:mod:`tests.extract.scanner.test_usage_ast_edges`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import sys

import pytest

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.model_usage import UsageAccess
from pitloom.extract._usage_attach import usage_models
from pitloom.extract._usage_match import (
    UsageModel,
    after_first_separator,
    format_template,
    join_path,
    matches,
    percent_template,
)
from pitloom.extract._usage_table import access_of_mode

from ._usage_helpers import accesses

_ONE = ("model.pkl",)


@pytest.mark.parametrize(
    ("template", "args", "expected"),
    [
        ("{[0]}/{}", ["a", "model.pkl"], "model.pkl"),
        ("{1}", ["a"], None),
        ("{:{}}/{}", ["a", "b", "model.pkl"], None),
        ("{.real}", ["model.pkl"], None),
        ("{:s}", ["d/model.pkl"], "d/model.pkl"),
        ("{!s}", ["d/model.pkl"], "d/model.pkl"),
        ("{!r}", ["d/model.pkl"], None),
        ("{:>9}", ["d/model.pkl"], None),
        ("{0}/{0}", ["d"], "d/d"),
        ("{", ["d"], None),
    ],
    ids=str,
)
def test_format_template(template: str, args: list[str], expected: str | None) -> None:
    assert format_template(template, args, {}) == expected


@pytest.mark.parametrize(
    ("template", "values", "expected"),
    [
        ("% s/model.pkl", ["a"], "model.pkl"),
        ("%*s/model.pkl", ["5", "x"], "model.pkl"),
        ("%.*f/model.pkl", ["2", "3.14"], "model.pkl"),
        ("%ls/model.pkl", ["d"], "d/model.pkl"),
        ("%()s/model.pkl", ["a"], "model.pkl"),
        ("%X/model.pkl", ["a"], "model.pkl"),
        ("%da/%db/model.pkl", ["1", "2"], "model.pkl"),
        ("%*s/%s", ["5", "x", "model.pkl"], None),
        ("%.3s/model.pkl", ["other"], "model.pkl"),
        ("%-s/model.pkl", ["other"], "model.pkl"),
        ("%s/model.pkl", ["other"], "other/model.pkl"),
        ("", [], None),
        ("100%%/model.pkl", [], "100%/model.pkl"),
    ],
    ids=str,
)
def test_percent_template(
    template: str, values: list[str], expected: str | None
) -> None:
    assert percent_template(template, values) == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("data", "\\abs\\model.pkl", "\\abs\\model.pkl"),
        ("data", "C:/model.pkl", "C:/model.pkl"),
        ("data/", "model.pkl", "data/model.pkl"),
        ("data\\", "model.pkl", "data/model.pkl"),
    ],
    ids=str,
)
def test_join_path(left: str, right: str, expected: str) -> None:
    assert join_path(left, right) == expected


def test_after_first_separator_drops_every_leading_separator() -> None:
    assert after_first_separator("a//model.pkl") == "model.pkl"
    assert after_first_separator("a\\model.pkl") == "model.pkl"
    assert after_first_separator("a/") is None


@pytest.mark.parametrize(
    ("text", "paths", "expected"),
    [
        ("c:/model.pkl", ("a/model.pkl",), False),
        ("~/model.pkl", _ONE, True),
        ("/%s/../model.pkl", _ONE, True),
        ("/%s/../model.pkl", ("data/model.pkl",), True),
        ("/%s/model.pkl", ("data/model.pkl",), True),
        ("data/C:/model.pkl", ("data/model.pkl",), False),
        ("/%s/model.pkl", _ONE, True),
    ],
    ids=str,
)
def test_matches_corners(text: str, paths: tuple[str, ...], expected: bool) -> None:
    assert matches(text, UsageModel("model.pkl", paths)) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("open('%d/model.pkl' % 'other')", {UsageAccess.READ}),
        ("open('%s/model.pkl' % 'other')", set()),
    ],
    ids=str,
)
def test_only_a_bare_percent_s_is_filled(code: str, expected: set[UsageAccess]) -> None:
    assert accesses(code, "model.pkl", ("data/model.pkl",)) == expected


def test_access_of_mode_reads_universal_newlines_only_with_r() -> None:
    assert access_of_mode("rU") is UsageAccess.READ
    assert access_of_mode("U") is UsageAccess.UNKNOWN


def test_usage_models_keeps_a_relative_physical_path_beside_the_relative_one() -> None:
    meta = AiModelMetadata(
        format_info=AiModelFormatInfo(
            model_format=AiModelFormat.ONNX,
            file_name="m.onnx",
            file_path_relative="pkg/m.onnx",
            physical_path="src/pkg/m.onnx",
        )
    )
    assert [m.paths for _, m in usage_models([meta])] == [
        ("pkg/m.onnx", "src/pkg/m.onnx")
    ]


def test_a_field_number_is_a_decimal_digit_as_in_cpython() -> None:
    """``{\u0663}`` is position 3; ``{\u00b2}`` is a keyword, as in ``str.format``."""
    args = ["a", "b", "c", "d/model.pkl"]
    kwargs = {"\u00b2": "k/model.pkl"}
    assert format_template("{\u0663}", args, kwargs) == "d/model.pkl"
    assert format_template("{\u00b2}", args, kwargs) == "k/model.pkl"


@pytest.mark.skipif(
    not hasattr(sys, "set_int_max_str_digits"), reason="no int digit limit"
)
def test_a_field_number_over_the_int_digit_limit_is_not_known() -> None:
    set_limit = sys.set_int_max_str_digits
    old = sys.get_int_max_str_digits()
    set_limit(640)
    try:
        assert format_template("{" + "9" * 1000 + "}/model.pkl", ["a"], {}) == (
            "model.pkl"
        )
    finally:
        set_limit(old)
