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
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4, uuid5

from hatchling.metadata.utils import normalize_requirement
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core._models_wheel import _resolve_file_header_extras, get_wheel_files
from pitloom.core._models_wheel_types import FileHeaderExtras
from pitloom.core.iri import doc_namespace, iri_segment

# Fixed pitloom namespace UUID, stable across all versions.
# Derived from: uuid5(NAMESPACE_URL, "https://github.com/bact/pitloom")
# DO NOT CHANGE: Modifying this constant will break the deterministic
# nature of all previously generated SBOM document UUIDs.
PITLOOM_NS = UUID("aecb050b-c1a4-5c3f-aaa7-d8e12dee7e5b")

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 ...
#              (uuid, "Relationship")     -> 1, 2, 3 ...
_ID_COUNTERS: dict[tuple[str, str], int] = {}

# Numbers a caller has reserved per (doc_uuid, prefix) -- see
# reserve_spdx_ids() -- because an IdRegistry already assigned them within
# this same document's namespace. generate_spdx_id() skips any reserved
# number instead of re-minting it, so a registry-supplied id merged into
# this document can never collide with a freshly-minted one.
_RESERVED: dict[tuple[str, str], set[int]] = {}

__all__ = [
    "PITLOOM_NS",
    "FileHeaderExtras",
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
    "reserve_spdx_ids",
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
    if version and version != "unknown":
        return f"{base}@{version.replace('+', '%2B')}"
    return base


def _clear_doc_counters(doc_uuid: str) -> None:
    """Remove all ``_ID_COUNTERS``/``_RESERVED`` entries for *doc_uuid*."""
    for key in list(_ID_COUNTERS):
        if key[0] == doc_uuid:
            del _ID_COUNTERS[key]
    for key in list(_RESERVED):
        if key[0] == doc_uuid:
            del _RESERVED[key]


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
    locked_dependencies: list[str] | None = None,
    locked_dependencies_provenance: str | None = None,
) -> str:
    """Compute a deterministic UUIDv5 for the SPDX document.

    *locked_dependencies* (e.g. ``poetry.lock``-resolved transitive
    dependencies) is folded into the seed too, whenever either it or
    *locked_dependencies_provenance* is given -- otherwise two documents
    with identical direct dependencies but different lock-resolved
    graphs would collide on the same UUID despite describing different
    dependency content. Both omitted leave the seed byte-identical to a
    document with no locked dependencies at all, so every non-Poetry
    (and lock-less Poetry) document is unaffected.

    *locked_dependencies_provenance* (the resolved
    ``ProjectMetadata.provenance["locked_dependencies"]`` string, e.g.
    ``"Source: pylock.toml | Method: resolved_lockfile"``) is folded in
    too, alongside *locked_dependencies* itself: as more lock/pin formats
    land in ``pitloom.extract.lock.cascade``'s cascade, two
    different formats can plausibly resolve to the identical dependency
    set for a small
    project -- e.g. a ``poetry.lock``-only run and a ``pylock.toml``-only
    run of the same project landing on the same pins. Seeding on
    dependency content alone would collide those two documents' UUIDs
    despite their generated ``provenance["locked_dependencies"]`` fields
    (and any override note) differing -- a real content difference the
    seed is supposed to guard against.

    Deliberately keyed on *either* argument being given, not just
    *locked_dependencies* being non-empty: a real, successfully-resolved
    lock file that legitimately has zero runtime dependencies still
    carries its own distinct provenance string, which must still
    distinguish that document from one with no lock present at all, or
    from a different lock source that also happened to resolve to zero
    dependencies -- gating on non-empty *locked_dependencies* alone would
    silently collide all three onto the same UUID.
    """
    normalized_deps = sorted(_normalize_dep(dep) for dep in dependencies)
    seed = "\x00".join([name, version, "\x00".join(normalized_deps)])
    if locked_dependencies or locked_dependencies_provenance:
        # A real, valid lock resolving to zero dependencies still has a
        # *provenance* string that differs from "no lock at all" (and
        # from a different lock source that also resolved to empty) --
        # gating this whole block on `locked_dependencies` being
        # non-empty would fold in neither, silently colliding an
        # empty-but-real lock's UUID with a lockless document's.
        normalized_locked = sorted(
            _normalize_dep(dep) for dep in (locked_dependencies or [])
        )
        seed += "\x00" + "\x00".join(normalized_locked)
        if locked_dependencies_provenance:
            seed += "\x00" + locked_dependencies_provenance
    if merkle_root is not None:
        seed += "\x00" + merkle_root
    return str(uuid5(PITLOOM_NS, seed))


def generate_spdx_id(
    prefix: str, doc_name: str = "pitloom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices.

    *prefix* and *doc_name* are raw names: both pass through
    :func:`~pitloom.core.iri.iri_segment`, so the id is a valid IRI.
    """
    current_doc_uuid = doc_uuid or str(uuid4())
    namespace = doc_namespace(doc_name, current_doc_uuid)

    if prefix == "SpdxDocument":
        return namespace

    prefix = iri_segment(prefix)

    counter_key = (current_doc_uuid, prefix)
    reserved = _RESERVED.get(counter_key, ())
    seq_id = _ID_COUNTERS.get(counter_key, 0) + 1
    while seq_id in reserved:
        seq_id += 1
    _ID_COUNTERS[counter_key] = seq_id
    return f"{namespace}#{prefix}-{seq_id}"


def reserve_spdx_ids(doc_name: str, doc_uuid: str, spdx_ids: Iterable[str]) -> None:
    """Reserve every number *spdx_ids* already uses in (*doc_name*,
    *doc_uuid*)'s own document namespace, so a later :func:`generate_spdx_id`
    call for the same ``(doc_uuid, prefix)`` skips it instead of re-minting a
    duplicate.

    Intended for a registry auto-harvested from an earlier run of the exact
    same document (same name/version/dependencies -> same deterministic
    *doc_uuid*): the registry looks ids up by content hash/name first (see
    ``pitloom.id_registry.IdRegistry.lookup_file``/``lookup_entity``), and only a
    lookup *miss* falls back to minting here -- without a reservation, a
    fresh mint doesn't know the registry already claimed a number in this
    same namespace and can hand out a duplicate. Call once per document,
    right after :func:`_clear_doc_counters`, before the first
    ``generate_spdx_id`` call for it. An id in a different namespace (a
    registry entry harvested from an unrelated document) is ignored -- only
    the ``prefix``/``n`` suffix matters, matched with a greedy prefix (e.g.
    ``AIPackage-my-model-3`` -> prefix ``AIPackage-my-model``, n=``3``).
    """
    namespace = doc_namespace(doc_name, doc_uuid)
    pattern = re.compile(rf"^{re.escape(namespace)}#(?P<prefix>.+)-(?P<n>\d+)$")
    for spdx_id in spdx_ids:
        match = pattern.match(spdx_id)
        if not match:
            continue
        counter_key = (doc_uuid, match.group("prefix"))
        _RESERVED.setdefault(counter_key, set()).add(int(match.group("n")))


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
