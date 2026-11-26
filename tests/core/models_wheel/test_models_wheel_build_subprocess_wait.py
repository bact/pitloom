# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the build wait's deadline (``_wait_until`` in
``pitloom.core._models_wheel_build_subprocess``): the deadline itself is
already past, and the last slice waits only what is left. The clock is the
module's own ``time`` name, patched, so no test waits.

See also: tests/core/models_wheel/test_models_wheel_build_subprocess.py
(the timeout on a real child).
"""

from __future__ import annotations

import subprocess
import types
from unittest import mock

import pytest

from pitloom.core import _models_wheel_build_subprocess as bs
from pitloom.core.build_signals import TerminationGuard


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [(0.0, None), (0.125, 0)],
    ids=["at-deadline", "before"],
)
def test_wait_until_the_deadline_is_inclusive(
    monkeypatch: pytest.MonkeyPatch, remaining: float, expected: int | None
) -> None:
    """At the deadline no wait starts; before it, the wait is the time left
    (0.125 s, exact in binary floating point, shorter than a slice)."""
    monkeypatch.setattr(bs, "time", types.SimpleNamespace(monotonic=lambda: 100.0))
    proc = mock.create_autospec(subprocess.Popen, instance=True)
    proc.wait.return_value = 0
    # pylint: disable-next=protected-access
    assert bs._wait_until(proc, 100.0 + remaining, TerminationGuard()) == expected
    if expected is None:
        proc.wait.assert_not_called()
    else:
        proc.wait.assert_called_once_with(timeout=remaining)
