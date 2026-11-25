# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A value outside its field's shape is a caller's bug, never a user's
error: the catalogue's writers raise
:class:`~pitloom.core.internal_error.InternalError` (still a
``ValueError``), which no code and no ``except`` for a bad input takes for
one.

See also: tests/messages/test_messages_field_writers.py.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.messages._field_writers import failure_text, plain_text, whole
from pitloom.messages._input_not_found import INPUT_LINE, INPUT_NOT_FOUND
from pitloom.messages._templates import render, written
from pitloom.messages.options import namespace_invalid


@pytest.mark.parametrize(
    "call",
    [
        lambda: written("FILE=%(file)s", {"file": ""}),
        lambda: written("FILE=%(file)s", {"file": 5}),
        lambda: written("FILE=%(file)s", {}),
        lambda: render("FILE=%(file)s", {"file": b"x"}),
        lambda: INPUT_LINE.render({"input": "no kind", "path": "x"}),
        lambda: INPUT_NOT_FOUND.line_for("ERROR", ["nope"]),
        lambda: INPUT_NOT_FOUND.line_for("WARNING", ["input", "path"], INPUT_LINE),
        lambda: plain_text(5),
        lambda: whole(True),
        lambda: failure_text("text"),
        lambda: namespace_invalid("urn:x", "no such problem"),
    ],
    ids=[
        "empty-file",
        "int-file",
        "missing-field",
        "bytes-file",
        "unknown-kind",
        "no-line",
        "not-its-line",
        "plain-text",
        "whole-bool",
        "failure-text",
        "namespace",
    ],
)
def test_out_of_shape_value_is_internal(call: Callable[[], object]) -> None:
    with pytest.raises(InternalError):
        call()
