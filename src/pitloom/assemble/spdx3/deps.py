# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents.

See also: :mod:`pitloom.assemble.spdx3.deps_pypi` for the PyPI JSON API
fallback, :mod:`pitloom.assemble.spdx3.deps_license` for license element
and relationship construction, and :mod:`pitloom.assemble.spdx3.
deps_supplier` for supplier/originator resolution -- all three of which
this module composes.
"""

from __future__ import annotations

from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import _add_license_noassertion, _apply_license
from pitloom.assemble.spdx3.deps_pypi import (
    _extract_pypi_license,
    _extract_pypi_supplier,
    _extract_release_hash,
    _fetch_pypi_release_info,
    _prefetch_pypi_release_infos,
)
from pitloom.assemble.spdx3.deps_supplier import (
    _apply_originator,
    _find_license_copyright,
    _parse_project_urls,
    _resolve_metadata_url,
    _resolve_supplier,
)
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.models import build_pypi_purl, build_relationship, generate_spdx_id
from pitloom.core.project import PhantomDependency
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash

# Operators used in PEP 508 dependency specifiers, ordered longest-first to
# avoid splitting on a prefix of a multi-character operator (e.g. "==" before "=").
_VERSION_OPERATORS = ("===", "~=", "!=", "==", ">=", "<=", ">", "<")

# Well-known Project-URL labels that map to homePage / downloadLocation, in
# priority order. Matched case-insensitively against the label part of
# "Label, URL" entries. A tuple, not a set/frozenset: when a package
# declares more than one matching label, iteration order decides which URL
# wins, and a set's order is str-hash-dependent (PYTHONHASHSEED, randomized
# per process by default) -- a plain tuple keeps that choice deterministic
# across builds instead of varying by which process happened to generate
# the SBOM.
_HOMEPAGE_LABELS = ("homepage", "home page", "home")
_DOWNLOAD_LABELS = ("download",)


def _parse_dep_name(dep: str) -> str:
    """Return the bare package name from a PEP 508 dependency specifier.

    Parses *dep* as a :class:`packaging.requirements.Requirement` first, so
    environment markers (``; sys_platform == '...'``) and multi-clause
    specifier sets (``>=1,<2``) are handled correctly -- a naive
    operator-substring split misidentifies the split point when a marker's
    own ``==`` comparison is checked before the specifier's real operator,
    or when a later clause's operator appears before an earlier one's in
    the fixed *_VERSION_OPERATORS* priority order. Falls back to the naive
    split only for specifiers ``Requirement`` itself can't parse.
    """
    try:
        return Requirement(dep).name
    except InvalidRequirement:
        pass
    for op in _VERSION_OPERATORS:
        if op in dep:
            return dep.split(op)[0].strip()
    return dep.strip()


def _resolve_version(dep_name: str, dep: str) -> tuple[str, str | None]:
    """Return ``(version_string, resolved_from)`` for a dependency.

    Tries to read the installed version via ``importlib.metadata`` first.
    Falls back to extracting a pinned version (PEP 440 ``==``/``===``) from
    the specifier set via :class:`packaging.requirements.Requirement` (so a
    marker's own ``==`` comparison, e.g. ``sys_platform == 'linux'``, is
    never mistaken for a version pin). If *dep* isn't valid PEP 508 at all
    (``Requirement`` raises), falls back further to a naive ``"==" in dep``
    substring split -- a best-effort recovery for a malformed-but-pinned
    string, matching what a plain PEP 508 parse failure used to still
    recover before ``Requirement``-based parsing was introduced. Returns
    ``"unknown"`` only when none of these find a pin.

    Returns:
        A tuple of the version string and an optional provenance note.
        The provenance note is ``None`` when the version comes from the
        declared constraint, as the dep-level comment already records that.
    """
    try:
        return get_package_version(dep_name), (
            "Version resolved: Build-time environment (importlib.metadata)"
        )
    except PackageNotFoundError:
        pass

    try:
        pinned = [
            spec.version
            for spec in Requirement(dep).specifier
            if spec.operator in ("==", "===")
        ]
    except InvalidRequirement:
        if "==" in dep:
            return dep.split("==")[1].strip(), None
        return "unknown", None
    if pinned:
        return pinned[0], None

    return "unknown", None


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals
def _enrich_from_installed(
    dep_name: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    offline: bool = False,
    content_type_method: str = "auto",
) -> set[str]:
    """Populate optional fields on a dependency package from installed metadata.

    Returns which of ``{"supplier", "copyright", "license"}`` were actually
    filled in, so :func:`add_dependencies` knows what still needs a PyPI
    JSON API fallback or a ``NOASSERTION`` placeholder.
    """
    try:
        pkg_meta: PackageMetadata = get_pkg_metadata(dep_name)
    except PackageNotFoundError:
        return set()

    filled: set[str] = set()
    project_urls = _parse_project_urls(pkg_meta)

    # description
    summary = pkg_meta["Summary"] or ""
    if summary and summary != "UNKNOWN":
        dep_package.description = summary

    # homePage / downloadLocation -- core field first, then well-known
    # Project-URL labels
    home_page = _resolve_metadata_url(
        pkg_meta["Home-page"] or "", project_urls, _HOMEPAGE_LABELS
    )
    if home_page:
        dep_package.software_homePage = home_page
    download_url = _resolve_metadata_url(
        pkg_meta["Download-URL"] or "", project_urls, _DOWNLOAD_LABELS
    )
    if download_url:
        dep_package.software_downloadLocation = download_url

    repo_url = _resolve_metadata_url(
        "", project_urls, ("repository", "source", "source code")
    )
    if not repo_url:
        repo_url = home_page

    # packageUrl -- PyPI PURL (pkg:pypi/<name>@<version>)
    version = dep_package.software_packageVersion
    if version and version != "unknown":
        dep_package.software_packageUrl = build_pypi_purl(dep_name, version)

    # originatedBy -- Person built from Author/Maintainer metadata, when known
    originators = _resolve_supplier(pkg_meta)
    if _apply_originator(
        originators,
        dep_package,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        repo_url=repo_url,
        provenance_config=provenance_config,
        encoder=encoder,
        provenance_source=f"Source: installed metadata | Package: {dep_name}",
        offline=offline,
        content_type_method=content_type_method,
    ):
        filled.add("originator")

    # copyrightText -- first copyright line found in a declared License-File
    copyright_text = _find_license_copyright(dep_name, pkg_meta)
    if copyright_text:
        dep_package.software_copyrightText = copyright_text
        filled.add("copyright")

    # hasDeclaredLicense / hasConcludedLicense -- prefer PEP 639
    # License-Expression over legacy License. Single-candidate mode returns
    # exactly one of the two relationships (never both) depending on whether
    # `_is_license_concluded` treats "installed metadata" as transparent --
    # it doesn't, so this is always the concluded slot in practice; see
    # _apply_license for why both are checked.
    license_id = pkg_meta["License-Expression"] or pkg_meta["License"] or ""
    if _apply_license(
        license_id,
        f"Source: installed metadata | Package: {dep_name}",
        dep_package,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    ):
        filled.add("license")

    return filled


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _enrich_from_pypi(
    dep_name: str,
    dep_version: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    already_filled: set[str],
    release_info_cache: dict[tuple[str, str | None], dict[str, Any] | None]
    | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    offline: bool = False,
    content_type_method: str = "auto",
) -> set[str]:
    """Best-effort PyPI JSON API fallback for whatever *already_filled*
    doesn't already cover (supplier, license), plus the published
    artifact's integrity hash -- never available from local install state
    alone, since an installed package's unpacked files aren't the original
    distributed wheel/sdist bytes. Silently does nothing if the network is
    unavailable; see :func:`~pitloom.assemble.spdx3.deps_pypi.
    _fetch_pypi_release_info`.

    *release_info_cache*, when given, must already contain an entry for
    this dependency's ``(name, version)`` key -- see
    :func:`~pitloom.assemble.spdx3.deps_pypi._prefetch_pypi_release_infos`,
    which every current caller uses to fetch all of a document's
    dependencies concurrently before this function runs for any of them.
    Falls back to fetching individually when omitted (e.g. a direct
    unit-test call).
    """
    version = dep_version if dep_version != "unknown" else None
    release_info = (
        release_info_cache.get((dep_name, version))
        if release_info_cache is not None
        else _fetch_pypi_release_info(dep_name, version)
    )
    if release_info is None:
        return set()

    filled: set[str] = set()
    info = release_info.get("info") or {}

    project_urls = info.get("project_urls") or {}
    lower_project_urls = {k.lower(): v for k, v in project_urls.items()}
    repo_url = _resolve_metadata_url(
        "", lower_project_urls, ("repository", "source", "source code")
    )
    if not repo_url:
        home_page = info.get("home_page") or _resolve_metadata_url(
            info.get("project_url") or "", lower_project_urls, _HOMEPAGE_LABELS
        )
        repo_url = home_page

    if "originator" not in already_filled:
        originators = _extract_pypi_supplier(info)
        if _apply_originator(
            originators,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            repo_url=repo_url,
            provenance_config=provenance_config,
            encoder=encoder,
            provenance_source=f"Source: PyPI JSON API | Package: {dep_name}",
            offline=offline,
            content_type_method=content_type_method,
        ):
            filled.add("originator")

    if "license" not in already_filled:
        license_id = _extract_pypi_license(info)
        if _apply_license(
            license_id,
            f"Source: PyPI JSON API | Package: {dep_name}",
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        ):
            filled.add("license")

    # verifiedUsing -- the published artifact's real sha256, only when a
    # definite version is known: an unpinned/unresolved dependency has no
    # single "the" artifact to assert an integrity hash against.
    if version is not None:
        digest = _extract_release_hash(release_info)
        if digest:
            dep_package.verifiedUsing = [sha256_hash(digest)]
            filled.add("hash")

    return filled


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _finish_dependency_enrichment(
    dep_name: str,
    dep_version: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    offline: bool,
    release_info_cache: dict[tuple[str, str | None], dict[str, Any] | None]
    | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    content_type_method: str = "auto",
) -> None:
    """Apply the shared dependency-package completeness policy to an
    already-created *dep_package*: PURL (name-only when *dep_version* is
    unresolved), local-install enrichment, then -- unless *offline* -- a
    PyPI JSON API fallback for whatever's still missing, then an explicit
    ``NOASSERTION`` for copyright/license if neither source determined
    them. Shared by :func:`add_dependencies` (``loom project``/``loom
    wheel``/the Hatchling hook) and :func:`~pitloom.assemble.spdx3.
    document.build_deployed` (``loom env``) so every dependency-package
    path gets the same NTIA-completeness treatment instead of each one
    needing this policy re-applied by hand.

    *release_info_cache*: see :func:`_enrich_from_pypi` -- pass the result
    of a prior :func:`~pitloom.assemble.spdx3.deps_pypi.
    _prefetch_pypi_release_infos` call covering this dependency to avoid a
    per-dependency blocking network round-trip.
    """
    dep_package.software_packageUrl = build_pypi_purl(
        dep_name, dep_version if dep_version != "unknown" else None
    )

    filled = _enrich_from_installed(
        dep_name,
        dep_package,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
        offline=offline,
        content_type_method=content_type_method,
    )

    if not offline:
        filled |= _enrich_from_pypi(
            dep_name,
            dep_version,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            already_filled=filled,
            release_info_cache=release_info_cache,
            provenance_config=provenance_config,
            encoder=encoder,
            offline=offline,
            content_type_method=content_type_method,
        )

    if "copyright" not in filled:
        dep_package.software_copyrightText = "NOASSERTION"
    if "license" not in filled:
        _add_license_noassertion(
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_dependencies(
    dependencies: list[str],
    dep_provenance: str,
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    offline: bool = False,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    content_type_method: str = "auto",
) -> None:
    """Build SPDX ``software_Package`` and ``Relationship`` elements for each
    declared dependency.

    Each dependency is enriched from installed metadata first (fast,
    deterministic, no network), then -- unless *offline* -- from the PyPI
    JSON API for whatever installed metadata didn't cover (supplier,
    license, and the published artifact's integrity hash, which is never
    available locally). A package whose license or copyright remains
    unknown after both gets an explicit ``NOASSERTION`` rather than a
    silently absent field.

    The PyPI lookups for every dependency are fetched concurrently before
    any ``software_Package``/``Relationship`` element is built -- element
    construction itself (and the deterministic id-counters it uses) stays
    single-threaded and in declaration order, only the network round-trips
    overlap -- so N dependencies cost roughly one request's wall time
    instead of N sequential ones.
    """
    resolved = []
    for dep in dependencies:
        dep_name = _parse_dep_name(dep)
        dep_version, version_note = _resolve_version(dep_name, dep)
        resolved.append((dep, dep_name, dep_version, version_note))
    release_info_cache = (
        None
        if offline
        else _prefetch_pypi_release_infos(
            (dep_name, dep_version) for _dep, dep_name, dep_version, _note in resolved
        )
    )

    for dep, dep_name, dep_version, version_note in resolved:
        dep_provenance_fields: dict[str, str] = {
            "dependencies": dep_provenance,
            "declared_constraint": dep,
        }
        if version_note:
            dep_provenance_fields["version"] = version_note

        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep_name,
            creationInfo=creation_info,
        )
        dep_package.software_packageVersion = dep_version
        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library

        _finish_dependency_enrichment(
            dep_name,
            dep_version,
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            offline=offline,
            release_info_cache=release_info_cache,
            provenance_config=provenance_config,
            encoder=encoder,
            content_type_method=content_type_method,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance=dep_provenance_fields,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        dep_rel = build_relationship(
            from_id=main_package_spdx_id,
            to_ids=[require_spdx_id(dep_package)],
            rel_type=spdx3.RelationshipType.dependsOn,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            creation_info=creation_info,
        )
        if dep_rel:
            exporter.add_relationship(dep_rel)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def add_phantom_dependencies(
    phantom_deps: list[PhantomDependency],
    main_package_spdx_id: str,
    file_spdx_ids: dict[str, str],
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Build SPDX elements for bundled phantom binary dependencies.

    Unlike :func:`add_dependencies`, there's no PyPI (or any registry)
    lookup here -- a phantom dependency is a bundled shared library (e.g.
    ``.so``/``.dll``/``.dylib``) discovered by binary inspection, not a
    named package release, so there's no ecosystem identifier to query.
    But the same "always assert something concrete" completeness policy
    still applies: license/copyright get an explicit ``NOASSERTION``
    rather than a silently absent field (see :func:`add_dependencies`),
    and the bundled binary's own SHA-256 -- already computed locally with
    no network needed -- becomes its ``verifiedUsing`` integrity hash.
    """
    for dep in phantom_deps:
        dep_package = spdx3.software_Package(
            spdxId=generate_spdx_id("Package", doc_name=doc_name, doc_uuid=doc_uuid),
            name=dep.name,
            creationInfo=creation_info,
        )
        if dep.version:
            dep_package.software_packageVersion = dep.version
        else:
            dep_package.software_packageVersion = "unknown"

        dep_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
        dep_package.software_copyrightText = "NOASSERTION"
        if dep.digest_sha256:
            dep_package.verifiedUsing = [sha256_hash(dep.digest_sha256)]
        _add_license_noassertion(
            dep_package,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        exporter.add_package(dep_package)
        emit_provenance(
            subject=dep_package,
            provenance={
                "package": "Phantom dependency bundled in distribution artifact"
            },
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )

        # The main package depends on this phantom package.
        dep_rel = build_relationship(
            from_id=main_package_spdx_id,
            to_ids=[require_spdx_id(dep_package)],
            rel_type=spdx3.RelationshipType.dependsOn,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            creation_info=creation_info,
        )
        if dep_rel:
            exporter.add_relationship(dep_rel)

        # Link the phantom package to the physical file if it was registered
        file_spdx_id = file_spdx_ids.get(dep.file_path)
        if file_spdx_id:
            file_rel = build_relationship(
                from_id=require_spdx_id(dep_package),
                to_ids=[file_spdx_id],
                rel_type=spdx3.RelationshipType.contains,
                doc_name=doc_name,
                doc_uuid=doc_uuid,
                creation_info=creation_info,
            )
            if file_rel:
                exporter.add_relationship(file_rel)
