# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the build-output line cleaning behind the ``--allow-build``
``WARNING:``/``DEBUG:`` lines.

See also: tests/core/models_wheel/test_models_wheel_build_subprocess.py
(``test_run_build_subprocess_nonzero_exit`` runs the same cleaning on a
real child's output).
"""

from __future__ import annotations

import pytest

from pitloom.core._models_wheel_build_subprocess import _clean_line


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("\x1b[1;31mred\x1b[0m", "red", id="csi"),
        pytest.param("\x9b1mbold", "bold", id="csi_8bit"),
        pytest.param(
            "\x1b]8;;https://e.invalid\x1b\\link\x1b]8;;\x1b\\ tail",
            "link tail",
            id="osc8_st",
        ),
        pytest.param("\x1b]0;title\x07text", "text", id="osc_bel"),
        pytest.param("\x9d8;;https://e.invalid\x9ctext", "text", id="osc_8bit"),
        pytest.param("a\x1bPdcs body\x1b\\b", "ab", id="dcs"),
        pytest.param("a\x1b_apc body\x1b\\b", "ab", id="apc"),
        pytest.param("text\x1b]8;;https://e.invalid", "text", id="osc_unterminated"),
        pytest.param("  a\tb\x00c  ", "abc", id="control_chars"),
        pytest.param("", "", id="empty"),
    ],
)
def test_clean_line(line: str, expected: str) -> None:
    assert _clean_line(line) == expected
