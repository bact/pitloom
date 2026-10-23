# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The "has no effect" warning shows a user-given subject safely."""

from __future__ import annotations

import logging

import pytest

from pitloom.core.no_effect import warn_no_effect


@pytest.mark.parametrize(
    ("subject", "shown"),
    [
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
)
def test_the_subject_is_masked_and_on_one_line(
    caplog: pytest.LogCaptureFixture, subject: str, shown: str
) -> None:
    with caplog.at_level(logging.WARNING):
        warn_no_effect("Build: ", subject, ("--allow-build",), "for a repository")
    assert [r.getMessage() for r in caplog.records] == [
        f"Build: {shown}: --allow-build has no effect for a repository"
    ]
    assert "SECRET" not in caplog.text
