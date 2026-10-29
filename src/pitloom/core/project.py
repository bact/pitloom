# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Generic project metadata representation with provenance tracking."""

from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, NamedTuple, TypedDict

from pitloom.core.file_hash import FileDigests, HexDigests
from pitloom.core.lfs_pointer import LfsPointer

log = logging.getLogger(__name__)

# The archive extensions an sdist is distributed as.
SDIST_EXTENSIONS = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".zip")


def is_sdist_archive(path: Path) -> bool:
    """Whether *path* is an existing sdist archive file.

    One authority for every caller that branches on "sdist archive vs
    project directory" (the project reader, the build-flag settle). A
    directory named like an archive is not one, hence the file check
    before the extension match. ``os.path.isfile``, not
    ``Path.is_file()``: never raises (e.g. EACCES).
    """
    if not os.path.isfile(path):
        return False
    return os.path.basename(os.fspath(path)).lower().endswith(SDIST_EXTENSIONS)


@dataclass
# pylint: disable-next=too-many-instance-attributes
class ProjectFile:
    """A file included in the project distribution.

    Attributes:
        physical_path: Project-root-relative path to the physical file on
            disk (see CLAUDE.md's ``physical_path``/``distribution_path``
            contract). A file sourced by the ``--allow-build`` build-and-read
            mechanism (``pitloom.core._models_wheel_build_and_read``) has an
            absolute path into a temporary extraction directory instead
            (``built`` is then true). A consumer that joins it onto
            ``project_dir`` or bakes it into a determinism-sensitive string
            goes through :func:`project_relative_or_fallback`, since
            ``pathlib`` discards the left operand of a join with an absolute
            right operand. For a wheel member it is the raw archive name
            (never a filesystem path); for an sdist member, its name without
            the sdist's top directory (a member outside it: the raw name).
            ``distribution_path`` is the normalised member name. The registry
            key comes from one or the other per
            :func:`~pitloom.id_registry.keys.file_lookup_key`.
        distribution_path: Canonical path of the file inside the wheel/package.
        digest_sha256: Hex-encoded SHA-256 digest of the file contents.
            ``None`` when discovered via
            ``pitloom.core._models_wheel.get_wheel_files(skip_merkle_root=True)``,
            which skips per-file hashing entirely. For a Git LFS pointer
            in a checkout, the pointer's ``oid``: the content's SHA-256
            as the pointer states it (see :func:`digest_fields`).
        digest_sha512: Hex-encoded SHA-512 digest of the same read;
            ``None`` when ``digest_sha256`` is, and for a pointer whose
            ``oid`` stands in (no SHA-512 of the content was read).
        copyright_text: The file's own declared copyright text, from an
            ``SPDX-FileCopyrightText:`` tag or a bare ``Copyright (c) ...``
            fallback line in its header. ``None`` when neither is present
            or file-header scanning is off (see
            ``pitloom.extract._file_headers.parse_file_header``).
        copyright_source: ``"spdx_tag"`` or ``"bare_copyright_line"`` --
            which form produced ``copyright_text``.
        file_contributors: Every ``SPDX-FileContributor:`` value from the
            file's header, in order. Empty when none are present.
        file_type: The raw ``SPDX-FileType:`` tag value, untranslated.
        spdx_license_identifier: The file's own ``SPDX-License-Identifier:``
            expression, independent of the project's overall license.
        content_type: A real IANA media type detected from the file's
            content/filename (``magika`` or a filename-extension
            fallback), or asserted directly by a
            ``[[tool.pitloom.content-type.override]]`` config match,
            independent of ``file_type`` -- see
            ``pitloom.extract._file_headers.guess_content_type``/
            ``resolve_content_type_override``. ``None`` when
            content-type detection is off or inconclusive.
        content_type_method: ``"magika"``, ``"extension_guess"``, or
            ``"config_override"`` -- which tool (or config match)
            resolved ``content_type``.
        built: Extracted from a just-built wheel (``--allow-build``), so
            ``physical_path`` is an absolute temp path and there is no
            project path.
        lfs_pointer: What the file states when its bytes are a Git LFS
            pointer (an LFS-tracked file in a checkout made with LFS off),
            on every route, whichever digests were recorded; ``None`` for
            any other file or one not hashed. Its header and content are
            not read: the header and content-type fields stay empty, but
            for a ``config_override`` content type.
    """

    physical_path: str
    distribution_path: str
    digest_sha256: str | None = None
    digest_sha512: str | None = None
    copyright_text: str | None = None
    copyright_source: str | None = None
    file_contributors: list[str] = field(default_factory=list)
    file_type: str | None = None
    spdx_license_identifier: str | None = None
    content_type: str | None = None
    content_type_method: str | None = None
    built: bool = False
    lfs_pointer: LfsPointer | None = None

    def hex_digests(self) -> HexDigests | None:
        """This file's digests as its ``verifiedUsing`` states them;
        ``None`` when it was not hashed."""
        if self.digest_sha256 is None:
            return None
        return HexDigests(self.digest_sha256, self.digest_sha512)

    def registry_sha256(self) -> str | None:
        """The SHA-256 an ID registry entry for this file records, and every
        lookup of it gates on: for a Git LFS pointer its ``oid`` on every
        route, whatever ``digest_sha256`` the SBOM states (an archive or the
        hook states the pointer text's), so the routes share one entry;
        else ``digest_sha256`` (``None``: not hashed)."""
        if self.lfs_pointer is not None:
            return self.lfs_pointer.oid
        return self.digest_sha256


