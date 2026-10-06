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
from typing import Any, ClassVar, TypedDict

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
class ProjectFile:
    """A file included in the project distribution.

    Attributes:
        physical_path: Project-root-relative path to the physical file on
            disk (see CLAUDE.md's ``physical_path``/``distribution_path``
            contract) -- except for a file sourced via the generic
            ``--allow-build`` build-and-read mechanism
            (``pitloom.core._models_wheel_build_and_read``), where it is
            instead an absolute path into a temporary extraction
            directory: that mechanism's real files never live under the
            project's own root, so no project-relative path exists for
            them (``_build_project_file_entry()``'s
            ``source.relative_to(project_dir)`` falls back to
            ``source.as_posix()`` when it raises ``ValueError``). Not
            project-relative in that one case -- do not assume this field
            is always a relative path without checking; any consumer
            that joins it onto ``project_dir`` (e.g.
            ``pitloom.enrich._resolve_model_search_dir``) must check
            ``Path(physical_path).is_absolute()`` first and fall back to
            ``distribution_path``/``file_path_relative``, since
            ``pathlib``'s own join semantics silently discard the
            left-hand side when the right-hand operand is absolute. For a
            member read from a wheel or sdist archive it is the raw
            archive name (never a filesystem path), kept as a registry
            lookup key; ``distribution_path`` is its normalised name.
        distribution_path: Canonical path of the file inside the wheel/package.
        digest_sha256: Hex-encoded SHA-256 digest of the file contents.
            ``None`` when discovered via
            ``pitloom.core._models_wheel.get_wheel_files(skip_merkle_root=True)``,
            which skips per-file hashing entirely.
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
    """

    physical_path: str
    distribution_path: str
    digest_sha256: str | None = None
    copyright_text: str | None = None
    copyright_source: str | None = None
    file_contributors: list[str] = field(default_factory=list)
    file_type: str | None = None
    spdx_license_identifier: str | None = None
    content_type: str | None = None
    content_type_method: str | None = None


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

    Relocated here (rather than defined in
    :mod:`pitloom.assemble.spdx3.provenance`, which re-exports it) so both
    :mod:`pitloom.extract` and :mod:`pitloom.assemble` can use it without
    :mod:`pitloom.extract` importing from the :mod:`pitloom.assemble`
    layer -- see :attr:`ProjectMetadata.field_conflicts`.
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
        version: Inferred version of the binary, if any.
    """

    name: str
    file_path: str
    digest_sha256: str | None = None
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
    keywords: list[str] = field(default_factory=list)
    authors: list[dict[str, str]] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    locked_dependencies: list[str] = field(default_factory=list)
    locked_dependency_hashes: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    files: list[ProjectFile] = field(default_factory=list)
    field_conflicts: dict[str, list[ConflictCandidate]] = field(default_factory=dict)

    #: Every dict/list-valued field name on this dataclass -- the set
    #: :meth:`replace_with_fresh_containers` gives a fresh shallow copy to,
    #: since :func:`dataclasses.replace` shares each of them with *self* by
    #: reference otherwise. Kept in sync by hand (not derived from
    #: :func:`dataclasses.fields` at class-definition time, to avoid a
    #: metaclass/decorator-ordering dependency for a fixed, rarely-changed
    #: list) -- a newly added dict/list field must be added here too, or it
    #: silently loses the same protection every other container field has.
    _CONTAINER_FIELD_NAMES: ClassVar[tuple[str, ...]] = (
        "keywords",
        "authors",
        "urls",
        "dependencies",
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

        :func:`dataclasses.replace` shares every un-overridden field's
        object with *self* by reference -- for a container field, that
        means the result and *self* start out as the exact same dict/list
        object. A caller that goes on to mutate the result in place (add
        a key to ``.provenance``, append to ``.field_conflicts``, ...)
        would silently corrupt *self* too unless every such caller
        remembers to defensively copy first -- a hazard this repo has
        already hit twice independently (:func:`merge_project_metadata`
        and ``reconcile_installed_metadata()`` in
        ``pitloom.extract.project._installed_reconcile`` each patched it
        separately for ``provenance``/``field_conflicts`` before this
        method existed). Prefer this over a bare
        ``dataclasses.replace()`` call whenever the result will be
        mutated in place afterward, for any container field -- not just
        the two fields that happened to trigger a bug report first.
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

    Iterates :func:`dataclasses.fields` instead of hand-listing every field,
    so a newly added :class:`ProjectMetadata` field (like ``license_concluded``)
    is merged automatically with the same default rule -- no call site needs
    updating when the schema grows.

    Two fields are special-cased rather than "primary when present else
    secondary":

    - ``name`` -- always *primary*'s, even if empty (a project's own name is
      never meaningfully "filled in" from a secondary/fallback source).
    - ``provenance`` -- dict-merged, *primary*'s entries winning on key
      conflict, rather than replaced wholesale.

    Every other field: *primary*'s value when present, else *secondary*'s.
    This rule is uniform across scalar and container fields, with no
    field-type-specific case: a falsy value -- an empty container
    (``dependencies``, ``keywords``, ``urls``, etc.) or a scalar's
    ``None`` (e.g. ``requires_python`` left unset by an explicit
    ``python = "*"``) -- with provenance confirming it was explicitly
    declared in *primary* is authoritative and preserved, exactly like a
    truthy value would be. A falsy value absent from *primary*'s
    provenance is treated as not-yet-resolved and filled from
    *secondary*. A non-empty *primary* list replaces
    *secondary*'s wholesale, it is never unioned with it. If a future
    ``locked_dependencies`` source needs union-not-replace semantics (e.g.
    combining two lock-derived dependency sets), that is a deliberate
    deviation from every sibling list field here and belongs in a dedicated
    merge step at the call site, not a silent special case in this
    otherwise-uniform field-by-field loop.

    The "explicitly declared" check looks up *provenance* by the field's own
    name (e.g. ``provenance["keywords"]``) -- except ``license_name``, whose
    extractors record its provenance under the literal key ``"license"``
    (see ``project.pyproject``/``project._setuptools_options``), not
    ``"license_name"``; :data:`_PROVENANCE_KEY_ALIASES`
    maps that known mismatch so the same presence check finds it.

    ``field_conflicts`` is dict-merged the same way as ``provenance``
    (*primary*'s entries winning on key conflict) rather than left to the
    generic per-field loop below: both are seeded via
    :meth:`ProjectMetadata.replace_with_fresh_containers` (never a bare
    ``dataclasses.replace()``, which would alias every un-overridden
    container field to *primary*'s own object) and then explicitly
    overridden with the merged dict computed here. At most one side has
    conflicts at every current call site (``setup.py`` vs ``setup.cfg`` ones
    from ``read_setuptools()``; this merge runs before the installed
    reconciliation), but a future caller or ordering change must not
    silently corrupt either input's own dict via this function's output.
    """
    merged = primary.replace_with_fresh_containers()
    merged.provenance = {**secondary.provenance, **primary.provenance}
    colliding_fields = set(secondary.field_conflicts) & set(primary.field_conflicts)
    if colliding_fields:
        # Not reachable at any current call site (see the docstring above),
        # but if it ever is: primary wins outright below, same as every
        # other field -- log it rather than silently drop secondary's
        # whole ConflictCandidate list with no signal at all, per this
        # repo's "no silent deviations" principle.
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
