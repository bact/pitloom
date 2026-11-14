# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_model_file()`` of :mod:`pitloom.extract.model_target` on a named
file whose content is no model: refused as ``model-wrong-format``, in the
words of ``loom model``, naming the file as *shown* says.

See also: tests/extract/test_model_target.py (the rule),
tests/extract/test_model_target_clone.py (a named file and how a refusal names
it) and tests/extract/test_model_target_invariants.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.model_target import read_model_file
from pitloom.messages import code_of
from pitloom.messages.models import MODEL_WRONG_FORMAT

_NOT_A_MODEL = "not an AI model file of a supported format"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("notes.txt", b"plain text, no model magic\n"),
        ("blob.dat", b"\x00\x01\x02\x03" * 8),
        ("empty.dat", b""),
    ],
    ids=["text", "binary", "empty"],
)
@pytest.mark.parametrize("shown", [None, "models/shown.dat"], ids=["path", "shown"])
def test_a_named_file_that_is_no_model_is_refused(
    tmp_path: Path, name: str, content: bytes, shown: str | None
) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(ValueError) as caught:
        read_model_file(path, shown=shown)
    assert code_of(caught.value) == MODEL_WRONG_FORMAT.code
    text = str(caught.value)
    assert _NOT_A_MODEL in text
    assert ("shown.dat" in text) == (shown is not None)
    assert (name in text) == (shown is None)
