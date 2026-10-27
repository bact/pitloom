# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""JSON texts that say the same (``_fragments_equal``), and the merge that
uses it: a respelling is no conflict, for any property, in any order.

See also: tests/assemble/test_fragments_generated.py (the generated-value
fold, which uses the same comparison).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_equal import same_json
from pitloom.assemble.spdx3._fragments_props import _merge_scalar
from tests.assemble.test_fragments_generated import _base, _levels, _merge


@pytest.mark.parametrize(
    ("old", "new", "same"),
    [
        pytest.param('{"a":1,"b":[1,2]}', '{"b":[1,2],"a":1}', True, id="key-order"),
        pytest.param("[1,2]", "[ 1, 2 ]", True, id="spacing"),
        pytest.param("[1,2]", "[2,1]", False, id="array-order"),
        pytest.param('{"n":1}', '{"n":1.0}', False, id="int-vs-float"),
        pytest.param('{"n":1}', '{"n":true}', False, id="number-vs-boolean"),
        pytest.param('{"a":1}', '{"a":1,"b":2}', False, id="key-more"),
        pytest.param('{"a":1,"b":2}', '{"a":1}', False, id="key-less"),
        pytest.param("[1e400]", "[2e999]", False, id="float-overflow"),
        pytest.param("[0.1]", "[0.10000000000000000001]", False, id="float-precision"),
        pytest.param('{"a":1}', '{"a":2,"a":1}', False, id="repeated-key"),
        pytest.param('["\\ud800"]', '[ "\\ud800"]', True, id="lone-surrogate"),
        pytest.param('["\ud800"]', '[ "\ud800"]', True, id="raw-lone-surrogate"),
        pytest.param('["\\u0041"]', '["A"]', True, id="escape-spelling"),
        pytest.param("[-0]", "[0]", True, id="negative-zero-int"),
        pytest.param("[-0.0]", "[0.0]", False, id="negative-zero-float"),
        # a long number with a fraction is kept as its text: no integer
        # conversion, so it folds (a long integer depends on the interpreter's
        # digit limit and is left untested)
        pytest.param(
            "[" + "9" * 5000 + ".5]", "[ " + "9" * 5000 + ".5]", True, id="long-float"
        ),
        pytest.param("not json", "not json ", False, id="not-json"),
        pytest.param("1", " 1", False, id="scalar-number"),
        pytest.param("true", "\ntrue", False, id="scalar-boolean"),
        pytest.param('"ab"', ' "ab"', False, id="scalar-string"),
        pytest.param("null", " null", False, id="scalar-null"),
        pytest.param("[NaN]", "[ NaN]", False, id="nan-is-no-json"),
        pytest.param("[Infinity]", "[ Infinity]", False, id="infinity-is-no-json"),
        pytest.param('["1.0"]', "[1.0]", False, id="string-vs-float"),
        pytest.param(" [1]", "[1] ", True, id="blank-around"),
        pytest.param(
            "[" * 64 + "1" + "]" * 64, "[" * 64 + " 1" + "]" * 64, True, id="at-cap"
        ),
        pytest.param(
            "[" * 65 + "1" + "]" * 65, "[" * 65 + " 1" + "]" * 65, False, id="over-cap"
        ),
        pytest.param(
            "[[]," + "[" * 63 + "1" + "]" * 64,
            "[[], " + "[" * 63 + "1" + "]" * 64,
            True,
            id="64-deep-65-brackets",
        ),
        pytest.param(
            "[" + "{}," * 70 + "1]", "[" + "{}, " * 70 + "1]", True, id="wide"
        ),
        pytest.param(
            '{"a":' * 65 + "1" + "}" * 65,
            '{"a": ' * 65 + "1" + "}" * 65,
            False,
            id="objects-over-cap",
        ),
        pytest.param(
            '["\\"' + "[" * 80 + '"]',
            '["\\"' + "[" * 80 + '" ]',
            True,
            id="brackets-after-escaped-quote",
        ),
        pytest.param(
            "[" * 200_000 + "]" * 200_000,
            "[" * 200_000 + "] " + "]" * 199_999,
            False,
            id="too-deep-to-read",
        ),
    ],
)
def test_same_json(old: str, new: str, same: bool) -> None:
    """Only the same JSON in another spelling is the same; the comparison is
    exact (numbers, booleans, floats as text, repeated keys) and bounded."""
    assert same_json(old, new) is same


_INFO = '{"outputs":[{"name":"x"}]}'
_RESPELT = '{ "outputs": [ {"name": "x"} ] }'


@pytest.mark.parametrize("order", ["CR", "RC"])
@pytest.mark.parametrize("generated", [False, True], ids=["read", "generated"])
def test_a_respelt_copy_of_a_value_is_no_conflict_in_any_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, order: str, generated: bool
) -> None:
    """A fragment that holds the curated JSON in other spacing warns of no
    conflict, whether the base value was generated (then replaced) or not."""
    methods: dict[str, str | None] = {
        "outputs": "derived_from_format" if generated else None
    }
    base = _base(methods)
    if not generated:  # the base already holds the curated value
        for obj in base.object_set.objects:
            if hasattr(obj, "ai_informationAboutApplication"):
                obj.ai_informationAboutApplication = _INFO
    curated = {"ai_informationAboutApplication": _INFO}
    respelt = {"ai_informationAboutApplication": _RESPELT}
    fragments: dict[str, dict[str, Any]] = {"C": curated, "R": respelt}
    model, records, _ = _merge(tmp_path, caplog, base, [fragments[c] for c in order])
    # The spelling that comes first stays: the base's, or (a generated base
    # value yielding) the first fragment's.
    first = _INFO if not generated or order[0] == "C" else _RESPELT
    assert model["ai_informationAboutApplication"] == first
    assert logging.WARNING not in _levels(records)


def test_a_scalar_that_reads_as_json_is_still_a_conflict(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Only an object or array folds: a version ``1`` and `` 1`` are two texts,
    kept as before with the conflict warning."""
    model, records, _ = _merge(
        tmp_path,
        caplog,
        _base({}),
        [{"software_packageVersion": "1"}, {"software_packageVersion": " 1"}],
    )
    assert logging.WARNING in _levels(records)
    assert model["software_packageVersion"] == "1"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (1, 2),
        (
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2027, 1, 1, tzinfo=timezone.utc),
        ),
        ("[1]", 1),
        (1, "[1]"),
    ],
    ids=["int", "datetime", "text-vs-number", "number-vs-text"],
)
def test_a_differing_value_that_is_no_text_is_a_conflict(
    caplog: pytest.LogCaptureFixture, old: object, new: object
) -> None:
    """Non-text values go to the usual conflict warning, not to the JSON
    comparison (which reads text only)."""
    element = spdx3.software_Package(spdxId="https://example.org/e")
    with caplog.at_level(logging.WARNING):
        _merge_scalar(element, "x", old, new)
    assert "conflicting" in caplog.text
