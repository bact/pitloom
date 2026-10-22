# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for Python wheels (Analyzed SBOM)."""

from __future__ import annotations

import email.message
import logging
import zipfile
from pathlib import Path
from typing import TypedDict

from pitloom._wheel_sbom_location import name_version_from_email_message
from pitloom.core.file_hash import DigestHasher
from pitloom.core.models import archive_base_name
from pitloom.core.project import (
    FilesOrigin,
    ProjectFile,
    ProjectMetadata,
    digest_fields,
)
from pitloom.core.quote_source import quote_source
from pitloom.core.wheel_dist_info import (
    open_wheel_zip,
    read_metadata_headers,
    refuse_unreadable,
    resolve_own_dist_info,
    wheel_members,
)
from pitloom.extract._core_metadata import (
    core_metadata_license_with_source,
    parse_core_metadata_authors,
    parse_project_urls,
)
from pitloom.extract._license_detect import (
    LICENSE_FILE_CAP,
    LICENSE_FILE_MAX_BYTES,
    pick_license_names,
)
from pitloom.extract.authors import AuthorSplit
from pitloom.extract.copyright_notices import apply_in_package_copyright
from pitloom.logging_config import warn_over_cap

log = logging.getLogger(__name__)


def _hash_wheel_entry(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, name: str, archive: str
) -> ProjectFile:
    """Compute the SHA-256 and SHA-512 of a wheel entry in streaming chunks.

    *name* is the entry's install-location name (see
    :func:`pitloom.core.archive_member_names.zip_file_members`), the
    ``distribution_path``. ``physical_path`` is the raw archive name, so a
    registry keyed by it before names were normalised still hits.

    Raises:
        ValueError: The member cannot be read (damaged, encrypted,
            unsupported, badly named): the wheel is refused as a whole.
    """
    hasher = DigestHasher()
    with refuse_unreadable(archive, info.orig_filename), zf.open(info) as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return ProjectFile(
        physical_path=info.orig_filename,
        distribution_path=name,
        **digest_fields(hasher.digests()),
    )


def _license_members(
    zf: zipfile.ZipFile,
    members: list[tuple[str, zipfile.ZipInfo]],
    prefix: str,
    wheel: Path,
) -> dict[str, bytes]:
    """The licence files of the own ``.dist-info`` *prefix*, basename to
    bytes: the names
    :func:`~pitloom.extract._license_detect.pick_license_names` picks among the
    files right in its ``licenses/`` (PEP 639), then right in it (an older
    wheel), a name in ``licenses/`` winning. One over the size cap is warned
    about, as *wheel*:name, and left out."""
    found: dict[str, bytes] = {}
    for folder in (f"{prefix}licenses/", prefix):
        # A nested name ("vendor/LICENSE") is no licence-file name.
        here = {
            name[len(folder) :]: info
            for name, info in members
            if name.startswith(folder)
        }
        for base in pick_license_names(here):
            if base in found:
                continue
            # Read whole above (hashed): a damaged member refused the wheel.
            with zf.open(here[base]) as fh:
                raw = fh.read(LICENSE_FILE_MAX_BYTES + 1)
            if len(raw) > LICENSE_FILE_MAX_BYTES:
                warn_over_cap(
                    log, LICENSE_FILE_CAP, f"{wheel}:{folder}{base}", once=True
                )
                continue
            found[base] = raw
    return found


def _parse_metadata_urls(msg: email.message.Message) -> dict[str, str]:
    """Extract URLs from email METADATA message."""
    return parse_project_urls(msg, include_download=True)


def _populate_metadata_from_email(
    metadata: ProjectMetadata,
    provenance: dict[str, str],
    msg: email.message.Message,
    source: str,
    author_splits: list[AuthorSplit] | None = None,
) -> None:
    """Populate ProjectMetadata and provenance from parsed METADATA msg;
    *author_splits* as for :func:`read_wheel`."""
    name, version = name_version_from_email_message(msg)
    if name:
        metadata.name = name
        provenance["name"] = source
    if version:
        metadata.version = version
        provenance["version"] = source
    if msg.get("Summary"):
        metadata.description = msg["Summary"]
    if msg.get("Requires-Python"):
        metadata.requires_python = msg["Requires-Python"]

    license_name, license_source = core_metadata_license_with_source(msg, source)
    if license_name:
        metadata.license_name = license_name
        provenance["license"] = license_source

    reqs = msg.get_all("Requires-Dist")
    if reqs:
        metadata.dependencies = reqs
        provenance["dependencies"] = source

    metadata.authors = parse_core_metadata_authors(msg, splits=author_splits)
    if metadata.authors:
        provenance["authors"] = source
    metadata.urls = _parse_metadata_urls(msg)


def wheel_identity(metadata: ProjectMetadata) -> tuple[str | None, str | None]:
    """The (name, version) the wheel's ``METADATA`` declared, from what
    :func:`read_wheel` returned: ``None`` for each it did not.

    ``metadata.name`` is the sentinel ``"unknown"`` where the header is
    absent, so only ``provenance`` says whether either was read.
    """
    return (
        metadata.name if "name" in metadata.provenance else None,
        metadata.version if "version" in metadata.provenance else None,
    )


