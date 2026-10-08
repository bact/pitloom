# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.scalar_text`: the one spelling of a scalar.

See also: :mod:`tests.core.test_ai_metadata` (``source_metadata``) and
:mod:`tests.extract.ai_model.test_gguf_scalar_text` (GGUF float32).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import struct
import subprocess  # nosec B404 -- runs this interpreter on fixed code
import sys
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from pitloom.core.scalar_text import scalar_text, scalar_type

# RFC 8785 Appendix B: IEEE 754 double (big-endian hex) -> JSON spelling.
_RFC8785_APPENDIX_B = [
    ("0000000000000000", "0"),
    ("8000000000000000", "0"),
    ("0000000000000001", "5e-324"),
    ("8000000000000001", "-5e-324"),
    ("7fefffffffffffff", "1.7976931348623157e+308"),
    ("ffefffffffffffff", "-1.7976931348623157e+308"),
    ("4340000000000000", "9007199254740992"),
    ("c340000000000000", "-9007199254740992"),
    ("4430000000000000", "295147905179352830000"),
    ("44b52d02c7e14af5", "9.999999999999997e+22"),
    ("44b52d02c7e14af6", "1e+23"),
    ("44b52d02c7e14af7", "1.0000000000000001e+23"),
    ("444b1ae4d6e2ef4e", "999999999999999700000"),
    ("444b1ae4d6e2ef4f", "999999999999999900000"),
    ("444b1ae4d6e2ef50", "1e+21"),
    ("3eb0c6f7a0b5ed8c", "9.999999999999997e-7"),
    ("3eb0c6f7a0b5ed8d", "0.000001"),
    ("41b3de4355555553", "333333333.3333332"),
    ("41b3de4355555554", "333333333.33333325"),
    ("41b3de4355555555", "333333333.3333333"),
    ("41b3de4355555556", "333333333.3333334"),
    ("41b3de4355555557", "333333333.33333343"),
    ("becbf647612f3696", "-0.0000033333333333333333"),
    ("43143ff3c1cb0959", "1424953923781206.2"),
    # The non-finite rows, which RFC 8785 makes errors: the XSD spellings.
    ("7fffffffffffffff", "NaN"),
    ("7ff0000000000000", "INF"),
    ("fff0000000000000", "-INF"),
]


@pytest.mark.parametrize(
    ("hex_double", "expected"),
    _RFC8785_APPENDIX_B,
    ids=[row[0] for row in _RFC8785_APPENDIX_B],
)
def test_a_double_is_spelt_as_rfc8785_appendix_b(
    hex_double: str, expected: str
) -> None:
    value = struct.unpack(">d", bytes.fromhex(hex_double))[0]
    assert scalar_text(value) == expected
    assert scalar_type(value) == "float"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (-1, "-1"),
        (2**53 - 1, "9007199254740991"),
        (2**53, "9007199254740992"),
        (2**53 + 1, "9007199254740993"),  # not a double: never rounded
        (2**64 - 1, "18446744073709551615"),
        (-(2**63), "-9223372036854775808"),
    ],
)
def test_an_integer_is_decimal_at_any_size(value: int, expected: str) -> None:
    assert scalar_text(value) == expected
    assert scalar_type(value) == "integer"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (100.0, "100"),
        (1e-7, "1e-7"),
        (0.1, "0.1"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (5e-324, "5e-324"),
        (-0.0, "0"),  # the one documented loss: the sign of zero
        (float("nan"), "NaN"),
        (float("inf"), "INF"),
        (float("-inf"), "-INF"),
        (Fraction(1, 4), "0.25"),
    ],
    ids=[
        "integral",
        "exponent",
        "tenth",
        "1e20",
        "1e21",
        "subnormal",
        "negative-zero",
        "nan",
        "inf",
        "negative-inf",
        "fraction",
    ],
)
def test_a_float_is_spelt_as_rfc8785(value: float, expected: str) -> None:
    assert scalar_text(value) == expected
    assert scalar_type(value) == "float"


@pytest.mark.parametrize(
    ("value", "expected"), [(True, "true"), (False, "false")], ids=["true", "false"]
)
def test_a_boolean_is_lowercase_never_an_integer(value: bool, expected: str) -> None:
    assert scalar_text(value) == expected
    assert scalar_type(value) == "boolean"


def test_a_string_is_as_is_and_untyped() -> None:
    assert scalar_text("True") == "True"
    assert scalar_text("") == ""
    assert scalar_type("1") is None


@pytest.mark.parametrize(
    "value",
    [None, [1], {"a": 1}, b"x", 1j, Decimal("0.1")],
    ids=["none", "list", "dict", "bytes", "complex", "decimal"],
)
def test_anything_but_a_string_or_a_scalar_is_refused(value: Any) -> None:
    """``None`` is an absent value: a caller leaves the key out."""
    assert scalar_type(value) is None
    with pytest.raises(TypeError, match="not a scalar"):
        scalar_text(value)


@pytest.mark.parametrize(
    ("make", "expected", "kind"),
    [
        (lambda np: np.bool_(True), "true", "boolean"),
        (lambda np: np.bool_(False), "false", "boolean"),
        (lambda np: np.uint64(2**64 - 1), "18446744073709551615", "integer"),
        (lambda np: np.int8(-5), "-5", "integer"),
        (lambda np: np.float64(1e-7), "1e-7", "float"),
        (lambda np: np.float32(0.5), "0.5", "float"),
        (lambda np: np.float32(1e-6), "9.999999974752427e-7", "float"),  # widened
        (lambda np: np.float16(float("nan")), "NaN", "float"),
        (lambda np: np.str_("x"), "x", None),
    ],
    ids=[
        "bool-true",
        "bool-false",
        "uint64-max",
        "int8",
        "float64",
        "float32-exact",
        "float32-widened",
        "float16-nan",
        "str",
    ],
)
def test_a_numpy_scalar_is_spelt_as_its_python_value(
    make: Any, expected: str, kind: str | None
) -> None:
    numpy = pytest.importorskip("numpy")
    value = make(numpy)
    assert scalar_text(value) == expected
    # pylint: disable-next=unidiomatic-typecheck
    assert type(scalar_text(value)) is str  # never a numpy.str_ subclass
    assert scalar_type(value) == kind


def test_a_stand_in_numpy_module_without_bool_is_harmless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "numpy", object())
    assert scalar_text(True) == "true"
    assert scalar_type("x") is None


def test_numpy_is_never_imported() -> None:
    """NumPy is optional (the ``ai`` extra): the spelling works without it."""
    code = (
        "import sys; sys.modules['numpy'] = None\n"
        "from pitloom.core.scalar_text import scalar_text\n"
        "print(scalar_text(True), scalar_text(1e-7), scalar_text(2**64))\n"
        "assert sys.modules['numpy'] is None\n"
    )
    result = subprocess.run(  # nosec B603 -- this interpreter, fixed code
        [sys.executable, "-c", code], capture_output=True, check=True
    )
    assert result.stdout.decode().split() == ["true", "1e-7", "18446744073709551616"]
