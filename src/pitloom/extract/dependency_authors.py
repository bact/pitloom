# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A dependency's originators from its free-text author or maintainer
fields (an installed record, a PyPI record), by the one reading of
:func:`pitloom.extract.authors.author_pairs`.

See also: :mod:`pitloom.extract.authors` (the reading) and
:mod:`pitloom.extract._author_warnings` (the one split line per document).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from pitloom.extract._author_warnings import AuthorSplit, report_dependency_splits
from pitloom.extract.authors import AUTHOR_KEYS, author_pairs, stated_text

if TYPE_CHECKING:
    from pitloom.extract.authors import NameEmail

__all__ = ["dependency_author_pairs", "dependency_originator_pairs"]


def dependency_author_pairs(
    package: str,
    names: str | None,
    addresses: str | None,
    keys: tuple[str, str] = AUTHOR_KEYS,
) -> list[NameEmail]:
    """A dependency's originator pairs from one name/address field pair
    (their keys *keys*), by :func:`~pitloom.extract.authors.author_pairs`.
    A split is reported once per document by the enclosing
    :func:`~pitloom.extract.authors.dependency_author_splits` block, or at
    once outside one; an address entry that is no address is left out
    quietly (another project's record, one line each would flood a large
    environment). A field over a cap warns: these authors are used."""
    splits: list[AuthorSplit] = []
    pairs = author_pairs(
        names, addresses, splits=splits, quiet=False, address_warnings=False, keys=keys
    )
    report_dependency_splits(package, splits)
    return pairs


def dependency_originator_pairs(
    package: str,
    fields: tuple[tuple[str, str], ...],
    value: Callable[[str], str | None],
) -> list[NameEmail]:
    """A dependency's originator pairs (:func:`dependency_author_pairs`)
    from the first of *fields* (``(name field, address field)``, e.g. the
    author pair then the maintainer pair) that states either; *value*
    gives a field's text. A pair stating a value read as no author ends
    the search: only an absent pair (missing, blank, ``UNKNOWN``) falls
    back to the next, so a package is never credited to its maintainer
    for an author left unread. Each field's warning key is its name in
    upper case, ``-`` read as ``_`` (``MAINTAINER_EMAIL``)."""
    for name_field, address_field in fields:
        names, addresses = value(name_field), value(address_field)
        if stated_text(names) or stated_text(addresses):
            keys = (_field_key(name_field), _field_key(address_field))
            return dependency_author_pairs(package, names, addresses, keys)
    return []


def _field_key(field: str) -> str:
    """A metadata field name as a warning key: ``Author-email``,
    ``author_email`` -> ``AUTHOR_EMAIL``."""
    return field.upper().replace("-", "_")
