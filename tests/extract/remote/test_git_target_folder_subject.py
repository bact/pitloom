# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""A project read of a Git URL that names a file reads the folder, so its
refusal names the folder, not the file.

See also: :mod:`tests.extract.remote.test_git_target_named` (the named file
under the other modes).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.model_target import PROJECT
from pitloom.extract.remote import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.remote.git_target import _folder_subject, resolve_git_target

_REPO = "https://example.com/o/r"


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
