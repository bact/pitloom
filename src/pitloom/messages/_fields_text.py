# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The value only the ``text-unsafe`` lines name: the SBOM properties whose
display text had an invisible or bidi control character escaped, each after
the label of the element it belongs to.

The labels and properties are closed tables here, since this package does
not import :mod:`pitloom.assemble`; a drift test holds them equal to
:mod:`pitloom.assemble.spdx3._display_text`'s.

See also: :mod:`pitloom.messages._fields` (every field, this one included)
and :mod:`pitloom.messages._text_unsafe` (the lines).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import joined

#: The labels naming the element a property belongs to (none for a model's
#: own package).
TEXT_LABELS: Final = (
    "base model",
    "base model relationship",
    "dataset",
    "dataset creator",
    "dataset relationship",
    "license",
    "model originator",
    "model supplier",
)

#: The properties whose display text is escaped: an element's own, then
#: those of a list property's entries, named by the list property.
TEXT_PROPERTIES: Final = (
    "name",
    "summary",
    "description",
    "comment",
    "software_packageVersion",
    "software_downloadLocation",
    "ai_limitation",
    "ai_informationAboutApplication",
    "ai_typeOfModel",
    "ai_domain",
    "dataset_dataCollectionProcess",
    "dataset_intendedUse",
    "dataset_dataPreprocessing",
    "dataset_knownBias",
    "dataset_anonymizationMethodUsed",
    "simplelicensing_licenseText",
    "simplelicensing_licenseExpression",
    "ai_hyperparameter",
    "externalRef",
    "externalIdentifier",
)


def _one_of(texts: tuple[str, ...]) -> str:
    """A pattern matching one of *texts*, the longest first."""
    return "|".join(re.escape(t) for t in sorted(texts, key=len, reverse=True))


#: One property, its element's label before it when it has one.
_PROPERTY: Final = f"(?:(?:{_one_of(TEXT_LABELS)}) )?(?:{_one_of(TEXT_PROPERTIES)})"

#: The ``text-unsafe`` lines' field.
TEXT_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "properties": Field(
            rf"{_PROPERTY}(?:, {_PROPERTY})*",
            joined,
            "<properties>",
            "the SBOM properties escaped, sorted and comma-separated, each after "
            "the element it belongs to (`dataset name`, `base model "
            "description`); a model's own property alone (`name`)",
        ),
    }
)