class WheelDocumentIdentity(TypedDict):
    """The :class:`~pitloom.core.document.DocumentModel` fields that say
    whether a wheel's name was read, and that its files are the wheel's
    members (:func:`wheel_document_identity`)."""

    identity_known: bool
    identity_seed: str | None
    files_origin: FilesOrigin


def wheel_document_identity(
    metadata: ProjectMetadata,
    wheel_path: Path | str,
    project_dir: Path | str | None = None,
) -> WheelDocumentIdentity:
    """``identity_known``, ``identity_seed`` and ``files_origin`` for a
    document of the wheel at *wheel_path*, read as *metadata*: every route
    that builds one passes them on
    (``DocumentModel(..., **wheel_document_identity(...))``), so each keys
    the wheel's members alike. An embed's *project_dir* (its files only add
    header extras) is the origin's, so a member is keyed below the
    project's prefix in the registry, as a built file is.

    A wheel whose name was not read is not looked up in an ID registry, and
    its base file name seeds the document UUID (see
    :func:`~pitloom.core.models.archive_base_name`).
    """
    known = wheel_identity(metadata)[0] is not None
    return {
        "identity_known": known,
        "identity_seed": None if known else archive_base_name(wheel_path),
        "files_origin": FilesOrigin(
            project_dir=None if project_dir is None else Path(project_dir),
            archive=True,
        ),
    }


def payload_files(files: list[ProjectFile], wheel_name: str) -> list[ProjectFile]:
    """*files* minus the wheel's own ``.dist-info``.

    An SBOM describes the project that is packaged, not its package: nothing
    under the own ``.dist-info`` (``RECORD``, ``METADATA``, ``licenses/``,
    ``sboms/``, signatures, ...) is listed, linked or hashed into the package
    Merkle root, as with the Hatchling build hook's SBOM. *wheel_name* is the
    wheel file name; with no single own ``.dist-info``, *files* is returned
    as is. Another ``*.dist-info`` (vendored under a package) is payload.
    """
    prefix = resolve_own_dist_info(
        wheel_name, [f.distribution_path for f in files]
    ).prefix
    if prefix is None:
        return files
    return [f for f in files if not f.distribution_path.startswith(prefix)]


def read_wheel(
    wheel_path: Path | str, *, author_splits: list[AuthorSplit] | None = None
) -> tuple[ProjectMetadata, list[ProjectFile]]:
    """Extract project metadata and file records from a built wheel.

    Args:
        wheel_path: Path to the .whl file.
        author_splits: When given, an ``Author``/``Author-email`` string
            split into several entries is appended to it instead of warned
            about, for a caller that may replace the wheel's authors
            (:func:`~pitloom.extract.authors.warn_author_splits`).

    Returns:
        A tuple of (ProjectMetadata, list of ProjectFile): the wheel's
        payload, see :func:`payload_files`.
        The ProjectMetadata contains core fields extracted from the
        ``METADATA`` of the wheel's own top-level ``.dist-info`` (see
        :func:`pitloom.core.wheel_dist_info.resolve_own_dist_info`); any
        other ``*.dist-info`` directory is an ordinary file.

    Raises:
        ValueError: The wheel is refused as a whole
            (:class:`~pitloom.core.wheel_dist_info.WheelRefused`): not a ZIP
            archive, a member cannot be read (damaged, encrypted,
            unsupported, badly named), two members have one name or one
            holds a NUL.
        OSError: *wheel_path* cannot be opened (missing, permission denied).
    """
    wheel_path_obj = Path(wheel_path)
    metadata = ProjectMetadata(name="unknown")
    project_files: list[ProjectFile] = []
    provenance: dict[str, str] = {}
    archive = wheel_path_obj.name
    source = f"Source: wheel METADATA | File: {archive}"

    with open_wheel_zip(wheel_path_obj) as zf:
        members = wheel_members(zf, archive, log)
        choice = resolve_own_dist_info(archive, [name for name, _ in members])
        if choice.problem:
            log.warning(
                "ARCHIVE=%s: %s%s",
                quote_source(archive),
                choice.problem,
                "" if choice.prefix else " -- identity unknown",
            )
        # Every member is read, the own .dist-info's too, so a damaged one
        # still refuses the wheel; it is not listed afterwards.
        project_files = payload_files(
            [_hash_wheel_entry(zf, info, name, archive) for name, info in members],
            archive,
        )
        msg = (
            read_metadata_headers(zf, members, choice.prefix, archive)
            if choice.prefix
            else None
        )
        licences = (
            _license_members(zf, members, choice.prefix, wheel_path_obj)
            if choice.prefix
            else {}
        )

    if msg is not None:
        _populate_metadata_from_email(metadata, provenance, msg, source, author_splits)
    metadata.provenance = provenance
    apply_in_package_copyright(metadata, licences, archive)
    # Archive order is the writer's; SPDX ids are minted in file order.
    project_files.sort(key=lambda f: f.distribution_path)
    metadata.files = project_files
    return metadata, project_files
