# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""When ``licenseid``'s matches decide a licence: a stated licence wins a
near-tie; with none stated, a near-tie with another licence family is no
detection, unless the runner-up fits the input measurably worse.

See also: test_license_detection.py (detection, mocked),
test_license_detection_corpus.py (real licence files).
"""

from typing import cast

import pytest
from licenseid.types import LicenseMatch

from pitloom.extract._license import (
    _best_reading_decides,
    _decisive,
    _stated_among,
    _stated_ids,
)


@pytest.mark.parametrize(
    ("scores", "stated", "expected"),
    [
        ([("Pixar", 0.996), ("Apache-2.0", 0.992)], "Apache-2.0", "Apache-2.0"),
        ([("Pixar", 0.996), ("Apache-2.0", 0.992)], "apache-2.0", "Apache-2.0"),
        ([("Apache-2.0", 0.99), ("ECL-2.0", 0.9)], "ECL-2.0", None),  # too far
        ([("Pixar", 0.996)], "MIT", None),  # not among the matches
        ([("Pixar", 0.996)], None, None),
        ([], "MIT", None),
        ([("Pixar", 0.996), ("Apache-2.0", 0.992)], "MIT OR Apache-2.0", "Apache-2.0"),
        ([("Pixar", 0.996)], "LicenseRef-Pixar", None),  # one id, not a part
        # a deprecated "+" id is its successor
        (
            [("GPL-2.0-only", 1.0), ("GPL-2.0-or-later", 1.0)],
            "MIT OR GPL-2.0+",
            "GPL-2.0-or-later",
        ),
        ([("MIT", 0.99), ("X11", 0.985)], "X11 licence text, see MIT", None),
        ([("X", 0.9), ("Y", 0.5), ("MIT", 0.905)], "MIT", "MIT"),  # unsorted
    ],
)
def test_a_stated_licence_wins_only_a_near_tie(
    scores: list[tuple[str, float]], stated: str | None, expected: str | None
) -> None:
    results = [{"license_id": i, "score": s} for i, s in scores]
    found = _stated_among(results, _stated_ids(stated))  # type: ignore[arg-type]
    assert found == expected


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([("JSON", 0.935), ("MIT", 0.929)], None),  # another licence: a tie
        ([("GPL-3.0-only", 1.0), ("GPL-3.0-or-later", 1.0)], "GPL-3.0-only"),
        ([("MIT", 0.855), ("JSON", 0.848)], None),  # runner-up below threshold
        ([("MIT", 0.95), ("JSON", 0.939)], "MIT"),  # a clear lead
        ([("MIT", 0.84)], None),  # below threshold
        ([("A", 0.9), ("X", 0.5), ("B", 0.905)], None),  # not sorted by score
        ([], None),
    ],
)
def test_a_near_tie_with_another_licence_family_is_no_detection(
    scores: list[tuple[str, float]], expected: str | None
) -> None:
    results = [{"license_id": i, "score": s} for i, s in scores]
    assert _decisive(results, 0.85) == expected  # type: ignore[arg-type]


#: (id, score, similarity, coverage) as licenseid 0.4 gives them: a score
#: capped to 1, the fit measured.
_FitRow = tuple[str, float, "float | None", "float | None"]


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        # the input is a quarter of FSL-1.1-MIT: no tie with MIT at 1
        ([("MIT", 1.0, 0.977, 0.959), ("FSL-1.1-MIT", 1.0, 1.0, 0.25)], "MIT"),
        # as much of each licence held, JSON matches less closely
        ([("MIT", 1.0, 0.979, 0.982), ("JSON", 0.993, 0.962, 0.982)], "MIT"),
        # both hold their whole licence and more (coverage over 1): a tie
        ([("MIT", 0.930, 0.899, 1.182), ("JSON", 0.927, 0.896, 1.123)], None),
        ([("JSON", 0.935, 0.904, 1.134), ("MIT", 0.929, 0.897, 1.194)], None),
        # within the margin on both measures: a tie
        ([("MIT", 1.0, 0.979, 0.982), ("JSON", 0.995, 0.971, 0.975)], None),
        ([("MIT", 1.0, None, None), ("JSON", 0.995, None, None)], None),  # unmeasured
    ],
    ids=[
        "partial-licence",
        "less-similar",
        "extra-words",
        "extra-words-2",
        "close",
        "unmeasured",
    ],
)
def test_a_runner_up_that_fits_measurably_worse_is_no_tie(
    rows: list[_FitRow], expected: str | None
) -> None:
    assert _decisive(_fit_rows(rows), 0.85) == expected


def _fit_rows(rows: list[_FitRow]) -> list[LicenseMatch]:
    """*rows* as ``licenseid`` 0.4 matches (the fields read here only)."""
    return cast(
        "list[LicenseMatch]",
        [
            {"license_id": i, "score": s, "similarity": sim, "coverage": cov}
            for i, s, sim, cov in rows
        ],
    )


_MIT_CAPPED: _FitRow = ("MIT", 1.0, 0.977, 0.959)


@pytest.mark.parametrize(
    ("rows", "stated", "expected"),
    [
        # against a capped top, a stated near-variant must fit as well
        ([_MIT_CAPPED, ("FSL-1.1-MIT", 1.0, 1.0, 0.25)], "FSL-1.1-MIT", None),
        ([_MIT_CAPPED, ("JSON", 0.990, 0.959, 0.911)], "JSON", None),
        ([_MIT_CAPPED, ("JSON", 0.995, 0.971, 0.955)], "JSON", "JSON"),  # as close
        (
            [("GPL-2.0-only", 1.0, 0.999, 1.0), ("GPL-2.0-or-later", 1.0, 0.999, 1.0)],
            "GPL-2.0+",
            "GPL-2.0-or-later",
        ),
        # below the cap the score still orders: requests' Apache 2.0 text
        (
            [("Pixar", 0.9963, 0.9913, 1.0043), ("Apache-2.0", 0.9921, 0.9421, 0.8859)],
            "Apache-2.0",
            "Apache-2.0",
        ),
    ],
    ids=["partial-licence", "less-similar", "close", "or-later", "below-cap"],
)
def test_a_stated_licence_must_fit_as_well_as_a_capped_top(
    rows: list[_FitRow], stated: str, expected: str | None
) -> None:
    found = _stated_among(_fit_rows(rows), _stated_ids(stated))
    assert found == expected


_TIED: list[_FitRow] = [_MIT_CAPPED, ("JSON", 0.995, 0.971, 0.955)]
_DECIDED: list[_FitRow] = [_MIT_CAPPED, ("JSON", 0.990, 0.959, 0.911)]


@pytest.mark.parametrize(
    ("readings", "expected"),
    [
        ([_TIED, _DECIDED], "MIT"),  # equal top scores: the one that decides
        ([_DECIDED, _TIED], "MIT"),
        ([_TIED, _TIED], None),
        # a lower-scoring reading never decides over a better one
        (
            [
                [("X", 0.98, 0.98, 1.0), ("Y", 0.975, 0.975, 1.0)],
                [("MIT", 0.95, 0.95, 1.0)],
            ],
            None,
        ),
    ],
    ids=["tie-first", "tie-second", "both-tied", "lower-score"],
)
def test_reading_order_alone_never_turns_an_answer_into_none(
    readings: list[list[_FitRow]], expected: str | None
) -> None:
    found = _best_reading_decides(
        [_fit_rows(rows) for rows in readings],
        0.85,
    )
    assert found == expected
