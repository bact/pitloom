# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether two JSON texts say the same, in any spelling.

A fragment's text value that is a JSON object or array (the input/output
description of a model) may hold the same JSON as another with other spacing or
key order. The merge reads those as one value: no ``Merge: conflicting`` warning and no
second value. A fragment is untrusted input, so the comparison is bounded
(:data:`MAX_JSON_DEPTH`) and exact: ``1``, ``1.0`` and ``true`` are three
values, a float is its text, and a repeated key is no JSON.

See also: :mod:`pitloom.assemble.spdx3._fragments_props` (the field merge that
uses it) and :mod:`pitloom.assemble.spdx3._fragments_generated`.
"""

from __future__ import annotations

import json

from pitloom.extract._extract_utils import json_nests_over


class _Float(str):
    """A JSON number with a fraction or an exponent, kept as its text: two
    spellings of it are two values (a float would equate ``1e400`` with
    ``2e999``, or ``0.1`` with ``0.10000000000000000001``)."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def _same(old: object, new: object) -> bool:
    """Whether two parsed JSON values are the same, a number and a boolean
    never (``1`` and ``true``) and a float only as the same text."""
    if type(old) is not type(new):
        return False
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same(old[k], new[k]) for k in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(
            _same(o, n) for o, n in zip(old, new, strict=True)
        )
    return bool(old == new)


#: The deepest nesting of fragment JSON text that is compared. Reading deeper
#: text fails at a depth that depends on the Python version and the call stack
#: (about 1000 on 3.10 and 3.11, more later), so the line is drawn here.
MAX_JSON_DEPTH = 64


def _no_constant(name: str) -> object:
    raise ValueError(f"not JSON: {name}")


def same_json(old: str, new: str) -> bool:
    """Whether the texts *old* and *new* are the same JSON object or array, in
    any spelling of the whitespace and the order of an object's keys. Text
    that is not an object or array (a name, a version, ``"1"``, ``"true"``),
    is no JSON (``NaN`` and ``Infinity`` included), has a repeated key or
    nests too deeply to read (a fragment is untrusted) is never the same: it
    is compared as text, by the caller."""
    if not all(text.lstrip()[:1] in {"{", "["} for text in (old, new)):
        return False
    if any(
        json_nests_over(text.encode("utf-8", "surrogatepass"), MAX_JSON_DEPTH)
        for text in (old, new)
    ):
        return False
    try:
        return _same(
            *(
                json.loads(
                    text,
                    parse_float=_Float,
                    parse_constant=_no_constant,
                    object_pairs_hook=_no_duplicate_keys,
                )
                for text in (old, new)
            )
        )
    except (ValueError, RecursionError):
        return False
