# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Several ``License ::`` classifiers as one licence expression:
``LicenseRef-pitloom-classifier-<name> AND ...``, one term per licence name
as the classifier gives it (no mapping to a listed id). Each ``LicenseRef-``
encodes its name reversibly, so the element builder recovers the names from
the expression alone, identically on every surface.

See also: :func:`pitloom.extract._core_metadata.license_from_classifiers`
(the reader side) and
:func:`pitloom.assemble.spdx3._license_elements.get_or_create_license_element`
(the builder, which maps each reference to a text element through
``simplelicensing_customIdToUri``).
"""

from __future__ import annotations

from collections.abc import Sequence

CLASSIFIER_REF_PREFIX = "LicenseRef-pitloom-classifier-"
_AND = " AND "


def _encoded(name: str) -> str:
    """*name* as an SPDX idstring (``[A-Za-z0-9.-]``): letters and digits as
    they are, a space as ``-``, any other UTF-8 byte as ``.XX`` (upper-case
    hex), so ``MIT License`` is ``MIT-License``."""
    out: list[str] = []
    for byte in name.encode("utf-8"):
        char = chr(byte)
        if char.isascii() and char.isalnum():
            out.append(char)
        elif char == " ":
            out.append("-")
        else:
            out.append(f".{byte:02X}")
    return "".join(out)


def _decoded(encoded: str) -> str | None:
    """The name :func:`_encoded` gave *encoded*, or ``None`` when it is not
    that function's output."""
    data = bytearray()
    index = 0
    while index < len(encoded):
        char = encoded[index]
        if char == ".":
            pair = encoded[index + 1 : index + 3]
            if len(pair) != 2 or not all(c in "0123456789ABCDEF" for c in pair):
                return None
            data.append(int(pair, 16))
            index += 3
            continue
        data.append(0x20 if char == "-" else ord(char) if char.isascii() else 0)
        index += 1
    try:
        name = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return name if _encoded(name) == encoded else None


def classifier_expression(names: Sequence[str]) -> str:
    """The ``AND`` of *names* (two or more, in the order given) as
    ``LicenseRef-pitloom-classifier-`` terms."""
    return _AND.join(CLASSIFIER_REF_PREFIX + _encoded(name) for name in names)


def classifier_terms(expression: str) -> list[tuple[str, str]] | None:
    """``(LicenseRef id, licence name)`` per term when *expression* is exactly
    what :func:`classifier_expression` writes for two or more names, else
    ``None``. A user's own expression spelled exactly in that form is read
    as one; any other spelling, other ``LicenseRef-`` terms included, is
    not."""
    terms = expression.split(_AND)
    if len(terms) < 2:
        return None
    found: list[tuple[str, str]] = []
    for term in terms:
        if not term.startswith(CLASSIFIER_REF_PREFIX):
            return None
        name = _decoded(term[len(CLASSIFIER_REF_PREFIX) :])
        if not name:
            return None
        found.append((term, name))
    return found
