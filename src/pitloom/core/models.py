# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials."""

from __future__ import annotations

from uuid import uuid4

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 …
#              (uuid, "Relationship")     -> 1, 2, 3 …
_ID_COUNTERS: dict[tuple[str, str], int] = {}


def generate_spdx_id(
    prefix: str, doc_name: str = "pitloom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices.

    The namespace URL is ``https://spdx.org/spdxdocs/{doc_name}-{doc_uuid}``.
    All elements in the same document share this namespace; only the fragment
    (``#{prefix}-{n}``) differs.  Counters are per ``(doc_uuid, prefix)`` pair
    so each element type has its own independent sequence.

    Args:
        prefix: Element type label used in the fragment, e.g. ``"software_Package"``.
            Also determines which per-type counter is incremented.
        doc_name: The name of the *document* (i.e. the project name).
            Must be the same value for every element in a given document.
        doc_uuid: Document UUID.  If not provided, a new UUID will be generated.

    Returns:
        str: A unique SPDX ID.
    """
    # TODO: Use deterministic UUIDv5 based on document content instead of random UUIDv4.
    current_doc_uuid = doc_uuid or str(uuid4())
    doc_namespace = f"https://spdx.org/spdxdocs/{doc_name}-{current_doc_uuid}"

    if prefix == "SpdxDocument":
        return doc_namespace

    counter_key = (current_doc_uuid, prefix)
    _ID_COUNTERS[counter_key] = _ID_COUNTERS.get(counter_key, 0) + 1
    seq_id = _ID_COUNTERS[counter_key]
    return f"{doc_namespace}#{prefix}-{seq_id}"
