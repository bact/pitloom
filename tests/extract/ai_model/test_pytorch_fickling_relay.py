# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What fickling writes to stderr while it reads a pickle: its own words,
relayed after ``fickling: `` on one ``WARNING:`` line, uncoded (the text is
fickling's), a credential masked, cut, escaped, never a forged line or
code.

See also: tests/extract/ai_model/test_model_bounds.py (the cut's bound).
"""

from __future__ import annotations

import ast
import io
import logging
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from pitloom.extract.ai_model.pytorch import FICKLING_PREFIX, _fickling_get_top_class
from pitloom.messages import trusted_message

fickle = pytest.importorskip("fickling.fickle")

_SECRET = "s3cr3t-value"
_NOISE = {
    "newline-forged-line": "parse\nWARNING: forged [config-invalid]\n",
    "ansi": "\x1b[31mred\x1b[0m",
    "url-credential": f"fetching https://user:{_SECRET}@h.example/x\n",
    "forged-code": "careful [model-unreadable]",
}


@pytest.mark.parametrize("noise", _NOISE.values(), ids=_NOISE.keys())
def test_ficklings_stderr_is_one_relayed_line(
    noise: str,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def noisy(_stream: io.BytesIO) -> object:
        sys.stderr.write(noise)
        return SimpleNamespace(ast=ast.parse("result = Foo()"))

    caplog.set_level(logging.WARNING)
    with mock.patch.object(fickle.Pickled, "load", side_effect=noisy):
        assert _fickling_get_top_class(io.BytesIO(b"\x80\x02N.")) == "Foo"
    assert capsys.readouterr().err == ""
    (record,) = caplog.records
    text = record.getMessage()
    assert text.startswith(FICKLING_PREFIX)
    assert "\n" not in text and "\x1b" not in text and _SECRET not in text
    assert getattr(record, "pitloom_code", None) is None
    assert trusted_message(f"WARNING: {text}") is None


def test_no_stderr_says_nothing(caplog: pytest.LogCaptureFixture) -> None:
    def quiet(_stream: io.BytesIO) -> object:
        sys.stderr.write(" \n\t")
        return SimpleNamespace(ast=ast.parse("result = Foo()"))

    caplog.set_level(logging.WARNING)
    with mock.patch.object(fickle.Pickled, "load", side_effect=quiet):
        _fickling_get_top_class(io.BytesIO(b"\x80\x02N."))
    assert not caplog.records
