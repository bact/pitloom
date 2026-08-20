# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials.

See Also:
    :mod:`pitloom.core._models_wheel` for wheel file scanning and header parsing.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID, uuid4, uuid5

from hatchling.metadata.utils import normalize_requirement
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core._models_wheel import (
    _FileHeaderExtras,
    _resolve_file_header_extras,
    get_wheel_files,
)

# Fixed pitloom namespace UUID, stable across all versions.
# Derived from: uuid5(NAMESPACE_URL, "https://github.com/bact/pitloom")
# DO NOT CHANGE: Modifying this constant will break the deterministic
# nature of all previously generated SBOM document UUIDs.
PITLOOM_NS = UUID("aecb050b-c1a4-5c3f-aaa7-d8e12dee7e5b")

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 ...
#              (uuid, "Relationship")     -> 1, 2, 3 ...
_ID_COUNTERS: dict[tuple[str, str], int] = {}

__all__ = [
    "PITLOOM_NS",
    "_FileHeaderExtras",
    "_ID_COUNTERS",
    "_build_merkle_tree",
    "_clear_doc_counters",
    "_resolve_file_header_extras",
    "build_pypi_purl",
    "build_relationship",
    "compute_doc_uuid",
    "generate_spdx_id",
    "get_wheel_files",
    "normalize_dependency_specifier",
]


def normalize_dependency_specifier(dep: str) -> str:
    """Return *dep* with its package name canonicalized to PEP 503 form."""
    try:
        req = Requirement(dep)
    except InvalidRequirement:
        return dep
    normalize_requirement(req)
    return str(req)


def build_pypi_purl(name: str, version: str | None) -> str:
    """Return a canonical ``pkg:pypi/<name>[@<version>]`` Package URL."""
    base = f"pkg:pypi/{canonicalize_name(name)}"
    return f"{base}@{version}" if version else base


def _clear_doc_counters(doc_uuid: str) -> None:
    """Remove all ``_ID_COUNTERS`` entries for *doc_uuid*."""
    for key in list(_ID_COUNTERS):
        if key[0] == doc_uuid:
            del _ID_COUNTERS[key]


def _build_merkle_tree(leaf_hashes: list[bytes]) -> str:
    """Build a binary Merkle tree from *leaf_hashes* and return the root as hex."""
    nodes: list[bytes] = list(leaf_hashes)
    while len(nodes) > 1:
        next_level: list[bytes] = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                combined = hashlib.sha256(nodes[i] + nodes[i + 1]).digest()
            else:
                combined = nodes[i]  # unpaired: promote unchanged
            next_level.append(combined)
        nodes = next_level
    return nodes[0].hex()


_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?")


def _normalize_dep(dep: str) -> str:
    """Normalize the package-name portion of a dependency specifier."""
    dep = dep.strip()
    match = _DEP_NAME_RE.match(dep)
    if not match:
        return dep
    normalized_name = re.sub(r"[-_.]+", "-", match.group(0)).lower()
    return normalized_name + dep[match.end() :]


def compute_doc_uuid(
    name: str,
    version: str,
    dependencies: list[str],
    merkle_root: str | None = None,
) -> str:
    """Compute a deterministic UUIDv5 for the SPDX document."""
    normalized_deps = sorted(_normalize_dep(dep) for dep in dependencies)
    seed = "\x00".join([name, version, "\x00".join(normalized_deps)])
    if merkle_root is not None:
        seed += "\x00" + merkle_root
    return str(uuid5(PITLOOM_NS, seed))


def generate_spdx_id(
    prefix: str, doc_name: str = "pitloom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices."""
    current_doc_uuid = doc_uuid or str(uuid4())
    doc_namespace = f"https://spdx.org/spdxdocs/{doc_name}-{current_doc_uuid}"

    if prefix == "SpdxDocument":
        return doc_namespace

    counter_key = (current_doc_uuid, prefix)
    _ID_COUNTERS[counter_key] = _ID_COUNTERS.get(counter_key, 0) + 1
    seq_id = _ID_COUNTERS[counter_key]
    return f"{doc_namespace}#{prefix}-{seq_id}"


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def build_relationship(
    from_id: str | None,
    to_ids: list[str],
    rel_type: str,
    doc_name: str,
    doc_uuid: str,
    creation_info: spdx3.CreationInfo,
    rel_class: type[spdx3.Relationship] = spdx3.Relationship,
    id_suffix: str | None = None,
    **kwargs: Any,
) -> spdx3.Relationship | None:
    """Helper to cleanly instantiate SPDX 3 Relationship objects."""
    if from_id is None:
        return None

    spdx_id = generate_spdx_id(
        id_suffix or "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
    )
    return rel_class(
        spdxId=spdx_id,
        from_=from_id,
        to=to_ids,
        relationshipType=rel_type,
        creationInfo=creation_info,
        **kwargs,
    )
