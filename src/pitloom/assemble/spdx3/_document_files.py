# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SPDX 3 file-element assembly for :mod:`pitloom.assemble.spdx3.document`.

See also: :mod:`pitloom.assemble.spdx3.document`, the public entry point
that re-exports :func:`_add_package_files`.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import build_file_declared_license
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.document import DocumentModel
from pitloom.core.models import build_relationship, generate_spdx_id
from pitloom.core.project import ProjectFile
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
from pitloom.ids import IdRegistry

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
    file_path = package_file.physical_path
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

    if package_file.spdx_license_identifier:
        exporter.add_relationship(
            build_file_declared_license(
                package_file.spdx_license_identifier,
                require_spdx_id(package_entry),
                f"Source: {file_path} | Field: SPDX-License-Identifier",
                spdx_ci,
                doc_name,
                doc_uuid,
                exporter,
                provenance_config=provenance_config,
                encoder=encoder,
            )
        )


# pylint: disable=too-many-locals
# pylint: disable-next=too-many-arguments
def _add_package_files(
    doc: DocumentModel,
    main_package: spdx3.software_Package,
    spdx_ci: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    registry: IdRegistry | None = None,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> dict[str, str]:
    """Add package files and directory containment relationships.

    When *registry* is given, each wheel file's id is looked up by content
    hash under its physical (project-root-relative) path first, then its
    distribution (in-package) path (:meth:`~pitloom.ids.IdRegistry.lookup_file`,
    tried twice -- the two paths differ for any src/-layout project, and
    auto-harvested entries can only ever carry the distribution path); a
    match reuses the registered ``spdxId`` instead of minting a fresh one,
    so this element and the ``software_File`` a ``pitloom.loom`` fragment
    emits for the same script become literally the same element once merged
    (see :func:`pitloom.assemble.spdx3.fragments.merge_fragments`). A miss
    (not registered under either path, or a stale/mismatched hash) falls
    back to the existing deterministic minting -- unchanged behaviour when
    no registry applies.

    When a ``package_file`` carries SPDX-header-derived data (see
    :class:`pitloom.core.project.ProjectFile`), it's wired onto the
    resulting ``software_File`` element by
    :func:`_emit_file_header_metadata` -- *provenance_config*/*encoder*
    are forwarded there.
    """
    metadata = doc.project
    file_spdx_ids: dict[str, str] = {}
    dir_spdx_ids: dict[str, str] = {}

    for package_file in metadata.files:
        dist_path = Path(package_file.distribution_path)
        parent_paths = [p for p in list(dist_path.parents)[::-1] if p.name]

        for index, directory_path in enumerate(parent_paths):
            directory_name = directory_path.as_posix()
            if directory_name in dir_spdx_ids:
                continue

            directory_file = spdx3.software_File(
                spdxId=generate_spdx_id(
                    "File", doc_name=metadata.name, doc_uuid=doc_uuid
                ),
                name=directory_name,
                creationInfo=spdx_ci,
            )
            directory_file.software_fileKind = spdx3.software_FileKindType.directory
            exporter.add_file(directory_file)
            dir_spdx_ids[directory_name] = require_spdx_id(directory_file)

            parent_id = (
                main_package.spdxId
                if index == 0
                else dir_spdx_ids[parent_paths[index - 1].as_posix()]
            )
            rel1 = build_relationship(
                from_id=parent_id,
                to_ids=[require_spdx_id(directory_file)],
                rel_type=spdx3.RelationshipType.contains,
                doc_name=metadata.name,
                doc_uuid=doc_uuid,
                creation_info=spdx_ci,
            )
            if rel1:
                exporter.add_relationship(rel1)

        registered_id = None
        if registry is not None:
            # physical_path (project-root-relative, e.g. from `pitloom ids
            # generate`'s filesystem scan) is tried first; distribution_path
            # (the built package's internal path -- the only path a
            # software_File element's `name` field actually carries, so
            # it's what auto-harvest keys files by, see
            # `pitloom.ids.IdRegistry.harvest`) is the fallback. The two
            # differ for any src/-layout project, where auto-harvest's
            # entries would otherwise never be found again.
            registered_id = registry.lookup_file(
                package_file.physical_path, package_file.digest_sha256
            ) or registry.lookup_file(
                package_file.distribution_path, package_file.digest_sha256
            )
        package_entry = spdx3.software_File(
            spdxId=registered_id
            or generate_spdx_id("File", doc_name=metadata.name, doc_uuid=doc_uuid),
            name=package_file.distribution_path,
            creationInfo=spdx_ci,
        )
        package_entry.software_fileKind = spdx3.software_FileKindType.file
        package_entry.verifiedUsing = [sha256_hash(package_file.digest_sha256)]
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
