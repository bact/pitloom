# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``--build-timeout`` value helpers in
``pitloom.core._models_wheel_types``: ``validate_build_timeout()``,
``resolve_build_timeout()`` and ``parse_build_timeout()``.

See also: tests/core/models_wheel/test_models_wheel_types.py (the same
module's other helpers) and
tests/core/models_wheel/test_models_wheel_build_subprocess.py (the
timeout's enforcement).
"""

from __future__ import annotations

import pytest

from pitloom.core._models_wheel_types import (
    DEFAULT_BUILD_TIMEOUT_SECONDS,
    MAX_BUILD_TIMEOUT_SECONDS,
    parse_build_timeout,
    resolve_build_timeout,
    validate_build_timeout,
)


def test_constants() -> None:
    assert DEFAULT_BUILD_TIMEOUT_SECONDS == 1200
    assert MAX_BUILD_TIMEOUT_SECONDS == 7 * 24 * 60 * 60


@pytest.mark.parametrize("value", [1, 1200, 604_800], ids=str)
def test_validate_build_timeout_accepts(value: int) -> None:
    assert validate_build_timeout(value) == value


@pytest.mark.parametrize("value", [0, -1, 604_801], ids=str)
def test_validate_build_timeout_rejects_out_of_range(value: int) -> None:
    with pytest.raises(ValueError, match="1-604800 seconds"):
        validate_build_timeout(value)


@pytest.mark.parametrize("value", [True, False, 1.5, "10", None], ids=repr)
def test_validate_build_timeout_rejects_non_int(value: object) -> None:
    with pytest.raises(TypeError, match="build timeout"):
        validate_build_timeout(value)


def test_validate_build_timeout_message_has_no_build_prefix() -> None:
    with pytest.raises(ValueError) as excinfo:
        validate_build_timeout(0)
    assert not str(excinfo.value).startswith("Build:")


def test_resolve_build_timeout_none_is_default() -> None:
    assert resolve_build_timeout(None) == DEFAULT_BUILD_TIMEOUT_SECONDS


def test_resolve_build_timeout_passes_valid_value() -> None:
    assert resolve_build_timeout(30) == 30


@pytest.mark.parametrize("value", [0, True], ids=repr)
def test_resolve_build_timeout_validates(value: int) -> None:
    with pytest.raises((ValueError, TypeError)):
        resolve_build_timeout(value)


# Every accepted unit-bearing case below has the same meaning (in seconds)
# as Go's time.ParseDuration -- hardcoded, so a grammar change that drifts
# from Go semantics fails here. Bare numbers are seconds (GNU timeout, pip).
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", 1),
        ("900", 900),
        ("900s", 900),
        ("90m", 5400),
        ("1h", 3600),
        ("1h30m", 5400),
        ("1h30m45s", 5445),
        ("1h0m0s", 3600),
        ("1h90m", 9000),
        ("168h", 604_800),
    ],
    ids=str,
)
def test_parse_build_timeout_accepts(text: str, expected: int) -> None:
    assert parse_build_timeout(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "s",
        "h",
        "0",
        "0s",
        "168h1s",
        "1.5h",
        "500ms",
        "1d",
        "1H",
        "90M",
        " 90m",
        "90m ",
        "1h 30m",
        "30m1h",
        "1h1h",
        "-5",
        "+5",
        "\u0665",  # ARABIC-INDIC DIGIT FIVE: \d would match it, [0-9] must not
        "1e3",
    ],
    ids=repr,
)
def test_parse_build_timeout_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_build_timeout(text)


def test_parse_build_timeout_error_names_accepted_forms() -> None:
    with pytest.raises(ValueError, match="h/m/s units"):
        parse_build_timeout("1.5h")


def test_parse_build_timeout_out_of_range_reports_range() -> None:
    with pytest.raises(ValueError, match="1-604800 seconds"):
        parse_build_timeout("168h1s")


@pytest.mark.parametrize(
    "text",
    ["9" * 5000, "9" * 4299 + "h", "1h" + "9" * 50 + "s", "0" * 5000 + "9999999h"],
    ids=["bare-5000-digits", "hours-4299-digits", "seconds-50-digits", "zeros"],
)
def test_parse_build_timeout_huge_value_is_out_of_range(text: str) -> None:
    # Checked before int(), which refuses digit strings beyond
    # sys.get_int_max_str_digits(); the input is never echoed in full.
    with pytest.raises(ValueError, match="1-604800 seconds") as excinfo:
        parse_build_timeout(text)
    assert str(excinfo.value).endswith("got more than 604800")


def test_parse_build_timeout_leading_zeros_beyond_int_digit_limit() -> None:
    assert parse_build_timeout("0" * 5000 + "90m") == 5400


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        (10**5000, "more than 604800"),
        (3600 * (10**4299 - 1), "more than 604800"),
        (10**49, "more than 604800"),
        (-(10**5000), "less than 1"),
        (604_801, "604801"),
        (-3, "-3"),
    ],
    ids=["10**5000", "4299-digit-hours", "50-digits", "-10**5000", "max+1", "-3"],
)
def test_validate_build_timeout_out_of_range_message(value: int, shown: str) -> None:
    # Huge ints are described, not formatted: str() of one beyond
    # sys.get_int_max_str_digits() raises CPython's own ValueError.
    with pytest.raises(ValueError, match="1-604800 seconds") as excinfo:
        validate_build_timeout(value)
    assert str(excinfo.value).endswith(f"got {shown}")
