# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 data models for representing software bill of materials."""

from __future__ import annotations

import hashlib
import operator
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID, uuid4, uuid5

from hatchling.metadata.utils import normalize_requirement
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.project import ProjectFile

if TYPE_CHECKING:
    # Type-only: core/ must not import from extract/ at runtime (see
    # get_wheel_files()'s own deferred imports below) -- this import is
    # erased before execution, so it doesn't violate that layering.
    from pitloom.extract._file_headers import FileHeaderMetadata

# Fixed pitloom namespace UUID, stable across all versions.
# Derived from: uuid5(NAMESPACE_URL, "https://github.com/bact/pitloom")
# DO NOT CHANGE: Modifying this constant will break the deterministic
# nature of all previously generated SBOM document UUIDs.
PITLOOM_NS = UUID("aecb050b-c1a4-5c3f-aaa7-d8e12dee7e5b")

# Counters keyed by (doc_uuid, element_type) so each type has its own sequence.
# For example: (uuid, "software_Package") -> 1, 2, 3 …
#              (uuid, "Relationship")     -> 1, 2, 3 …
_ID_COUNTERS: dict[tuple[str, str], int] = {}


def normalize_dependency_specifier(dep: str) -> str:
    """Return *dep* with its package name canonicalized to PEP 503 form.

    Parses *dep* as a :class:`packaging.requirements.Requirement` and applies
    Hatchling's own ``normalize_requirement()`` (lowercases the name and any
    extras, and collapses runs of ``-``/``_``/``.`` to a single ``-``) so
    that a dependency specifier is rendered identically regardless of which
    extractor produced it -- :func:`~pitloom.extract.pyproject.read_pyproject`
    (the CLI) or :func:`~pitloom.extract.hatchling.metadata_from_hatchling`
    (the Hatchling build hook). Both paths feed :func:`compute_doc_uuid`, so
    any drift here would give the same project two different document UUIDs
    depending on which path generated the SBOM.

    Unparseable specifiers are returned unchanged rather than dropped.
    """
    try:
        req = Requirement(dep)
    except InvalidRequirement:
        return dep
    normalize_requirement(req)
    return str(req)


def build_pypi_purl(name: str, version: str | None) -> str:
    """Return a canonical ``pkg:pypi/<name>[@<version>]`` Package URL.

    Uses :func:`packaging.utils.canonicalize_name` for PEP 503
    canonicalization (lowercase; runs of ``-``/``_``/``.`` collapsed to a
    single ``-``), so e.g. ``zope.interface`` yields
    ``pkg:pypi/zope-interface@...`` rather than the non-canonical
    ``pkg:pypi/zope.interface@...`` that a naive ``.replace("_", "-")``
    would produce (dots are left untouched by that substitution alone).

    *version* is optional -- the ``@<version>`` component is a purl-spec
    qualifier, not a requirement. Omitting it (``version=None``) still
    yields a valid, matchable identifier for a dependency whose exact
    version can't be resolved (e.g. an unpinned, platform-gated requirement
    that isn't installed in the current environment) -- preferable to
    leaving the package with no identifier at all.
    """
    base = f"pkg:pypi/{canonicalize_name(name)}"
    return f"{base}@{version}" if version else base


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


def _build_merkle_tree(leaf_hashes: list[bytes]) -> str:
    """Build a binary Merkle tree from *leaf_hashes* and return the root as hex.

    Each internal node is ``SHA-256(left_child || right_child)``.  An unpaired
    node at any level is promoted unchanged to the next level.

    Args:
        leaf_hashes: Non-empty list of SHA-256 digests for the leaf nodes.

    Returns:
        str: Hex-encoded root digest.
    """
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


class _FileHeaderExtras(TypedDict):
    """Keyword arguments for :class:`ProjectFile`'s header/content-type fields."""

    copyright_text: str | None
    copyright_source: str | None
    file_contributors: list[str]
    file_type: str | None
    spdx_license_identifier: str | None
    content_type: str | None
    content_type_method: str | None


