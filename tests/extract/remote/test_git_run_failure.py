# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""git's own failure text in a ``git.clone-failed`` error: masked whole
before its ``fatal:``/``error:``/``remote:`` lines are picked, and again
once on one line.

See also: tests/extract/remote/test_git_say_errors.py (the same error from
a real git against a local server).
"""

from __future__ import annotations

import pytest

from pitloom.extract.remote._git_run import _failed, _failure
from pitloom.messages import code_of


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        (
            "fatal: unable to access 'https://u:S3cr\n3tPw99x@h/r/': 403\n",
            "fatal: unable to access 'https://***:***@h/r/': 403",
        ),
        (
            "hint: x\nfatal: https://u:S3cr\r\n3tPw99x@h/r\n",
            "fatal: https://***:***@h/r",
        ),
        ("see https://u:S3cr\n3tPw99x@h/r\n", "see https://***:***@h/r"),
        ("see https://u:S3cr\t3tPw99x@h/r\n", "see https://***:***@h/r"),
    ],
    ids=["fatal-lf", "fatal-crlf", "no-fatal-lf", "no-fatal-tab"],
)
def test_git_failure_masks_before_it_picks_lines(err: str, expected: str) -> None:
    """Lines picked first, a ``fatal:`` line keeps the start of a password
    split by a line break (``https://u:S3cr``); collapsed first, both halves
    read as two words."""
    error = _failed("ls-remote", err, 128)
    text = str(error)
    assert "S3cr" not in text and "3tPw99x" not in text
    assert text == f"git ls-remote: {expected}; nothing fetched"
    assert code_of(error) == "git-repository-unusable"


def test_git_failure_with_no_text_names_the_exit_status() -> None:
    assert "git exited 128" in str(_failed("ls-remote", " \n", 128))


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        (
            "fatal: https://u:hunter2Qz\xa09pW7xK4v@h/x",
            "fatal: https://***:***@h/x",
        ),
        ("X-Api-Key:\nhunter2Qz9pW7xK\n", "X-Api-Key: ***"),
    ],
    ids=["nbsp-password", "header-value-next-line"],
)
def test_git_failure_masks_what_the_collapse_splits_or_joins(
    err: str, expected: str
) -> None:
    """A no-break space inside a password is a space once collapsed, which
    would show both halves; a header's value on the next line reads as its
    value only once the lines are joined, so the joined text is masked
    again."""
    shown = _failure(err, 1)
    assert "hunter2Qz" not in shown and "9pW7xK" not in shown
    assert shown == expected
