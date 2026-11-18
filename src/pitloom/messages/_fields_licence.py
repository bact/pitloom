# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the licence lines name: a licence value as read, the
``License ::`` classifiers, the expression LicenseID reads, the steps it
took and why a value is not read as an expression.

A value read from a file is written by
:func:`~pitloom.logging_config.excerpt`
(:func:`~pitloom.messages._fields_lock.excerpt_text`): on one line, a URL's
credentials masked, cut, escaped.

See also: :mod:`pitloom.messages._fields` (every field, these included) and
:mod:`pitloom.messages._license_expression` (the lines).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.log_masking import masked_text
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import free_text, plain_text
from pitloom.messages._fields_lock import EXCERPT_MEANING, excerpt_text, excerpts_text


def masked_free_text(value: object) -> str:
    """A text LicenseID reports (a reason names the operand it could not
    resolve, which may be a URL), written as
    :func:`~pitloom.messages._field_writers.free_text` writes it, the
    credentials of a URL in it masked."""
    return free_text(masked_text(plain_text(value)))


#: The licence lines' fields.
LICENCE_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "classifiers": Field(
            r".+",
            excerpts_text,
            "<classifiers>",
            "the `License ::` classifiers, sorted, comma-separated, each "
            f"{EXCERPT_MEANING}",
            free=True,
        ),
        "expression": Field(
            r".+",
            masked_free_text,
            "<expression>",
            "the SPDX license expression recorded (`Apache-2.0 AND MIT`); "
            "escaped when it holds a control character",
            free=True,
        ),
        "license": Field(
            r".+",
            excerpt_text,
            "<license>",
            f"a licence value as read, {EXCERPT_MEANING}",
            free=True,
        ),
        "license_reason": Field(
            r".+",
            masked_free_text,
            "<license-reason>",
            "why the value is no SPDX license expression: LicenseID's reason "
            "(`parse failed: Unexpected 'OR'`, `not found: Acme-Terms`) or "
            "Pitloom's (`more than one line`); escaped when it holds a control "
            "character",
            free=True,
        ),
        "steps": Field(
            r".+",
            masked_free_text,
            "<steps>",
            "LicenseID's steps (`separator, version_spelling`), or its category "
            "when it took none (`listed_name`); escaped when it holds a "
            "control character",
            free=True,
        ),
    }
)
