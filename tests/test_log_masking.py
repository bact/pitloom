# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :func:`pitloom.log_masking.masked_lines`.

See also: tests/logging/ (the record factory and the sinks), and the tests
of each caller that keeps some of the lines:
tests/core/models_wheel/test_models_wheel_setuptools_relay_edges.py,
tests/core/models_wheel/test_models_wheel_build_subprocess_clean.py,
tests/extract/test_env.py, tests/extract/remote/test_git_run_failure.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pitloom import log_masking
from pitloom.log_masking import UNSHOWN_MESSAGE, masked_lines


@pytest.mark.parametrize("brk", ["\n", "\r\n", "\u2028"], ids=["lf", "crlf", "u2028"])
def test_masked_lines_masks_before_it_splits(brk: str) -> None:
    """Split first, neither piece of the password reads as user information."""
    lines = masked_lines(f"a\nsee https://u:S3cr{brk}3tPw99x@h/x\nb")
    assert not any("S3cr" in ln or "3tPw99x" in ln for ln in lines)
    assert lines == ["a", "see https://***:***@h/x", "b"]


def test_masked_lines_never_raises() -> None:
    with patch.object(
        log_masking, "masked_given_path", side_effect=RecursionError, autospec=True
    ):
        assert masked_lines("x\ny") == [UNSHOWN_MESSAGE]
