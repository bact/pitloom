# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A catalogued line's template: the names it uses, and the line it renders
from the caller's values, each written by its field.

See also: :mod:`pitloom.messages._fields` (the fields a template names).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from pitloom.messages._fields import FIELDS

#: A name in a template.
PLACEHOLDER: Final = re.compile(r"%\(([a-z_]+)\)s")


def template_names(template: str) -> tuple[str, ...]:
    """The names *template* uses, in order.

    A field of a closed shape may stand twice (``header is not
    %(format)s`` after ``FORMAT=%(format)s``), printing the one value both
    times; a free one may not.

    Raises:
        ValueError: A name is not in :data:`FIELDS`, a free one is used
            twice, or a ``%`` is not part of a name.
    """
    names = tuple(PLACEHOLDER.findall(template))
    unknown = sorted(set(names) - set(FIELDS))
    if unknown:
        raise ValueError(f"{template!r}: unknown field {unknown[0]!r}")
    repeated = sorted({n for n in names if FIELDS[n].free and names.count(n) > 1})
    if repeated:
        raise ValueError(f"{template!r}: free field {repeated[0]!r} named twice")
    if "%" in PLACEHOLDER.sub("", template):
        raise ValueError(f"{template!r}: a '%' that names no field")
    return names


def template_pattern(template: str) -> str:
    """*template* as a regular expression: its text literal, each name its
    field's :attr:`~Field.pattern`."""
    parts: list[str] = []
    end = 0
    for found in PLACEHOLDER.finditer(template):
        parts.append(re.escape(template[end : found.start()]))
        parts.append(f"(?:{FIELDS[found.group(1)].pattern})")
        end = found.end()
    parts.append(re.escape(template[end:]))
    return "".join(parts)


def written(template: str, values: Mapping[str, object]) -> dict[str, str]:
    """Each value of *values* written by its field, for *template*.

    Raises:
        ValueError: *values* names other fields than *template*, or a
            written value does not have its field's shape.
    """
    names = template_names(template)
    if set(values) != set(names):
        raise ValueError(
            f"{template!r} takes {sorted(set(names))}, not {sorted(values)}"
        )
    texts: dict[str, str] = {}
    for name in dict.fromkeys(names):
        text = FIELDS[name].write(values[name])
        if re.fullmatch(FIELDS[name].pattern, text) is None:
            raise ValueError(f"{name}={text!r} is not a {name}")
        texts[name] = text
    return texts


def shown(template: str) -> str:
    """*template* as the reference shows it, each name its field's
    :attr:`~Field.shown` (``<file>``)."""
    return PLACEHOLDER.sub(lambda found: FIELDS[found.group(1)].shown, template)


def render(template: str, values: Mapping[str, object]) -> str:
    """*template* with each name replaced by its value, as written by its
    field (:func:`written`)."""
    texts = written(template, values)
    return PLACEHOLDER.sub(lambda found: texts[found.group(1)], template)