def _resolve_file_header_extras(
    raw_bytes: bytes,
    filename: str,
    distribution_path: str,
    parse_header: Callable[[bytes], FileHeaderMetadata | None] | None,
    detect_content: Callable[[bytes, str, str], tuple[str | None, str | None]] | None,
    resolve_override: (
        Callable[[str, tuple[ContentTypeOverride, ...]], ContentTypeOverride | None]
        | None
    ),
    content_type_overrides: tuple[ContentTypeOverride, ...],
    content_type_method: str,
) -> _FileHeaderExtras:
    """Resolve the optional per-file header/content-type fields for *raw_bytes*.

    Returns :class:`ProjectFile` keyword arguments (empty/``None`` values
    when the corresponding detector wasn't requested at all) -- factored
    out of :func:`get_wheel_files` to keep its own body under the locals
    budget, not for reuse elsewhere.

    *resolve_override* is only ever passed (non-``None``) when
    *detect_content* is also requested -- overrides are a per-file
    refinement within the ``detect_content_type`` gate, not a way to
    bypass it (see :func:`get_wheel_files`). When it matches, it
    pre-empts *detect_content* entirely for this file.
    """
    header = parse_header(raw_bytes) if parse_header else None
    content_type: str | None = None
    resolved_method: str | None = None
    if detect_content:
        override = (
            resolve_override(distribution_path, content_type_overrides)
            if resolve_override
            else None
        )
        if override is not None:
            content_type = override.content_type
            resolved_method = "config_override"
        else:
            content_type, resolved_method = detect_content(
                raw_bytes, filename, content_type_method
            )
    return _FileHeaderExtras(
        copyright_text=header.copyright_text if header else None,
        copyright_source=header.copyright_source if header else None,
        file_contributors=header.file_contributors if header else [],
        file_type=header.file_type if header else None,
        spdx_license_identifier=(header.spdx_license_identifier if header else None),
        content_type=content_type,
        content_type_method=resolved_method,
    )


