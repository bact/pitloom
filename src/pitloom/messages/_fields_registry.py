# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the ID registry's lines name: an element's type, kind, name
and ``spdxId``, the namespace, and why an element is keyed by its name.

See also: :mod:`pitloom.messages._fields` (every field, these included).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.core.iri import NAMESPACE_EMPTY, NAMESPACE_PROBLEMS
from pitloom.messages._field_tables import ELEMENT_KINDS, KEY_REASONS, REGISTRY_PARTS
from pitloom.messages._field_type import QUOTED, Field
from pitloom.messages._field_writers import (
    entities_text,
    entity_text,
    plain_text,
    quoted_text,
)

#: What a line can say of a namespace it names: never empty (an empty
#: one has its own line, or is no document id).
_PRINTED_PROBLEMS: Final = tuple(p for p in NAMESPACE_PROBLEMS if p != NAMESPACE_EMPTY)

#: How a field naming an element or a namespace writes it; a meaning that
#: already says where the text comes from takes only the masking part.
_MASKED_MEANING: Final = (
    "a URL's credentials masked; in quotes, escaped, when it holds a control character"
)
_ENTITY_MEANING: Final = f"as given, {_MASKED_MEANING}"

#: The ID registry's fields.
REGISTRY_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "claimant": Field(
            r".+",
            entity_text,
            "<claimant>",
            "the other element, key or spelling that wants the same id or "
            f"holds it (a path, a name, `name@version`), {_ENTITY_MEANING}",
            free=True,
        ),
        "element_kind": Field(
            "|".join(re.escape(kind) for kind in ELEMENT_KINDS),
            plain_text,
            "<kind>",
            "what the element is: " + ", ".join(f"`{k}`" for k in ELEMENT_KINDS),
        ),
        "element_type": Field(
            QUOTED,
            quoted_text,
            "'<type>'",
            "an element type as the ID registry file names it, in quotes "
            "(`'software_File'`), escaped when it holds a control character",
        ),
        "entities": Field(
            r".+",
            entities_text,
            "<entities>",
            f"names or keys, comma-separated, each {_ENTITY_MEANING}",
            free=True,
        ),
        "entity": Field(
            r".+",
            entity_text,
            "<entity>",
            "an element's name or ID registry key (a path, a dataset or model "
            f"name, `name@version`), {_ENTITY_MEANING}",
            free=True,
        ),
        "key_reason": Field(
            "|".join(re.escape(reason) for reason in KEY_REASONS),
            plain_text,
            "<key-reason>",
            "why the element is keyed by its name, or files by their path as "
            "read: " + ", ".join(f"`{r}`" for r in KEY_REASONS),
        ),
        "namespace": Field(
            r".+",
            entity_text,
            "<namespace>",
            "a document namespace IRI, as an ID registry file or an SBOM "
            f"states it, {_MASKED_MEANING}",
            free=True,
        ),
        "given_namespace": Field(
            r".+",
            entity_text,
            "<given-namespace>",
            f"the namespace a command line or caller gives, {_MASKED_MEANING}",
            free=True,
        ),
        "namespace_problem": Field(
            "|".join(re.escape(problem) for problem in _PRINTED_PROBLEMS),
            plain_text,
            "<why>",
            "why a text cannot be a document namespace: "
            + ", ".join(f"`{p}`" for p in _PRINTED_PROBLEMS),
        ),
        "registry_part": Field(
            "|".join(re.escape(part) for part in REGISTRY_PARTS),
            plain_text,
            "<what>",
            "what of an element the ID registry cannot hold: "
            + ", ".join(f"`{part}`" for part in REGISTRY_PARTS),
        ),
        "spdx_id": Field(
            r".+",
            entity_text,
            "<spdx-id>",
            f"an element's spdxId, as held or read, {_MASKED_MEANING}",
            free=True,
        ),
    }
)
