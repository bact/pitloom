# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.project._pyproject_deep`: a
``[project]`` requirement over the marker-nesting cap held out of
``pyproject-metadata``'s parse and put back in place.

See also: tests/test_deep_marker_surfaces.py (every route).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project.pyproject import read_pyproject
from tests._deep_marker import DEEP_REQUIREMENT

_DEEP = DEEP_REQUIREMENT


@pytest.mark.parametrize("quiet", [False, True], ids=["warns", "quiet"])
def test_a_deep_requirement_is_put_back_in_place(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, quiet: bool
) -> None:
    """A required one back at its index, refused as not PEP 508 later; an
    extra's skipped as one that is not PEP 508, with its ``WARNING:``, as
    on every route; one cap ``WARNING:`` for the text; *quiet* silences
    them."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "1.0"\n'
        f"dependencies = ['alpha', '{_DEEP}', 'beta', '{_DEEP}']\n"
        f"[project.optional-dependencies]\nx = ['{_DEEP}', 'gamma']\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        metadata, _ = read_pyproject(pyproject, quiet=quiet)
    assert metadata.dependencies == [
        "alpha", _DEEP, "beta", _DEEP, 'gamma; extra == "x"'
    ]  # fmt: skip
    capped = [m for m in caplog.messages if "marker-nesting cap" in m]
    skipped = [m for m in caplog.messages if m.startswith("Skipping extra entry")]
    assert (len(capped), len(skipped)) == ((0, 0) if quiet else (1, 1))
