# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for tests/_bounded.py: a bounded call fails the test at the
bound instead of hanging it.

See also: tests/test_network_helpers.py (the other shared test helper).
"""

from __future__ import annotations

import time

import pytest

from tests._bounded import run_bounded, run_bounded_in_child


@pytest.mark.parametrize(
    ("target", "args", "seconds", "outcome"),
    [
        ("math:fsum", ([0.5, 0.25],), 10, 0.75),
        ("math:sqrt", (-1,), 10, ValueError),
        ("os:_exit", (3,), 10, "child exited 3"),
        ("time:sleep", (30,), 1, "killed, still running after"),
    ],
    ids=["result", "raises", "dies", "killed-at-bound"],
)
def test_run_bounded_in_child(
    target: str, args: tuple[object, ...], seconds: float, outcome: object
) -> None:
    """The result, the exception raised, or a failure naming why; one
    still running is killed at the bound, not waited for."""
    start = time.monotonic()
    if isinstance(outcome, str):
        with pytest.raises(pytest.fail.Exception, match=outcome):
            run_bounded_in_child(target, *args, seconds=seconds)
    elif isinstance(outcome, type):
        with pytest.raises(outcome):
            run_bounded_in_child(target, *args, seconds=seconds)
    else:
        assert run_bounded_in_child(target, *args, seconds=seconds) == outcome
    assert time.monotonic() - start < seconds + 5


def test_run_bounded() -> None:
    """A closure's result, its exception, or a failure at the bound."""
    assert run_bounded(lambda: 1) == 1
    with pytest.raises(ValueError):
        run_bounded(lambda: int("x"))
    with pytest.raises(pytest.fail.Exception, match="still running"):
        run_bounded(lambda: time.sleep(0.5), seconds=0.01)
