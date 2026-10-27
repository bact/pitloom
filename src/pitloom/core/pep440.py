# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every PEP 440 version Pitloom parses from its input goes through here.

``packaging`` turns each number of a version (epoch, release, pre, post,
dev, a numeric local label) into an ``int``. Past Python's integer
string-conversion limit (``sys.get_int_max_str_digits()``, 4300 digits by
default, none before 3.10.7) that raises a plain ``ValueError``, not
``InvalidVersion``, so a lock file or a dependency pin holding
``"1." + "9" * 5000`` would end the run: when parsing the version, when
building a specifier set (``packaging`` 25 hashes each specifier) and when
printing or comparing one of several specifiers (26). A version with a run of more than
:data:`MAX_VERSION_NUMBER_DIGITS` ASCII digits is not one here: it is
refused before ``int()`` sees it, the same on every Python version and
whatever the interpreter's limit, and the caller treats it as any other
unparseable version (its own ``WARNING:``, or a plain string compare).

No Pitloom imports.

See also: :mod:`pitloom.core.pep508` (requirements and markers),
:mod:`pitloom.extract.lock.common` (the lock readers' version helpers).
Every ``SpecifierSet`` built from input text goes through
:func:`parse_specifier_set`, every ``Requirement`` through
:func:`pitloom.core.pep508.parse_requirement`.
"""

from __future__ import annotations

import re

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

__all__ = [
    "MAX_VERSION_NUMBER_DIGITS",
    "has_overlong_number",
    "parse_specifier_set",
    "parse_version",
    "specifier_contains",
]

#: Most ASCII digits one number of a version may have. The least nonzero
#: limit :func:`sys.set_int_max_str_digits` accepts
#: (``sys.int_info.str_digits_check_threshold``), so every number accepted
#: converts under any interpreter setting; a real version number has a few
#: digits, a date or a timestamp 14 at most.
MAX_VERSION_NUMBER_DIGITS = 640

#: Why a version, specifier or requirement is refused for its number. The one
#: wording, so the exception text and the project-table error say it alike.
NUMBER_REASON = f"has a number over {MAX_VERSION_NUMBER_DIGITS} digits"

_OVERLONG_NUMBER = re.compile(f"[0-9]{{{MAX_VERSION_NUMBER_DIGITS + 1}}}")


def has_overlong_number(text: str) -> bool:
    """Whether *text* has a run of more than :data:`MAX_VERSION_NUMBER_DIGITS`
    ASCII digits (leading zeros count: ``int()`` counts them too)."""
    return _OVERLONG_NUMBER.search(text) is not None


def parse_version(text: object) -> Version | None:
    """*text* as a PEP 440 :class:`~packaging.version.Version`, or ``None``
    when it is not a string, does not parse or has an overlong number
    (:func:`has_overlong_number`). Never raises."""
    if not isinstance(text, str) or has_overlong_number(text):
        return None
    try:
        return Version(text)
    except InvalidVersion:
        return None


def parse_specifier_set(text: str) -> SpecifierSet:
    """*text* as a PEP 440 :class:`~packaging.specifiers.SpecifierSet`.
    The caller logs its own ``WARNING:``.

    Raises:
        packaging.specifiers.InvalidSpecifier: *text* is not one, or has an
            overlong number (:func:`has_overlong_number`).
        TypeError: *text* is not a string.
    """
    if has_overlong_number(text):
        raise InvalidSpecifier(NUMBER_REASON)
    return SpecifierSet(text)


def specifier_contains(specifier: SpecifierSet, version: str) -> bool | None:
    """Whether *specifier* admits *version*, pre-releases included, as
    :meth:`~packaging.specifiers.SpecifierSet.contains` judges it (which
    may compare a ``===`` string that is no version); ``None`` when it
    cannot be judged: a number in either is overlong
    (:func:`has_overlong_number`), or ``packaging`` raises
    ``InvalidVersion`` (releases before 26 do on a non-version). Never
    raises."""
    if has_overlong_number(version) or any(
        has_overlong_number(spec.version) for spec in specifier
    ):
        return None
    try:
        return specifier.contains(version, prereleases=True)
    except InvalidVersion:
        return None
