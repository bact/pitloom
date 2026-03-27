# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials."""

from __future__ import annotations

import hashlib
import operator
import re
from pathlib import Path
from uuid import UUID, uuid4, uuid5

# Fixed pitloom namespace UUID, stable across all versions.
# Derived from: uuid5(NAMESPACE_URL, "https://github.com/bact/pitloom")
# DO NOT CHANGE: Modifying this constant will break the deterministic
# nature of all previously generated SBOM document UUIDs.
PITLOOM_NS = UUID("aecb050b-c1a4-5c3f-aaa7-d8e12dee7e5b")

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 …
#              (uuid, "Relationship")     -> 1, 2, 3 …
_ID_COUNTERS: dict[tuple[str, str], int] = {}


def _clear_doc_counters(doc_uuid: str) -> None:
    """Remove all ``_ID_COUNTERS`` entries for *doc_uuid*.

    Must be called at the start of each document assembly to guarantee that
    repeated builds of the same package (same deterministic *doc_uuid*) always
    produce the same element fragment IDs (``Person-1``, ``Package-1``, …).
    Without this reset, counters from a previous build in the same process
    would cause the second build to emit ``Person-2``, ``Package-2``, etc.
    """
    for key in list(_ID_COUNTERS):
        if key[0] == doc_uuid:
            del _ID_COUNTERS[key]


def compute_merkle_root(dirs: list[Path]) -> str | None:
    """Compute the SHA-256 Merkle root of all files in the given directories.

    Intended for computing a content fingerprint of the files that will be
    packaged into a wheel (i.e. the directories listed under
    ``[tool.hatch.build.targets.wheel] packages``).

    Files are sorted by their portable relative path (``/``-separated) so the
    result is deterministic across platforms.  Each leaf node is the SHA-256
    hash of a single file's raw bytes; internal nodes are the SHA-256 hash of
    the concatenation of their two children.  An unpaired node at any level is
    promoted unchanged.

    Args:
        package_dirs: Directories whose contents will be hashed.

    Returns:
        str: Hex-encoded Merkle root, or ``None`` if no files are found.
    """
    # Collect (dir_index, relative_posix_path, sha256_digest) for every file.
    # Sorting by (dir_index, relative_path) via operator.itemgetter gives a
    # fully deterministic order.
    file_entries: list[tuple[int, str, bytes]] = []
    for i, dir_ in enumerate(dirs):
        if not dir_.is_dir():
            continue
        for path in dir_.rglob("*"):
            if path.is_file():
                rel = path.relative_to(dir_).as_posix()
                file_entries.append(
                    (i, rel, hashlib.sha256(path.read_bytes()).digest())
                )

    if not file_entries:
        return None

    file_entries.sort(key=operator.itemgetter(0, 1))
    nodes: list[bytes] = [digest for _, _, digest in file_entries]
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


# Matches the package name at the start of a dependency specifier,
# e.g. "hatchling" in "hatchling>=1.28.0" or "Foo_Bar" in "Foo_Bar[extra]~=1.0".
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?")


def _normalize_dep(dep: str) -> str:
    """Normalize the package-name portion of a dependency specifier.

    Applies PEP 503 / PyPI canonical name rules to the leading name token:
    lowercase the name and collapse any run of ``-``, ``_``, or ``.`` to a
    single ``-``.  The version specifier and environment markers are left
    unchanged.

    Examples::

        "Foo_Bar>=1.0"          → "foo-bar>=1.0"
        "PyProject.Metadata"    → "pyproject-metadata"
        "tomli>=2.0; python_version<'3.11'"  → "tomli>=2.0; python_version<'3.11'"
    """
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
    """Compute a deterministic UUIDv5 for the SPDX document.

    The UUID is derived from the project's primary package name and version,
    the normalized sorted list of declared dependencies (``[project]
    dependencies`` in ``pyproject.toml``, optional dependencies excluded), and
    — when available — the Merkle root of all files that will be included in
    the wheel.  The same inputs always produce the same UUID, enabling
    reproducible builds and reproducible SBOMs.

    The resulting SPDX 3 document namespace is:
    ``https://spdx.org/spdxdocs/{name}-{uuid}``

    Args:
        name: Primary package name (from ``[project] name``).
        version: Primary package version (from ``[project] version``).
        dependencies: Declared dependencies from ``[project] dependencies``.
            Each specifier's package name is normalized per PEP 503 (lowercase,
            ``-``/``_``/``.`` collapsed to ``-``); the list is then sorted so
            canonical ordering is stable.
        merkle_root: Optional hex-encoded SHA-256 Merkle root of the wheel
            source files (see :func:`compute_merkle_root`).  When
            present, any change to the packaged source causes a new UUID.

    Returns:
        str: A deterministic UUIDv5 string.
    """
    normalized_deps = sorted(_normalize_dep(dep) for dep in dependencies)
    # Use NUL (\x00) as field separator: it cannot appear in package names
    # (PEP 508), version strings (PEP 440), or SHA-256 hex digests, so
    # different (name, version, deps, merkle_root) inputs always produce
    # distinct seeds with no delimiter-collision risk.
    seed = "\x00".join([name, version, "\x00".join(normalized_deps)])
    if merkle_root is not None:
        seed += "\x00" + merkle_root
    return str(uuid5(PITLOOM_NS, seed))


def generate_spdx_id(
    prefix: str, doc_name: str = "pitloom", doc_uuid: str | None = None
) -> str:
    """Generate a unique SPDX ID with UUID following SPDX 3 best practices.

    The namespace URL is ``https://spdx.org/spdxdocs/{doc_name}-{doc_uuid}``.
    All elements in the same document share this namespace; only the fragment
    (``#{prefix}-{n}``) differs.  Counters are per ``(doc_uuid, prefix)`` pair
    so each element type has its own independent sequence.

    For reproducible SBOMs, pass a deterministic ``doc_uuid`` computed with
    :func:`compute_doc_uuid` rather than a random UUID.

    Args:
        prefix: Element type label used in the fragment, e.g. ``"software_Package"``.
            Also determines which per-type counter is incremented.
        doc_name: The name of the *document* (i.e. the project name).
            Must be the same value for every element in a given document.
        doc_uuid: Document UUID.  Should be a deterministic value from
            :func:`compute_doc_uuid`; falls back to a random UUIDv4 if omitted.

    Returns:
        str: A unique SPDX ID.
    """
    current_doc_uuid = doc_uuid or str(uuid4())
    doc_namespace = f"https://spdx.org/spdxdocs/{doc_name}-{current_doc_uuid}"

    if prefix == "SpdxDocument":
        return doc_namespace

    counter_key = (current_doc_uuid, prefix)
    _ID_COUNTERS[counter_key] = _ID_COUNTERS.get(counter_key, 0) + 1
    seq_id = _ID_COUNTERS[counter_key]
    return f"{doc_namespace}#{prefix}-{seq_id}"
