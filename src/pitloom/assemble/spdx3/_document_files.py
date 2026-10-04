# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 file-element assembly for :mod:`pitloom.assemble.spdx3.document`.

See also: :mod:`pitloom.assemble.spdx3.document`, the public entry point
that re-exports :func:`_add_package_files`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import build_file_declared_license
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.document import DocumentModel
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import ProjectFile, project_relative_or_fallback
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
from pitloom.id_registry import DIRECTORY_ENTITY_TYPE, IdRegistrySession

# SPDX 2.x FileType -> SPDX 3 SoftwarePurpose: only the categories with a
# clean, identity-shaped equivalent. BINARY/AUDIO/IMAGE/TEXT/VIDEO
# (media-kind categories) and anything unrecognized have no
# SoftwarePurpose equivalent -- SPDX 3's own spec is explicit that
# SoftwarePurpose is "intrinsic to how the Element is being used rather
# than the content of the Element", a genuinely different axis from a
# file's content/media kind. Never derive a mapping from `contentType`
# for these -- see working-docs/design/file-headers.md.
_FILE_TYPE_TO_SOFTWARE_PURPOSE: dict[str, str] = {
    "SOURCE": spdx3.software_SoftwarePurpose.source,
    "ARCHIVE": spdx3.software_SoftwarePurpose.archive,
    "APPLICATION": spdx3.software_SoftwarePurpose.application,
    "DOCUMENTATION": spdx3.software_SoftwarePurpose.documentation,
    "OTHER": spdx3.software_SoftwarePurpose.other,
    "SPDX": spdx3.software_SoftwarePurpose.bom,
}


@lru_cache(maxsize=1)
def _magika_version() -> str:
    """Best-effort ``magika`` package version for the ``detected``-role
    provenance ``Tool:`` segment. Falls back to ``"unknown"`` if the
    version can't be resolved -- shouldn't happen in practice, since
    ``content_type_method == "magika"`` is only ever set after ``magika``
    actually ran successfully earlier in this same process.

    Cached for process lifetime -- the installed version can't change
    mid-process, and this is called once per file whose content type was
    magika-detected, same rationale as ``_get_magika()`` in
    :mod:`pitloom.extract._file_headers`.
    """
    try:
        return _pkg_version("magika")
    except PackageNotFoundError:
        return "unknown"