class DigestFields(TypedDict):
    """The digest fields of a :class:`ProjectFile`, from one read
    (:func:`digest_fields`); a :class:`PhantomDependency` takes the two
    digests from its file one by one."""

    digest_sha256: str
    digest_sha512: str | None
    lfs_pointer: LfsPointer | None


def digest_fields(digests: FileDigests, *, bytes_as_is: bool = False) -> DigestFields:
    """*digests* as the keyword arguments of a :class:`ProjectFile`: every
    constructor that hashed the file's bytes sets them through here.

    A Git LFS pointer records its ``oid`` as the SHA-256 and no SHA-512
    (the content was not read), unless *bytes_as_is*: an archive, or a
    build that packages the tree, ships the pointer text itself, so its
    own digests stay (they match the wheel's ``RECORD``). Either way
    ``lfs_pointer`` says what the pointer states.
    """
    recorded = digests.hex() if bytes_as_is else digests.stated()
    return DigestFields(
        digest_sha256=recorded.sha256,
        digest_sha512=recorded.sha512,
        lfs_pointer=digests.lfs_pointer,
    )


class FilesOrigin(NamedTuple):
    """How a document's file list was produced: scanned under
    *project_dir*, or read from an *archive* (a wheel; with *sdist*, an
    sdist); the defaults name neither (see
    :func:`~pitloom.id_registry.keys.file_lookup_key`)."""

    project_dir: Path | None = None
    archive: bool = False
    sdist: bool = False


def project_relative_or_fallback(physical_path: str, fallback: str) -> str:
    """*physical_path* if it's project-relative, else *fallback*.

    Every consumer that needs a stable, project-relative stand-in for
    ``ProjectFile.physical_path`` (a registry-lookup key, a
    determinism-sensitive provenance string, a directory to join onto
    ``project_dir``) hits the same hazard documented on
    :attr:`ProjectFile.physical_path`: for a build-and-read
    (``--allow-build``) discovered file, ``physical_path`` is an
    absolute path into a fresh ``tempfile.mkdtemp()`` directory that
    differs every run and never matches a project-relative value.
    *fallback* is normally ``distribution_path``/``file_path_relative``.
    """
    if Path(physical_path).is_absolute():
        return fallback
    return physical_path


class _ConflictCandidateRequired(TypedDict):
    value: str
    role: str
    source: str


class ConflictCandidate(_ConflictCandidateRequired, total=False):
    """One source's reported value for a field under dispute.

    Defined here so :mod:`pitloom.extract` and :mod:`pitloom.assemble` both
    use it; :mod:`pitloom.assemble.spdx3.provenance` re-exports it. See
    :attr:`ProjectMetadata.field_conflicts`.
    """

    ref: str