# pylint: disable=too-many-locals
def get_wheel_files(
    project_dir: Path,
    *,
    scan_file_headers: bool = False,
    detect_content_type: bool = False,
    content_type_method: str = "auto",
    content_type_overrides: tuple[ContentTypeOverride, ...] = (),
) -> tuple[str | None, list[ProjectFile]]:
    """Get all files included in the wheel and compute their SHA-256 Merkle root.

    Uses hatchling's :class:`~hatchling.builders.wheel.WheelBuilder` to
    discover the exact file set -- respecting every include/exclude rule,
    ``force-include`` entry, and ``packages`` configuration from
    ``pyproject.toml``.  Files are sorted by their ``distribution_path``
    (the canonical path inside the wheel), so both the hatchling build hook
    and the CLI produce the same root for the same project state.

    Args:
        project_dir: Project root directory containing ``pyproject.toml``.
        scan_file_headers: When ``True``, parse each file's leading comment
            header for SPDX-File* tags (see
            :func:`pitloom.extract._file_headers.parse_file_header`),
            reusing the bytes already read for hashing -- no second file
            read. Off by default at this function's own level; callers
            thread their own effective default (see
            ``[tool.pitloom] extract-file-header``).
        detect_content_type: When ``True``, also detect each file's real
            content type (see
            :func:`pitloom.extract._file_headers.guess_content_type`) --
            independent of ``scan_file_headers``, gated by its own
            separate parameter since it has a real per-file cost
            ``scan_file_headers`` alone does not.
        content_type_method: Which detector resolves ``contentType`` when
            ``detect_content_type`` is on: ``"auto"`` (default), ``"magika"``
            (raises ``RuntimeError`` up front, before scanning any file,
            when the ``magika`` package isn't installed -- see
            :func:`pitloom.extract._file_headers.require_magika_available`),
            or ``"extension"`` (skip ``magika`` entirely).
        content_type_overrides: Glob-pattern -> MIME-type entries (see
            :func:`pitloom.extract._file_headers.resolve_content_type_override`)
            that pre-empt ``guess_content_type`` for a matching file.
            Only takes effect when ``detect_content_type`` is also
            ``True`` -- a per-file refinement within that gate, not a way
            to bypass it; when ``detect_content_type`` is ``False``,
            overrides never fire, same as today.

    Returns:
        Tuple of (Hex-encoded Merkle root or None, List of ProjectFile objects).
    """
    # TODO: Update this when supporting setuptools or other build backends.
    # pylint: disable=import-outside-toplevel,cyclic-import
    from hatchling.builders.wheel import WheelBuilder  # runtime dep, local import

    parse_header = None
    if scan_file_headers:
        from pitloom.extract._file_headers import parse_file_header

        parse_header = parse_file_header

    detect_content = None
    resolve_override = None
    if detect_content_type:
        from pitloom.extract._file_headers import guess_content_type

        detect_content = guess_content_type

        if content_type_method == "magika":
            # Fail before scanning any file, not mid-scan -- the config
            # author demanded magika specifically.
            from pitloom.extract._file_headers import require_magika_available

            require_magika_available()

        # Overrides are only ever consulted when detection itself is
        # already on -- a per-file refinement within that gate, not a
        # separate bypass of it (see this function's own docstring).
        if content_type_overrides:
            from pitloom.extract._file_headers import resolve_content_type_override

            resolve_override = resolve_content_type_override

    try:
        builder = WheelBuilder(str(project_dir))
        project_files: list[ProjectFile] = []
        file_entries: list[tuple[str, bytes]] = []
        for included_file in builder.recurse_included_files():
            source = Path(included_file.path)
            if source.is_file():
                # Hatchling builds distribution_path with os.path.join, so
                # it carries backslashes on Windows -- unlike a wheel's
                # actual internal zip-entry paths, which the ZIP format
                # itself requires to be forward-slash-separated regardless
                # of host OS. Left un-normalized, this file's distribution
                # path (and thus this sort key, and thus the Merkle root
                # and doc_uuid built from it) would differ by build
                # platform for byte-identical source content. Normalizing
                # here matches physical_path's own .as_posix() a few lines
                # below, and is safe on every OS: pathlib accepts forward
                # slashes on Windows too.
                distribution_path = included_file.distribution_path.replace("\\", "/")
                raw_bytes = source.read_bytes()
                digest_bytes = hashlib.sha256(raw_bytes).digest()
                file_entries.append((distribution_path, digest_bytes))
                try:
                    rel_path = source.relative_to(project_dir).as_posix()
                except ValueError:
                    rel_path = source.as_posix()

                # This is the only point in the pipeline where the file's
                # bytes are still in memory -- header parsing/content-type
                # detection must happen here, not in the assembly layer,
                # which only ever sees the resolved ProjectFile fields
                # below (never the bytes themselves; holding every file's
                # bytes across a large project would be a memory blow-up).
                extras = _resolve_file_header_extras(
                    raw_bytes,
                    source.name,
                    distribution_path,
                    parse_header,
                    detect_content,
                    resolve_override,
                    content_type_overrides,
                    content_type_method,
                )
                project_files.append(
                    ProjectFile(
                        physical_path=rel_path,
                        distribution_path=distribution_path,
                        digest_sha256=digest_bytes.hex(),
                        **extras,
                    )
                )
    except Exception:  # pylint: disable=broad-exception-caught
        # hatchling raises ValueError when it cannot determine the file set
        # (e.g. no pyproject.toml, no recognisable package layout).  Treat
        # this the same as "no files found" so UUID computation degrades
        # gracefully to name + version + deps only.
        return None, []

    if not file_entries:
        return None, []

    file_entries.sort(key=operator.itemgetter(0))
    merkle_root = _build_merkle_tree([digest for _, digest in file_entries])
    return merkle_root, project_files


# Matches the package name at the start of a dependency specifier,
# e.g. "hatchling" in "hatchling>=1.31.0" or "Foo_Bar" in "Foo_Bar[extra]~=1.0".
_DEP_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?")


def _normalize_dep(dep: str) -> str:
    """Normalize the package-name portion of a dependency specifier.

    Applies PEP 503 / PyPI canonical name rules to the leading name token:
    lowercase the name and collapse any run of ``-``, ``_``, or ``.`` to a
    single ``-``.  The version specifier and environment markers are left
    unchanged.

    Examples::

        "Foo_Bar>=1.0"                       -> "foo-bar>=1.0"
        "PyProject.Metadata"                 -> "pyproject-metadata"
        "tomli>=2.0; python_version<'3.11'"  -> "tomli>=2.0; python_version<'3.11'"
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
    -- when available -- the Merkle root of all files that will be included in
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
            source files (see :func:`compute_wheel_merkle_root`).  When
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
