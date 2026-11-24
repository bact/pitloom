# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A project read of a Git URL that names a file reads the folder, so its
refusal names the folder, not the file; the model files it lists are masked
before they are escaped.

See also: :mod:`tests.extract.remote.test_git_target_named` (the named file
under the other modes).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pitloom.extract.model_target import PROJECT
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.remote.git_target import _folder_subject, resolve_git_target

_REPO = "https://example.com/o/r"
#: A file name holding a control character: not on Windows.
_CONTROL_NAMES = sys.platform != "win32"


def test_a_project_refusal_names_the_folder_not_the_missing_file(
    tmp_path: Path,
) -> None:
    """A file with a model suffix beside the missing one, no project."""
    (tmp_path / "other.npy").write_bytes(b"x")
    checkout = GitCheckout(
        str(tmp_path), _REPO, "main", "0" * 40, "m", False, file="nope.npy"
    )
    with checkout.reading(), pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_target(checkout, PROJECT, f"{_REPO}/blob/main/m/nope.npy")
    message = str(excinfo.value)
    assert f"{_REPO}/blob/main/m" in message
    assert "nope.npy" not in message


@pytest.mark.parametrize(
    ("subject", "file", "expected"),
    [
        (f"{_REPO}/blob/main/m/a.npy", "a.npy", f"{_REPO}/blob/main/m"),
        (f"{_REPO}/tree/main/m", "", f"{_REPO}/tree/main/m"),
        (f"{_REPO}?path=/m&version=GBmain", "a.npy", f"{_REPO}?path=/m&version=GBmain"),
    ],
    ids=["file-cut", "no-file", "query-style-kept"],
)
def test_folder_subject(subject: str, file: str, expected: str) -> None:
    assert _folder_subject(subject, file) == expected


_BODY = "T0KEN" + "aB3" * 10 + "x"


@pytest.mark.parametrize(
    ("name", "shown"),
    [
        pytest.param(
            f"m\x1bghp_{_BODY}.gguf",
            "m\\x1bghp_***.gguf",
            marks=pytest.mark.skipif(not _CONTROL_NAMES, reason="control name"),
            id="esc",
        ),
        pytest.param(
            f"m ghp_{_BODY[:18]}\u200b{_BODY[18:]}.gguf", "m ghp_***.gguf", id="zwsp"
        ),
    ],
)
def test_a_listed_model_file_name_is_masked_before_it_is_escaped(
    tmp_path: Path, name: str, shown: str
) -> None:
    """A model file whose name holds a token after an escape character, or
    split by a zero-width space, is listed with the token masked: escaped
    first, the masker would read the token glued to the escape, or in two
    runs of letters."""
    (tmp_path / name).write_bytes(b"x")
    checkout = GitCheckout(str(tmp_path), _REPO, "main", "0" * 40, "m", False)
    with checkout.reading(), pytest.raises(RemoteSourceError) as excinfo:
        resolve_git_target(checkout, PROJECT, f"{_REPO}/tree/main/m")
    assert excinfo.value.pitloom_code == "project-not-found/model-files"
    message = str(excinfo.value)
    assert _BODY[:18] not in message and shown in message
