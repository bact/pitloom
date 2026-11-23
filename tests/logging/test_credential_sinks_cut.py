# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A value cut short for a message is masked before it is cut: a cut that
took away the ``@`` ending a URL's user information once showed the start
of a long token in plain text.

See also: tests/logging/test_credential_sinks_root.py (the masking of a
record for every handler), tests/core/url_masking/test_url_masking_credentials.py.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble.spdx3._dep_scope import DependencyScopes
from pitloom.core.requirements import (
    warn_skipped_dependency,
    warn_skipped_extra_entry,
)
from pitloom.extract._license_resolve import DeclaredResolution, say_resolved
from pitloom.extract.project.reader import read_project
from pitloom.logging_config import EXCERPT_CHARS, excerpt, one_line
from pitloom.messages.authors import authors_text

#: The setup.cfg case reads a project from disk.
pytestmark = pytest.mark.platform

#: The start of a token a cut once showed; the token runs past any cut.
TOKEN_HEAD = "github_pat_11AAAA"
TOKEN = TOKEN_HEAD + "B" * 90
#: A setup.cfg requirement that is not PEP 508, its URL longer than a cut.
LONG = (
    f"private-lib @ git+https://oauth2:{TOKEN}@gitlab.example/o/r.git"
    " ; python_version >> '3.8'"
)


def _shown(text: str) -> None:
    """*text* shows no part of the token, and the cut value kept its
    masked user information."""
    assert TOKEN_HEAD not in text and "BBBB" not in text
    assert "***:***@" in text


@pytest.mark.parametrize("limit", [None, 40, 60, 200], ids=str)
def test_one_line_masks_before_it_cuts(limit: int | None) -> None:
    """``one_line`` cut at *limit* never shows the token, whether the cut
    falls in the user information (40, 60) or after it."""
    assert len(LONG) > 60  # the cut does fall inside the URL
    shown = one_line(ValueError(LONG), limit)
    assert TOKEN_HEAD not in shown and "BBBB" not in shown
    if limit is None or limit >= 60:
        assert "***:***" in shown


def test_excerpt_masks_before_it_cuts() -> None:
    """``excerpt`` cuts the masked text, so its ``...`` follows the host."""
    assert LONG.index("@gitlab") > EXCERPT_CHARS  # unmasked, the cut hides "@"
    shown = excerpt(LONG)
    _shown(shown)
    assert "gitlab.example" in shown


@pytest.mark.parametrize(
    "warn",
    [
        lambda v: warn_skipped_dependency("setup.cfg", v, "not-pep-508"),
        lambda v: warn_skipped_extra_entry("setup.cfg", "dev", v, "not-pep-508"),
        lambda v: DependencyScopes([v], "demo"),
        lambda v: say_resolved(
            v, DeclaredResolution("MIT", "id", (), (), True, "t", ()), "license"
        ),
        lambda v: logging.getLogger("pitloom.t").warning("%s", authors_text([v])),
    ],
    ids=["skipped", "extra-entry", "dep-scope", "license", "author"],
)
def test_each_excerpt_call_site_shows_no_token(
    warn: Callable[[str], object], caplog: pytest.LogCaptureFixture
) -> None:
    """Each kind of warning quoting a declared value shows no token."""
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        warn(LONG)
    assert caplog.records
    _shown(caplog.text)


def test_a_setup_cfg_requirement_warns_without_its_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The reported case: a setup.cfg ``install_requires`` entry that is
    not PEP 508, read through the project reader."""
    (tmp_path / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\n\n"
        f"[options]\ninstall_requires =\n    {LONG}\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.INFO, logger="pitloom"):
        read_project(tmp_path, include_locked_dependencies=False)
    assert "private-lib" in caplog.text  # the entry was warned about
    _shown(caplog.text)
