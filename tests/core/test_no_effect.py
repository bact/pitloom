# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The "has no effect" warning shows a user-given subject safely."""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from pitloom.core.no_effect import warn_no_effect

pytestmark = pytest.mark.platform


@pytest.mark.parametrize(
    ("subject", "shown"),
    [
        # A URL a path collapsed: one separator, no "://".
        ("ftp:/u:SECRET@h/x.whl", "ftp:/***:***@h/x.whl"),
        ("ftp:\\u:SECRET@h\\x.whl", "ftp:\\***:***@h\\x.whl"),
        (PurePosixPath("ftp://u:SECRET@h/x.whl"), "ftp:/***:***@h/x.whl"),
        (PureWindowsPath("ftp://u:SECRET@h/x.whl"), "ftp:\\***:***@h\\x.whl"),
        (Path("https://h/x?token=SECRET"), None),
        (
            "https://user:SECRET@gitlab.example/g/p",
            "https://***:***@gitlab.example/g/p",
        ),
        ("https://a:b?c#d@host/x", "https://***:***@host/x"),
        ("https://u:SEC RET@github.com/o/r", "https://***:***@github.com/o/r"),
        ("https://u:SEC\nRET@github.com/o/r", "https://***:***@github.com/o/r"),
        ("https://h/r?private_token=SECRET", "https://h/r?private_token=***"),
        ("dir/with\nINFO: forged", "'dir/with\\nINFO: forged'"),
        ("plain/path", "plain/path"),
    ],
    ids=["posix-collapsed", "windows-collapsed", "posix-path", "windows-path"]
    + ["native-path", "userinfo", "question-mark", "space", "newline", "query"]
    + ["forged-line", "plain"],
)
def test_the_subject_is_masked_and_on_one_line(
    caplog: pytest.LogCaptureFixture, subject: object, shown: str | None
) -> None:
    """A URL given as a path is masked whatever the path made of its
    ``//``: a subject without ``://`` is a URL too."""
    with caplog.at_level(logging.WARNING):
        warn_no_effect(subject, ("--allow-build",), "for a repository", build=True)
    messages = [r.getMessage() for r in caplog.records]
    if shown is not None:
        assert messages == [
            f"Build: {shown}: --allow-build has no effect for a repository"
        ]
    assert len(messages) == 1 and "SECRET" not in caplog.text
