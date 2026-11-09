# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found``: each line reads back as its entry, the error is a
:class:`FileNotFoundError` that keeps its code through a copy or a pickle,
and a caller names which of its four lines it says.

See also: tests/extract/test_model_target.py (a model file named on its
own) and tests/extract/remote/test_git_fetch_models.py (a Git URL's file).
"""

from __future__ import annotations

import copy
import pickle  # nosec B403

import pytest

from pitloom.messages import (
    GIT_FILE_IS_LINK_LINE,
    GIT_FILE_NOT_FOUND_LINE,
    GIT_FOLDER_NOT_FOUND_LINE,
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
    CodedFileNotFoundError,
    Line,
    code_of,
    trusted_message,
)
from tests._message_drift import raised_as


@pytest.mark.parametrize(
    ("line", "text"),
    [
        (MODEL_FILE_NOT_FOUND_LINE, "Model file not found: 'a b.gguf'"),
        (
            GIT_FILE_NOT_FOUND_LINE,
            "No file 'a b.gguf' in the repository at that branch.",
        ),
        (
            GIT_FILE_IS_LINK_LINE,
            "File 'a b.gguf' in the repository at that branch is a symbolic "
            "link; links are not followed.",
        ),
        (
            GIT_FOLDER_NOT_FOUND_LINE,
            "No folder 'a b.gguf' in the repository at that branch.",
        ),
    ],
    ids=["model-file", "git-file", "git-link", "git-folder"],
)
def test_each_line_is_a_file_not_found_error_with_its_code(
    line: Line, text: str
) -> None:
    exc = CodedFileNotFoundError(INPUT_NOT_FOUND, line=line, path="a b.gguf")
    assert isinstance(exc, FileNotFoundError) and str(exc) == text
    assert (exc.errno, exc.filename) == (None, None)
    assert raised_as(exc, INPUT_NOT_FOUND)
    for again in (pickle.loads(pickle.dumps(exc)), copy.copy(exc)):  # nosec B301
        assert isinstance(again, CodedFileNotFoundError)
        assert (str(again), code_of(again)) == (text, "input-not-found")


def test_the_caller_names_the_line() -> None:
    """Four lines name a path alone: none is chosen for the caller."""
    with pytest.raises(ValueError, match="4 name of its ERROR lines"):
        raise CodedFileNotFoundError(INPUT_NOT_FOUND, path="a")


@pytest.mark.parametrize(
    "line",
    [
        "ERROR: Model file not found: a.gguf [input-not-found]",
        "WARNING: Model file not found: 'a.gguf' [input-not-found]",
        "ERROR: No file 'a' in the repository at that branch [input-not-found]",
    ],
    ids=["unquoted", "level", "no-period"],
)
def test_a_line_out_of_its_shapes_is_not_trusted(line: str) -> None:
    assert trusted_message(line) is None
