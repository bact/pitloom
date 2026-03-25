# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials."""

from __future__ import annotations

from uuid import uuid4

_ID_COUNTERS: dict[str, int] = {}


def generate_spdx_id(
    prefix: str, doc_name: str = "loom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices.

    Args:
        prefix: The prefix for the SPDX ID (e.g., 'Person', 'Package', 'File')
        doc_name: The name of the document
        doc_uuid: Document UUID. If not provided, a new UUID will be generated.

    Returns:
        str: A unique SPDX ID.
    """
    current_doc_uuid = doc_uuid or str(uuid4())
    doc_namespace = f"https://spdx.org/spdxdocs/{doc_name}-{current_doc_uuid}"

    if prefix == "SpdxDocument":
        return doc_namespace

    if current_doc_uuid not in _ID_COUNTERS:
        _ID_COUNTERS[current_doc_uuid] = 0

    _ID_COUNTERS[current_doc_uuid] += 1
    seq_id = _ID_COUNTERS[current_doc_uuid]
    return f"{doc_namespace}#{prefix}-{seq_id}"
