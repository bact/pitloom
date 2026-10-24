# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.pep440`: a version with a number past
:data:`~pitloom.core.pep440.MAX_VERSION_NUMBER_DIGITS` digits is refused
before ``int()`` sees it, whatever the interpreter's digit limit.

See also: tests/extract/lock/test_overlong_versions.py (the lock readers
and ``loom project``).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from pitloom.core.pep440 import (
    MAX_VERSION_NUMBER_DIGITS,
    has_overlong_number,
    parse_version,
    specifier_contains,
)

_N = MAX_VERSION_NUMBER_DIGITS
_set_int_limit = getattr(sys, "set_int_max_str_digits", None)


@pytest.fixture(name="int_limit", params=[640, 4300, 0], ids=["min", "dflt", "off"])
def _int_limit(request: pytest.FixtureRequest) -> Iterator[int]:
    """The interpreter's int digit limit set explicitly (0: none, as on
    Python before 3.10.7), restored after."""
    if _set_int_limit is None:
        pytest.skip("no int string-conversion limit on this Python")
    old = sys.get_int_max_str_digits()  # pylint: disable=no-member
    _set_int_limit(request.param)
    yield request.param
    _set_int_limit(old)


def test_the_cap_is_under_every_interpreter_limit() -> None:
    """640 is the least nonzero limit Python accepts, so an accepted
    number converts under any setting."""
    if _set_int_limit is None:
        pytest.skip("no int string-conversion limit on this Python")
    assert sys.int_info.str_digits_check_threshold == _N  # pylint: disable=no-member


@pytest.mark.parametrize(
    "template",
    ["1.{}", "{}!1", "1rc{}", "1.post{}", "1.dev{}", "1+{}", "1+abc{}", "2.{}"],
    ids=["release", "epoch", "pre", "post", "dev", "local", "local-alnum", "zeros"],
)
@pytest.mark.parametrize(
    "digits", [_N, _N + 1, 4299, 4300, 4301, 5000], ids=lambda d: f"d{d}"
)
def test_parse_version_bounds_each_number(
    int_limit: int, template: str, digits: int
) -> None:
    """Each segment, at and past the cap and around the default limit;
    leading zeros count, as ``int()`` counts them. Never raises."""
    del int_limit
    number = ("0" * (digits - 1) + "7") if template == "2.{}" else "9" * digits
    text = template.format(number)
    assert has_overlong_number(text) is (digits > _N)
    parsed = parse_version(text)
    assert (parsed is None) is (digits > _N)
    if parsed is not None:
        assert parsed == Version(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.0", Version("1.0.0")),
        ("2026.10.24", Version("2026.10.24")),
        ("20261024123456", Version("20261024123456")),
        ("", None),
        ("-1", None),
        ("not a version", None),
        ("\u0661.\u0660", None),  # Arabic-Indic digits: int() takes them
        ("1." + "\u0669" * 5000, None),
        (None, None),
        (1, None),
    ],
    ids=[
        "equal",
        "calver",
        "stamp",
        "empty",
        "neg",
        "words",
        "ar",
        "ar-long",
        "none",
        "int",
    ],
)
def test_parse_version_ordinary_and_invalid(text: object, expected: object) -> None:
    """PEP 440 equality is unchanged for real versions; anything else is
    ``None``. Non-ASCII digits are no PEP 440 digits and are not counted."""
    assert parse_version(text) == expected
    if isinstance(text, str):
        assert not has_overlong_number(text)


@pytest.mark.parametrize(
    ("spec", "version", "expected"),
    [
        ("==1.0", "1.0.0", True),
        (">=2", "1.0", False),
        ("~=1.0", "1.5", True),
        ("==1.0", "1." + "9" * 5000, None),
        ("==1." + "9" * 5000, "1.0", None),
        (">=1," + "<" + "9" * (_N + 1), "1.0", None),
    ],
    ids=["equal", "outside", "compatible", "long-version", "long-pin", "long-bound"],
)
def test_specifier_contains(
    int_limit: int, spec: str, version: str, expected: bool | None
) -> None:
    """``SpecifierSet.contains`` for a real pair; ``None`` when a number
    in either is overlong. ``packaging`` 25 cannot even build an overlong
    one under a digit limit."""
    del int_limit
    try:
        specifier = SpecifierSet(spec)
    except ValueError:
        pytest.skip("this packaging release cannot build the specifier set")
    assert specifier_contains(specifier, version) is expected


def test_specifier_contains_an_invalid_version_error_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``packaging`` before 26 raises ``InvalidVersion`` on a non-version."""

    def _raise(*_args: object, **_kwargs: object) -> bool:
        raise InvalidVersion("x")

    monkeypatch.setattr(SpecifierSet, "contains", _raise)
    assert specifier_contains(SpecifierSet("==1.0"), "x") is None