# pylint: disable-next=too-many-arguments
def _emit_file_header_metadata(
    package_entry: spdx3.software_File,
    package_file: ProjectFile,
    spdx_ci: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> None:
    """Wire one file's SPDX-header-derived metadata onto *package_entry*.

    Native fields (``software_copyrightText``, ``software_primaryPurpose``,
    ``contentType``, a ``hasDeclaredLicense`` relationship) get their
    actual value set directly; the accompanying provenance Annotation
    records only *where* each came from -- role ``declared`` for
    everything read from the file's own header, ``detected`` for
    ``content_type`` resolved by Pitloom's own magika/extension-guess
    detection, or ``sbomAuthorSupplied`` when it instead came from a
    matching ``[[tool.pitloom.content-type.override]]`` entry (the config
    author's own assertion, not something Pitloom detected) -- see
    ``working-docs/implementation/annotation-provenance.md``'s role
    vocabulary. ``file_type``/``file_contributors`` values with no native
    SPDX 3 slot go into ``package_entry.summary`` instead, as one sorted
    ``"Key: value; Key: value"`` string -- never onto
    ``software_primaryPurpose``/``software_additionalPurpose``, which the
    SPDX 3 spec defines as being about usage, not content.

    Nothing is emitted when *package_file* carries no header-derived data
    at all (every field checked here is falsy) -- a project can have
    thousands of files; only ones that actually said something get an
    entry, unlike the dependency-completeness ``NOASSERTION`` policy in
    :mod:`pitloom.assemble.spdx3.deps`, which applies to a handful of
    packages, not every source file.
    """
    # physical_path is normally project-root-relative and therefore
    # already stable across runs; the one exception is a build-and-read
    # discovered file (see ProjectFile.physical_path's docstring), whose
    # physical_path is an absolute path into a fresh tempfile.mkdtemp()
    # directory that differs every run -- baking that into a "Source:"
    # provenance string would break SBOM determinism (CLAUDE.md's "SBOM
    # output" invariant) even though the file's own content is
    # unchanged. distribution_path is always deterministic, so use it
    # instead whenever physical_path isn't project-relative.
    file_path = project_relative_or_fallback(
        package_file.physical_path, package_file.distribution_path
    )
    field_provenance: dict[str, str] = {}
    summary_entries: list[tuple[str, str]] = []

    if package_file.copyright_text:
        package_entry.software_copyrightText = package_file.copyright_text
        field = (
            "SPDX-FileCopyrightText"
            if package_file.copyright_source == "spdx_tag"
            else "bare Copyright line"
        )
        field_provenance["copyright_text"] = f"Source: {file_path} | Field: {field}"

    if package_file.file_type:
        purpose = _FILE_TYPE_TO_SOFTWARE_PURPOSE.get(package_file.file_type)
        if purpose:
            package_entry.software_primaryPurpose = purpose
        else:
            summary_entries.append(("FileType", package_file.file_type))
        field_provenance["file_type"] = f"Source: {file_path} | Field: SPDX-FileType"

    if package_file.content_type:
        package_entry.contentType = package_file.content_type
        if package_file.content_type_method == "config_override":
            # A [[tool.pitloom.content-type.override]] match -- the
            # config author asserted this value directly, Pitloom
            # detected nothing, so role sbomAuthorSupplied rather than the
            # detected shape below (see working-docs/design/file-headers.md).
            segment = "Role: sbomAuthorSupplied"
        elif package_file.content_type_method == "magika":
            segment = (
                f"Method: magika_content_detection | Tool: magika=={_magika_version()}"
            )
        else:
            segment = "Method: extension_guess"
        field_provenance["content_type"] = f"Source: {file_path} | {segment}"

    if package_file.file_contributors:
        summary_entries.extend(
            ("Contributor", name) for name in package_file.file_contributors
        )
        field_provenance["file_contributors"] = (
            f"Source: {file_path} | Field: SPDX-FileContributor"
        )

    if summary_entries:
        # Canonical: feeds package_entry.summary, an SBOM output field
        # (see docstring above) -- not cosmetic iteration order.
        summary_entries.sort()
        package_entry.summary = "; ".join(f"{k}: {v}" for k, v in summary_entries)

    if field_provenance:
        emit_provenance(
            subject=package_entry,
            provenance=field_provenance,
            creation_info=spdx_ci,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

    _emit_file_license_relationship(
        package_entry,
        package_file,
        file_path,
        spdx_ci,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _emit_file_license_relationship(
    package_entry: spdx3.software_File,
    package_file: ProjectFile,
    file_path: str,
    spdx_ci: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> None:
    """Build *package_entry*'s ``hasDeclaredLicense`` relationship from the
    file's own ``SPDX-License-Identifier:`` header tag, if it has one."""
    license_id = package_file.spdx_license_identifier
    if not license_id:
        return
    license_provenance = f"Source: {file_path} | Field: SPDX-License-Identifier"

    relationship = build_file_declared_license(
        license_id,
        require_spdx_id(package_entry),
        license_provenance,
        spdx_ci,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    if relationship:
        exporter.add_relationship(relationship)


@dataclass(frozen=True)
class _FileAssemblyContext:
    """Shared, unchanging context threaded through directory/file
    assembly for one document build -- bundled so
    :func:`_ensure_directory_chain` takes it as a single argument instead
    of five positional ones."""

    main_package: spdx3.software_Package
    spdx_ci: spdx3.CreationInfo
    doc_name: str
    doc_uuid: str
    exporter: Spdx3JsonExporter


def _resolve_directory_hits_for_file(
    dist_path: Path,
    session: IdRegistrySession,
    dir_hits: dict[str, str],
    seen_dirs: set[str],
) -> None:
    """Resolve and claim a registry hit for each not-yet-seen ancestor
    directory of *dist_path* (root-to-leaf), updating *dir_hits* in
    place.

    *seen_dirs* remembers every directory this pass has already resolved
    -- hit, rejected by *session*, or lookup miss -- so a directory
    shared by many files (the common case) is looked up and claimed at
    most once. Checking membership in *dir_hits* instead would miss the
    rejected/miss cases (neither adds a *dir_hits* entry), so every
    later file under that directory would re-look it up and, on a
    rejection, re-log the same collision ``WARNING:`` once per file
    instead of once per directory. Split out of
    :func:`_resolve_file_and_directory_hits` to keep its own cognitive
    complexity down.
    """
    for directory_path in list(dist_path.parents)[::-1]:
        directory_name = directory_path.as_posix()
        if not directory_path.name or directory_name in seen_dirs:
            continue
        seen_dirs.add(directory_name)
        claimed_id = session.entity_id(
            directory_name, [directory_name], DIRECTORY_ENTITY_TYPE
        )
        if claimed_id is not None:
            dir_hits[directory_name] = claimed_id


def _resolve_file_and_directory_hits(
    files: list[ProjectFile],
    session: IdRegistrySession,
) -> tuple[dict[str, str], dict[str, str]]:
    """Pre-resolve every file's and directory's registry hit in one pass
    over *files*, before any minting starts.

    Returns ``(dir_hits, file_hits)``: *dir_hits* keyed by directory name
    (as :func:`_ensure_directory_chain` computes it, POSIX-style
    parent-path segment), *file_hits* keyed by ``distribution_path``. Both
    empty when *session* has no registry loaded. Callers must reserve
    every value in both dicts (:func:`~pitloom.core.models.reserve_spdx_ids`)
    before minting anything, then pass these dicts down instead of the
    registry itself: pre-resolution is the single source of truth for
    which ids were reserved, so the actual build must never look the
    registry up a second time and risk a different answer.

    *files* is walked in its own given order, and each file's directories
    root-to-leaf, so hit resolution is deterministic; when a directory or
    file's registry hit is an id something earlier in this same pass (or
    an earlier file/directory/AI-model hit in the same document, via the
    shared *session*) already claimed, only the first claimant reuses it
    -- a later one falls back to a fresh mint instead of duplicating the
    id, with one ``WARNING: ID registry: ...`` naming both.
    """
    dir_hits: dict[str, str] = {}
    file_hits: dict[str, str] = {}
    if session.registry is None:
        return dir_hits, file_hits
    seen_dirs: set[str] = set()

    for package_file in files:
        dist_path = Path(package_file.distribution_path)
        _resolve_directory_hits_for_file(dist_path, session, dir_hits, seen_dirs)

        file_digest = cast(str, package_file.digest_sha256)
        physical_lookup_key = project_relative_or_fallback(
            package_file.physical_path, package_file.distribution_path
        )
        lookup_paths = (
            [physical_lookup_key, package_file.distribution_path]
            if physical_lookup_key != package_file.distribution_path
            else [physical_lookup_key]
        )
        claimed_id = session.file_id(
            package_file.distribution_path, lookup_paths, file_digest
        )
        if claimed_id is not None:
            file_hits[package_file.distribution_path] = claimed_id

    return dir_hits, file_hits


def _ensure_directory_chain(
    parent_paths: list[Path],
    dir_spdx_ids: dict[str, str],
    dir_hits: dict[str, str],
    ctx: _FileAssemblyContext,
) -> None:
    """Ensure a ``software_File``(directory) element and ``contains``
    relationship exist for every not-yet-seen directory in *parent_paths*
    (root-to-leaf order), updating *dir_spdx_ids* in place.

    *dir_hits* is the pre-resolved, already-reserved map from
    :func:`_resolve_file_and_directory_hits` -- the single source of
    truth for what was reserved, so a hit here is reused as-is, never
    looked up again.
    """
    for index, directory_path in enumerate(parent_paths):
        directory_name = directory_path.as_posix()
        if directory_name in dir_spdx_ids:
            continue

        directory_file = spdx3.software_File(
            spdxId=dir_hits.get(directory_name)
            or generate_spdx_id("File", doc_name=ctx.doc_name, doc_uuid=ctx.doc_uuid),
            name=directory_name,
            creationInfo=ctx.spdx_ci,
        )
        directory_file.software_fileKind = spdx3.software_FileKindType.directory
        ctx.exporter.add_file(directory_file)
        dir_spdx_ids[directory_name] = require_spdx_id(directory_file)

        parent_id = (
            ctx.main_package.spdxId
            if index == 0
            else dir_spdx_ids[parent_paths[index - 1].as_posix()]
        )
        rel = build_relationship(
            from_id=parent_id,
            to_ids=[require_spdx_id(directory_file)],
            rel_type=spdx3.RelationshipType.contains,
            doc_name=ctx.doc_name,
            doc_uuid=ctx.doc_uuid,
            creation_info=ctx.spdx_ci,
        )
        if rel:
            ctx.exporter.add_relationship(rel)


# pylint: disable=too-many-locals
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _add_package_files(
    doc: DocumentModel,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    dir_hits: dict[str, str] | None = None,
    file_hits: dict[str, str] | None = None,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> dict[str, str]:
    """Add package files and directory containment relationships.

    *dir_hits*/*file_hits* are the pre-resolved registry hits from
    :func:`_resolve_file_and_directory_hits` (already reserved by the
    caller before the first mint -- see that function's docstring); a hit
    reuses the registered ``spdxId`` instead of minting a fresh one, so
    this element and the ``software_File`` a ``pitloom.loom`` fragment
    emits for the same script become literally the same element once
    merged (see :func:`pitloom.assemble.spdx3.fragments.merge_fragments`).
    A miss (not in the dict) falls back to the existing deterministic
    minting -- unchanged behaviour when no registry applies (both
    ``None``/empty).

    When a ``package_file`` carries SPDX-header-derived data (see
    :class:`pitloom.core.project.ProjectFile`), it's wired onto the
    resulting ``software_File`` element by
    :func:`_emit_file_header_metadata` -- *provenance_config*/*encoder*
    are forwarded there.
    """
    metadata = doc.project
    dir_hits = dir_hits or {}
    file_hits = file_hits or {}
    file_spdx_ids: dict[str, str] = {}
    dir_spdx_ids: dict[str, str] = {}
    ctx = _FileAssemblyContext(main_package, spdx_ci, metadata.name, doc_uuid, exporter)

    for package_file in metadata.files:
        dist_path = Path(package_file.distribution_path)
        parent_paths = [p for p in list(dist_path.parents)[::-1] if p.name]

        _ensure_directory_chain(parent_paths, dir_spdx_ids, dir_hits, ctx)

        # ProjectFile.digest_sha256 is typed Optional to accommodate
        # get_wheel_files(skip_merkle_root=True) (see embed.py), but
        # metadata.files here is always either the wheel's own
        # post-merge files or a get_wheel_files() call with the default
        # skip_merkle_root=False -- never the skip-hashing path -- so
        # the digest is always populated in practice.
        file_digest = cast(str, package_file.digest_sha256)

        registered_id = file_hits.get(package_file.distribution_path)
        package_entry = spdx3.software_File(
            spdxId=registered_id
            or generate_spdx_id("File", doc_name=metadata.name, doc_uuid=doc_uuid),
            name=package_file.distribution_path,
            creationInfo=spdx_ci,
        )
        package_entry.software_fileKind = spdx3.software_FileKindType.file
        package_entry.verifiedUsing = [sha256_hash(file_digest)]
        exporter.add_file(package_entry)
        _emit_file_header_metadata(
            package_entry,
            package_file,
            spdx_ci,
            metadata.name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
        file_spdx_ids[package_file.distribution_path] = require_spdx_id(package_entry)

        parent_id = (
            dir_spdx_ids[parent_paths[-1].as_posix()]
            if parent_paths
            else main_package.spdxId
        )
        rel2 = build_relationship(
            from_id=parent_id,
            to_ids=[require_spdx_id(package_entry)],
            rel_type=spdx3.RelationshipType.contains,
            doc_name=metadata.name,
            doc_uuid=doc_uuid,
            creation_info=spdx_ci,
        )
        if rel2:
            exporter.add_relationship(rel2)

    return file_spdx_ids