@dataclass
class PhantomDependency:
    """A bundled binary dependency not tracked by normal package metadata.

    Examples include bundled shared libraries (.so, .dll, .dylib) inside wheels
    and pre-compiled extension modules (.pyd) that link to external C/C++ libraries.

    Attributes:
        name: Name of the binary dependency (e.g., 'libz', 'openssl').
        file_path: Canonical path to the binary inside the distribution/wheel.
        digest_sha256: Hex-encoded SHA-256 digest of the binary file contents.
        digest_sha512: Hex-encoded SHA-512 digest of the same contents.
        version: Inferred version of the binary, if any.
    """

    name: str
    file_path: str
    digest_sha256: str | None = None
    digest_sha512: str | None = None
    version: str | None = None


@dataclass
# pylint: disable-next=too-many-instance-attributes
class ProjectMetadata:
    """Format-neutral representation of project metadata with provenance tracking.

    This dataclass is the common currency between the extract and assemble
    layers.  It carries no knowledge of how the data was obtained; any
    extractor (``pyproject.toml``, ``setup.cfg``, build logs, ...) can
    populate it.

    Provenance is recorded per-field in :attr:`provenance` using the pattern
    ``"Source: <location> | Field: <key>"`` or
    ``"Source: <location> | Method: <method>"``.

    :attr:`field_conflicts` records a genuine disagreement between this
    metadata's own value for a field and a second, independently-sourced
    candidate (e.g. an in-tree ``.egg-info``/``.dist-info`` -- see
    :mod:`pitloom.extract.project.installed`) that was rejected in favor of
    this instance's value. Empty for metadata that was never reconciled
    against a second source.

    Pitloom tool settings such as ``fragments`` and ``pretty`` are **not** stored
    here; they live in :class:`~pitloom.core.config.PitloomConfig` which is returned
    alongside this object by
    :func:`~pitloom.extract.project.pyproject.read_pyproject`.
    """

    name: str
    version: str | None = None
    description: str | None = None
    readme: str | None = None
    requires_python: str | None = None
    license_name: str | None = None
    license_concluded: str | None = None
    #: The copyright notices found in the project's own licence files
    #: (:mod:`pitloom.extract.copyright_notices`), ``None`` when none was.
    copyright_text: str | None = None
    keywords: list[str] = field(default_factory=list)
    authors: list[dict[str, str]] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    #: The files, relative to the project directory as the project lists
    #: them, the dependencies were read from (a requirements file
    #: ``[tool.setuptools.dynamic]`` or ``setup.cfg``'s ``file:`` names):
    #: declared dependencies, never a lock
    #: (:func:`~pitloom.extract.lock.cascade.apply_locked_dependencies`).
    dependency_files: list[str] = field(default_factory=list)
    locked_dependencies: list[str] = field(default_factory=list)
    locked_dependency_hashes: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    files: list[ProjectFile] = field(default_factory=list)
    field_conflicts: dict[str, list[ConflictCandidate]] = field(default_factory=dict)

    #: Every dict/list-valued field name on this dataclass: the fields
    #: :meth:`replace_with_fresh_containers` copies. Listed by hand; a new
    #: dict/list field must be added here.
    _CONTAINER_FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "keywords",
        "authors",
        "urls",
        "dependencies",
        "dependency_files",
        "locked_dependencies",
        "locked_dependency_hashes",
        "provenance",
        "files",
        "field_conflicts",
    )

    def replace_with_fresh_containers(self, **changes: Any) -> ProjectMetadata:
        """``dataclasses.replace(self, **changes)``, but every dict/list-
        valued field not explicitly given in *changes* gets a fresh
        shallow copy first.

        :func:`dataclasses.replace` shares every field not in *changes* with
        *self* by reference, so a caller that then mutates a container of the
        result in place (a key of ``.provenance``, an item of
        ``.field_conflicts``) would change *self* too. Use this method rather
        than a bare ``dataclasses.replace()`` whenever the result is mutated
        in place.
        """
        fresh_containers = {
            name: getattr(self, name).copy()
            for name in self._CONTAINER_FIELD_NAMES
            if name not in changes
        }
        return dataclasses.replace(self, **fresh_containers, **changes)


