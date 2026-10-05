# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One way to name an SPDX 3 element or value in a message: an element as
``Type <spdxId> 'name'``, never as a Python object repr, so a message is the
same on every run.

See also: :mod:`pitloom.export.spdx3_json` (its error messages use this).
"""

from __future__ import annotations

from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

#: Left out of an object's description: its blank-node id and its shared
#: creation info.
_UNDESCRIBED = frozenset({"_id", "creationInfo"})


def property_names(obj: spdx3.SHACLObject) -> list[str]:
    """The declared Python property names of *obj*'s class."""
    return [k[0] for k in obj.property_keys() if k[0] is not None]


def _is_blank(value: Any) -> bool:
    if isinstance(value, (str, list, spdx3.ListProxy)):
        return len(value) == 0
    return value is None


def describe_element(type_name: str, spdx_id: str | None, name: str | None) -> str:
    """``Type <spdxId> 'name'``; the name part only when there is one."""
    label = f"{type_name} {spdx_id or '<no spdxId>'}"
    return f"{label} {name!r}" if name else label


def describe_graph_element(element: dict[str, Any]) -> str:
    """:func:`describe_element` for a serialised ``@graph`` entry."""
    name = element.get("name")
    return describe_element(
        str(element.get("type", "unknown")),
        element.get("spdxId"),
        name if isinstance(name, str) else None,
    )


def describe_value(value: Any) -> str:
    """*value* for a message: an element by id and name, an object with no
    id (a ``Hash``) by its type and sorted non-empty values, a string as its
    repr, a list item by item."""
    if isinstance(value, spdx3.SHACLObject):
        spdx_id = getattr(value, "spdxId", None)
        if isinstance(value, spdx3.Element) and spdx_id:
            return describe_element(type(value).__name__, spdx_id, value.name)
        fields = [
            f"{pyname}={describe_value(getattr(value, pyname))}"
            for pyname in sorted(property_names(value))
            if pyname not in _UNDESCRIBED
            and not _is_blank(getattr(value, pyname, None))
        ]
        return f"{type(value).__name__}({', '.join(fields)})"
    if isinstance(value, (list, tuple, spdx3.ListProxy)):
        return "[" + ", ".join(describe_value(v) for v in value) + "]"
    if isinstance(value, str):
        return repr(value)
    return str(value)
