# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Measure that a call's time grows linearly with its text's length: the
ratio of the time on a text five times as long, not a wall-clock bound, so
a slow or loaded runner, or coverage tracing, cancels out.

See also: tests/core/url_masking/test_url_masking_linear_time.py and
tests/test_log_text.py, which use it.
"""

from __future__ import annotations

import time
from collections.abc import Callable

#: The ratio of five times the text that a linear call stays under (about 5,
#: up to 15 on a loaded runner; a quadratic one gives about 25, one with a
#: linear part as large at 100k characters 15.3). Counting the characters
#: the masker's patterns scan would be deterministic (roadmap follow-up).
RATIO_BOUND = 15

#: The shortest time a measurement counts as, so a run too fast to time does
#: not make the ratio noise.
_FLOOR_SECONDS = 0.005


def best_time(run: Callable[[str], object], text: str) -> float:
    """The shortest of three runs of *run* on *text*."""
    times = []
    for _ in range(3):
        started = time.perf_counter()
        run(text)
        times.append(time.perf_counter() - started)
    return min(times)


def settled_ratio(measure: Callable[[], float], tries: int = 3) -> float:
    """The least of up to *tries* measured ratios, stopping at the first under
    :data:`RATIO_BOUND`: a loaded runner slows one measurement, and a quadratic
    call is over the bound on every try."""
    ratio = float("inf")
    for _ in range(tries):
        ratio = min(ratio, measure())
        if ratio < RATIO_BOUND:
            break
    return ratio


def linear_ratio(
    run: Callable[[str], object],
    make: Callable[[int], str],
    short: int = 100_000,
) -> float:
    """The settled ratio of *run*'s best time on ``make(5 * short)`` to its
    best time on ``make(short)`` (at least 5 ms)."""

    def measure() -> float:
        first = max(best_time(run, make(short)), _FLOOR_SECONDS)
        return best_time(run, make(5 * short)) / first

    return settled_ratio(measure)
