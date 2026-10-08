# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The display text of an SPDX 3 element built from untrusted model data,
with its invisible and bidi controls made visible.

One function, :func:`escape_element_display_text`, for every element a
model brings into the SBOM: its own ``ai_AIPackage``, the base-model
package, dataset packages and their creators, its licence element, and the
relationships between them. Text is escaped as text, an IRI percent-encoded
(:mod:`pitloom.core.untrusted_text`).

See also: :func:`pitloom.assemble.spdx3._ai_package.finish_ai_package`
(the one warning per model).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.untrusted_text import (
    escape_display_controls,
    escape_display_controls_in_iri,
    escape_display_controls_in_json,
)

__all__ = [
    "BASE_MODEL",
    "BASE_MODEL_RELATIONSHIP",
    "DATASET",
    "DATASET_CREATOR",
    "DATASET_RELATIONSHIP",
    "LICENSE",
    "escape_element_display_text",
]

#: Labels naming, in the warning, the element a property belongs to.
BASE_MODEL = "base model"
BASE_MODEL_RELATIONSHIP = "base model relationship"
DATASET = "dataset"
DATASET_CREATOR = "dataset creator"
DATASET_RELATIONSHIP = "dataset relationship"
LICENSE = "license"

_Escape = Callable[[str], str]
_text = escape_display_controls
_iri = escape_display_controls_in_iri

# (property, escape, holds a list): an element's own properties, each
# applied only where the element's class has it.
_FIELDS: tuple[tuple[str, _Escape, bool], ...] = (
    ("name", _text, False),
    ("summary", _text, False),
    ("description", _text, False),
    ("comment", _text, False),
    ("software_packageVersion", _text, False),
    ("software_downloadLocation", _iri, False),
    ("ai_limitation", _text, False),
    ("ai_informationAboutApplication", escape_display_controls_in_json, False),
    ("ai_typeOfModel", _text, True),
    ("ai_domain", _text, True),
    ("dataset_dataCollectionProcess", _text, False),
    ("dataset_intendedUse", _text, False),
    ("dataset_dataPreprocessing", _text, True),
    ("dataset_knownBias", _text, True),
    ("dataset_anonymizationMethodUsed", _text, True),
    ("simplelicensing_licenseText", _text, False),
    ("simplelicensing_licenseExpression", _text, False),
)

# The same for each entry of a list property, named by that property.
_ENTRY_FIELDS: dict[str, tuple[tuple[str, _Escape, bool], ...]] = {
    "ai_hyperparameter": (("key", _text, False), ("value", _text, False)),
    "externalRef": (("comment", _text, False), ("locator", _iri, True)),
    "externalIdentifier": (
        ("identifier", _text, False),
        ("comment", _text, False),
        ("identifierLocator", _iri, True),
    ),
}


def _escape_field(obj: Any, prop: str, escape: _Escape, is_list: bool) -> bool:
    """Escape *obj*'s *prop* in place; return whether it changed."""
    if is_list:
        texts = list(getattr(obj, prop))
        shown_list = [escape(text) for text in texts]
        if shown_list == texts:
            return False
        setattr(obj, prop, shown_list)
        return True
    text = getattr(obj, prop)
    if text is None or (shown := escape(text)) == text:
        return False
    setattr(obj, prop, shown)
    return True


def _escape_fields(obj: Any, fields: tuple[tuple[str, _Escape, bool], ...]) -> bool:
    """Escape each of *fields* *obj*'s class has; return whether any changed."""
    changed = [
        _escape_field(obj, prop, escape, is_list)
        for prop, escape, is_list in fields
        if hasattr(obj, prop)
    ]
    return any(changed)


def escape_element_display_text(element: spdx3.Element) -> list[str]:
    """Escape the invisible and bidi controls in *element*'s display text,
    in place; return the names of the properties changed, sorted.

    Never touches ``spdxId``: an id is minted from the text as resolved,
    with these controls percent-encoded
    (:func:`pitloom.core.iri.iri_segment`), so it still agrees with the
    registry and with every reference to it."""
    changed = {
        prop
        for prop, escape, is_list in _FIELDS
        if hasattr(element, prop) and _escape_field(element, prop, escape, is_list)
    }
    for prop, fields in _ENTRY_FIELDS.items():
        if not hasattr(element, prop):
            continue
        # Every entry, not up to the first changed one.
        entries_changed = [_escape_fields(e, fields) for e in getattr(element, prop)]
        if any(entries_changed):
            changed.add(prop)
    return sorted(changed)
