# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""When two classified licence values name one licence: the rule the
field-agreement check and the declared vs concluded check share.

``licenseid.resolve`` reads a listed name as its id (``MIT License`` is
``MIT``), so two classified values of one licence are mostly equal strings.
It reads no expression in the List name of 14 deprecated ids
(``GNU Free Documentation License v1.3`` for ``GFDL-1.3``), and its public
API gives no List name for an id: those names are kept here, as the SPDX
License List packaged with ``licenseid`` spells them.
``tests/extract/test_license_names.py`` fails when that list or the
resolver's reading of a name changes.

See also: :mod:`pitloom.extract.project._field_agreement` and
:mod:`pitloom.assemble.spdx3.deps_license` (the callers), and
:mod:`pitloom.extract._license_resolve` (the reading of a value).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

#: The List name, case folded, of each deprecated id whose name
#: ``licenseid.resolve`` reads no expression in (``licenseid`` 0.7.0, SPDX
#: License List 3.29.0), to that id.
UNREAD_LISTED_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        name.casefold(): license_id
        for name, license_id in (
            ("Affero General Public License v1.0", "AGPL-1.0"),
            ("GNU Affero General Public License v3.0", "AGPL-3.0"),
            ("bzip2 and libbzip2 License v1.0.5", "bzip2-1.0.5"),
            ("GNU Free Documentation License v1.1", "GFDL-1.1"),
            ("GNU Free Documentation License v1.2", "GFDL-1.2"),
            ("GNU Free Documentation License v1.3", "GFDL-1.3"),
            (
                "GNU General Public License v2.0 w/Autoconf exception",
                "GPL-2.0-with-autoconf-exception",
            ),
            (
                "GNU General Public License v2.0 w/Bison exception",
                "GPL-2.0-with-bison-exception",
            ),
            (
                "GNU General Public License v2.0 w/Classpath exception",
                "GPL-2.0-with-classpath-exception",
            ),
            (
                "GNU General Public License v2.0 w/Font exception",
                "GPL-2.0-with-font-exception",
            ),
            (
                "GNU General Public License v2.0 w/GCC Runtime Library exception",
                "GPL-2.0-with-GCC-exception",
            ),
            (
                "GNU General Public License v3.0 w/Autoconf exception",
                "GPL-3.0-with-autoconf-exception",
            ),
            (
                "GNU General Public License v3.0 w/GCC Runtime Library exception",
                "GPL-3.0-with-GCC-exception",
            ),
            ("wxWindows Library License", "wxWindows"),
        )
    }
)


def _is_unread_listed_name(name: str, license_id: str) -> bool:
    """Whether *name* is the List name of the deprecated id *license_id*
    that ``licenseid`` does not read, in any case."""
    return UNREAD_LISTED_NAMES.get(name.strip().casefold()) == license_id


def same_licence(first: str, second: str) -> bool:
    """Whether the classified licence values *first* and *second* name one
    licence: equal, or one is the List name of the other's deprecated id
    (:data:`UNREAD_LISTED_NAMES`)."""
    return (
        first == second
        or _is_unread_listed_name(first, second)
        or _is_unread_listed_name(second, first)
    )