#: Maps a :class:`ProjectMetadata` field name to the literal provenance key
#: its extractors actually record it under, for the cases where they differ:
#:
#: - ``license_name``: every producer (``project.pyproject``,
#:   ``project._setuptools_options``) writes ``provenance["license"]``.
#: - ``locked_dependency_hashes``: companion to ``locked_dependencies``,
#:   sharing its ``provenance["locked_dependencies"]`` record so hashes stay
#:   bound to the winning lock-derived dependency set and never drift.
#:
#: Consulted by :func:`merge_project_metadata`'s "explicitly declared" check
#: so it looks up the key extractors actually use instead of a field name
#: that's never present in *provenance*.
_PROVENANCE_KEY_ALIASES: dict[str, str] = {
    "license_name": "license",
    "locked_dependency_hashes": "locked_dependencies",
}


def provenance_key_for(field_name: str) -> str:
    """The literal ``provenance`` dict key *field_name* is actually
    recorded under -- see :data:`_PROVENANCE_KEY_ALIASES` above. Public
    wrapper so a cross-module consumer (e.g.
    :mod:`pitloom.extract.project._installed_reconcile`, which needs the
    identical "explicitly declared" lookup this module's own
    :func:`merge_project_metadata` uses) doesn't have to reach into a
    leading-underscore module-private name to get it.
    """
    return _PROVENANCE_KEY_ALIASES.get(field_name, field_name)


def merge_project_metadata(
    primary: ProjectMetadata, secondary: ProjectMetadata
) -> ProjectMetadata:
    """Merge two :class:`ProjectMetadata` instances, *primary* winning
    field-by-field; *secondary* fills gaps where *primary*'s value is absent.

    Iterates :func:`dataclasses.fields`, so a new :class:`ProjectMetadata`
    field is merged with the same rule without a change here.

    Two fields are special-cased:

    - ``name`` -- always *primary*'s, even if empty.
    - ``provenance`` -- dict-merged, *primary*'s entries winning on key
      conflict, rather than replaced wholesale.

    Every other field takes *primary*'s value when present, else
    *secondary*'s, for scalar and container fields alike. A falsy *primary*
    value (an empty container, or a scalar ``None`` such as
    ``requires_python`` left unset by an explicit ``python = "*"``) whose
    provenance confirms it was declared is authoritative and kept. A falsy
    value absent from *primary*'s provenance is unresolved and filled from
    *secondary*. A non-empty *primary* list replaces *secondary*'s, never
    unions with it.

    The "explicitly declared" check looks up *provenance* by the field's own
    name (e.g. ``provenance["keywords"]``) -- except ``license_name``, whose
    extractors record its provenance under the literal key ``"license"``
    (see ``project.pyproject``/``project._setuptools_options``), not
    ``"license_name"``; :data:`_PROVENANCE_KEY_ALIASES`
    maps that known mismatch so the same presence check finds it.

    ``field_conflicts`` is dict-merged like ``provenance``, *primary*'s
    entries winning on key conflict, with one ``WARNING:`` naming a field
    both sides hold; the merged result holds fresh containers, so neither
    input is modified.
    """
    merged = primary.replace_with_fresh_containers()
    merged.provenance = {**secondary.provenance, **primary.provenance}
    colliding_fields = set(secondary.field_conflicts) & set(primary.field_conflicts)
    if colliding_fields:
        # Primary wins below, as for every other field; secondary's
        # ConflictCandidate list is dropped with this WARNING:, not silently.
        log.warning(
            "merge_project_metadata: both sides have a field_conflicts "
            "entry for %s -- keeping only primary's, secondary's conflict "
            "record is discarded",
            sorted(colliding_fields),
        )
    merged.field_conflicts = {**secondary.field_conflicts, **primary.field_conflicts}
    for f in dataclasses.fields(ProjectMetadata):
        if f.name in ("name", "provenance", "field_conflicts"):
            continue
        primary_value = getattr(primary, f.name)
        provenance_key = provenance_key_for(f.name)
        if not primary_value and provenance_key not in primary.provenance:
            setattr(merged, f.name, getattr(secondary, f.name))
    return merged
