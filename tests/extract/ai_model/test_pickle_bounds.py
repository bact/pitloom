# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The bounds on a pickle before fickling sees it: opcodes and decimal
numbers, and what the adapter raises for each.

See also: :mod:`tests.extract.ai_model.formats.test_pickle_walk` (the walk
itself) and :mod:`tests.extract.ai_model.test_model_bounds` (fickling's
side).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import pickle

import pytest

from pitloom.extract.ai_model import _pickle_bounds
from pitloom.extract.ai_model._pickle_bounds import first_pickle
from pitloom.extract.ai_model.limits import ModelLimitExceeded


def test_first_pickle_ends_at_stop() -> None:
    data = pickle.dumps({"a": [1, 2]}, protocol=2)
    assert first_pickle(data + b"\x00junk after the pickle") == data


@pytest.mark.parametrize(
    "data",
    [b"", b"\x80\x02N", b"\x80\x99", b"garbage", b"\x80\x02I12", b"\x80\x02L-"],
    ids=["empty", "no-stop", "bad-proto", "text", "int-cut", "long-cut"],
)
def test_first_pickle_rejects_malformed(data: bytes) -> None:
    """A decimal number cut short by the end of the data is malformed, not
    over a bound."""
    with pytest.raises(ValueError, match="not a well-formed pickle"):
        first_pickle(data)


@pytest.mark.parametrize(
    ("constant", "small", "large", "reason"),
    [
        ("MAX_PICKLE_OPCODES", b"\x80\x02N.", pickle.dumps([1, 2, 3], 2), "opcodes"),
        ("MAX_PICKLE_DECIMAL_DIGITS", b"I12\n.", b"I123456\n.", "5 digits"),
    ],
)
def test_the_adapter_reads_its_constants_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    small: bytes,
    large: bytes,
    reason: str,
) -> None:
    monkeypatch.setattr(_pickle_bounds, constant, 5)
    assert first_pickle(small) == small
    with pytest.raises(ModelLimitExceeded, match=reason):
        first_pickle(large)


@pytest.mark.parametrize(("opcodes", "refused"), [(250_000, False), (250_001, True)])
def test_the_pickle_opcode_cap_is_250k(opcodes: int, refused: bool) -> None:
    """``PROTO``, ``NONE`` repeated, ``STOP``: *opcodes* in all."""
    data = b"\x80\x02" + b"N" * (opcodes - 2) + b"."
    if refused:
        with pytest.raises(ModelLimitExceeded, match="250000 opcodes"):
            first_pickle(data)
    else:
        assert first_pickle(data) == data


def _decimal(code: bytes, text: bytes) -> bytes:
    """``PROTO 2``, ``NONE``, one decimal opcode, ``STOP``. Nothing is
    unpickled, so ``GET``/``PUT`` need no memo."""
    suffix = b"L" if code == b"L" else b""
    return b"\x80\x02N" + code + text + suffix + b"\n."


@pytest.mark.parametrize("code", [b"I", b"L", b"g", b"p"])
@pytest.mark.parametrize("sign", [b"", b"-"])
@pytest.mark.parametrize(("digits", "refused"), [(4300, False), (4301, True)])
def test_a_decimal_number_over_4300_digits_is_refused(
    code: bytes, sign: bytes, digits: int, refused: bool
) -> None:
    """The cap counts digits, so a sign or ``LONG``'s ``L`` does not count
    against it; 4300 is CPython's default ``int_max_str_digits``."""
    data = _decimal(code, sign + b"9" * digits)
    if refused:
        with pytest.raises(ModelLimitExceeded, match="over 4300 digits"):
            first_pickle(data)
    else:
        assert first_pickle(data) == data


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (_decimal(b"I", b"1" + b" " * 4302), "argument over 4302 bytes"),
        (b"\x80\x02L" + b"9" * 5000, "number over 4300 digits"),  # no newline
    ],
    ids=["padded", "unterminated"],
)
def test_decimal_text_past_the_window_is_refused_not_malformed(
    data: bytes, reason: str
) -> None:
    """Only the window is read: a long text of few digits, or a number cut
    short by the end of the data, is still over a bound."""
    with pytest.raises(ModelLimitExceeded, match=reason):
        first_pickle(data)
