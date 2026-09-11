# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Local installed metadata enrichment and PEP 508 parsing for dependencies.

See also: :mod:`pitloom.assemble.spdx3.deps` for the public facade and PyPI enrichment.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.assemble.spdx3.deps_originator import (
    _apply_originator,
    _find_license_copyright,
    _parse_project_urls,
    _resolve_author_or_maintainer,
    _resolve_metadata_url,
)
from pitloom.assemble.spdx3.provenance import ConflictCandidate, ProvenanceEncoder
from pitloom.core.models import build_pypi_purl
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._extract_utils import pkg_meta_get
from pitloom.extract._lock_common import is_same_version, single_exact_pin

_VERSION_OPERATORS = ("===", "~=", "!=", "==", ">=", "<=", ">", "<")
_HOMEPAGE_LABELS = ("homepage", "home page", "home")
_DOWNLOAD_LABELS = ("download",)

log = logging.getLogger(__name__)


def _parse_dep_name(dep: str) -> str:
    """Return the bare package name from a PEP 508 dependency specifier."""
    try:
        return Requirement(dep).name
    except InvalidRequirement:
        pass
    for op in _VERSION_OPERATORS:
        if op in dep:
            return dep.split(op)[0].strip()
    return dep.strip()


def _extract_pin_from_unparseable(dep: str) -> str | None:
    """Extract an exact pin (== or ===) from an unparseable requirement string."""
    dep_spec = dep.split(";", 1)[0] if ";" in dep else dep
    if not dep_spec or "," in dep_spec:
        return None
    for op in ("===", "=="):
        if op not in dep_spec:
            continue
        prefix, pin_part = dep_spec.split(op, 1)
        if any(other in prefix for other in _VERSION_OPERATORS):
            return None
        pin_part = pin_part.strip()
        if not pin_part or "*" in pin_part:
            return None
        try:
            exact = single_exact_pin(SpecifierSet(f"{op}{pin_part}"))
            return exact[1] if exact is not None else None
        except InvalidSpecifier:
            return None
    return None


def _extract_exact_pin(dep: str) -> tuple[Requirement | None, str | None]:
    """Parse *dep* into a Requirement and extract an exact pin (== or ===),
    if any of its (possibly several) specifier clauses is one.

    Unlike :func:`pitloom.extract._lock_common.single_exact_pin` (which
    requires the *entire* specifier set to be one exact pin -- correct for
    a lock file's own ``version`` field, always a single specifier), a
    general PEP 508 dependency string can legitimately combine an exact
    pin with another clause (e.g. ``foo==1.2.3,!=1.2.3.dev0``) and still be
    fully determined by that pin. Requiring the specifier set to contain
    *only* the pin would wrongly treat such a dependency as unpinned,
    letting a conflicting *locked_version* override a declared exact
    version -- the opposite of "explicit pin beats local environment".
    """
    try:
        req = Requirement(dep)
    except InvalidRequirement:
        return None, _extract_pin_from_unparseable(dep)
    for spec in req.specifier:
        if spec.operator in ("==", "===") and "*" not in spec.version:
            return req, spec.version
    return req, None


def _is_exact_pin_conflict(
    req: Requirement | None, pinned: str, locked_version: str
) -> bool:
    """Return True if locked_version conflicts with declared exact pin."""
    if req is not None and req.specifier:
        try:
            return not req.specifier.contains(locked_version, prereleases=True)
        except InvalidVersion:
            pass
    return not is_same_version(locked_version, pinned)


def _satisfies_constraint(req: Requirement | None, locked_version: str) -> bool | None:
    """Return whether locked_version satisfies req.specifier, or ``None``
    when that can't be determined at all (dep was unparseable, so its
    declared constraint -- if any -- is unknown, not merely absent)."""
    if req is None:
        return None
    if not req.specifier:
        return True
    try:
        return req.specifier.contains(locked_version, prereleases=True)
    except InvalidVersion:
        return False


def build_dependency_version_conflict(
    dep: str,
    locked_version: str,
    *,
    dep_source: str,
    locked_source: str,
) -> list[ConflictCandidate] | None:
    """Return the 2-candidate G2 conflict list for *dep* vs *locked_version*
    (G2, field ``"dependency_version"``), or ``None`` when they agree or the
    disagreement can't be determined.

    Deliberately re-derives the disagreement independently of
    :func:`_resolve_version`'s own winner-selection (re-parsing *dep* via
    :func:`_extract_exact_pin` and re-running
    :func:`_is_exact_pin_conflict`/:func:`_satisfies_constraint`) rather than
    being threaded through it -- widening `_resolve_version`'s
    ``tuple[str, str | None]`` return type would break every one of its
    ~24 existing 2-tuple-unpacking call sites in
    ``tests/assemble/test_deps_resolution_pins.py``,
    ``tests/assemble/test_deps_enrichment_names_versions.py``, and
    ``tests/assemble/test_assembly_edge_cases.py`` (a
    ``ValueError: too many values to unpack``), plus its 2 other production
    call sites in ``_document_locked_deps.py``. The small amount of
    duplicated parsing this costs is worth it for zero blast radius; do not
    "simplify" this later by merging it back into `_resolve_version`.

    Both candidates are ``role="declared"`` (see role-vocabulary.md: neither
    side is Pitloom's own independently-run detection procedure -- both are
    the subject's own stated claim, just from two different files -- this
    deviates from license's declared/detected split). No ``ref`` is set on
    either candidate: a dependency version has exactly one native slot
    (already filled by `_resolve_version`'s own winner-selection, unchanged
    here), not a second element to point at.

    Returns ``None`` (never ``[]``) when: there is no genuine disagreement,
    or when the declared constraint couldn't be parsed at all -- an
    inability to verify is not the same as a confirmed conflict, and must
    not be reported as one.
    """
    req, pinned = _extract_exact_pin(dep)
    if pinned is not None:
        if not _is_exact_pin_conflict(req, pinned, locked_version):
            return None
        return [
            {"value": pinned, "role": "declared", "source": dep_source},
            {"value": locked_version, "role": "declared", "source": locked_source},
        ]

    satisfies = _satisfies_constraint(req, locked_version)
    if satisfies is None or satisfies:
        # None = declared constraint unparseable, can't confirm a genuine
        # disagreement -- distinct from "confirmed no conflict" (satisfies
        # is True). Neither case gets a ConflictCandidate list.
        return None
    if req is None or not req.specifier:
        # Unreachable: _satisfies_constraint only returns False when req is
        # not None and req.specifier is non-empty. Kept for mypy narrowing
        # instead of an `assert` (production code, never test-only).
        return None
    declared_value = str(req.specifier)
    return [
        {"value": declared_value, "role": "declared", "source": dep_source},
        {"value": locked_version, "role": "declared", "source": locked_source},
    ]


def _resolve_version(
    dep_name: str,
    dep: str,
    *,
    locked_version: str | None = None,
    warn: bool = True,
) -> tuple[str, str | None]:
    """Resolve the authoritative version string and provenance note for *dep*.

    Honours the "explicit pin beats local environment" rule: an exact pin
    (``==`` or ``===``) declared directly on the dependency is authoritative;
    it cannot be silently overridden by whatever happens to be installed in
    Pitloom's own execution environment or a conflicting lock file entry.

    Likewise, a *locked_version* provided by a project lock file (PEP 751
    ``pylock.toml``, ``uv.lock``, ``poetry.lock``, etc.) for a direct dependency
    declared as a range or unpinned (e.g. ``requests>=2.0``) is authoritative
    over the host environment. When it does not satisfy the declared constraint
    in *dep*, a warning is emitted.

    The installed-environment lookup is a fallback for the case where neither
    pins an exact version.
    """
    req, pinned = _extract_exact_pin(dep)
    if pinned is not None:
        if (
            warn
            and locked_version is not None
            and _is_exact_pin_conflict(req, pinned, locked_version)
        ):
            log.warning(
                "Locked version %r for dependency %r conflicts with declared"
                " exact pin %r -- using declared pin",
                locked_version,
                dep_name,
                pinned,
            )
        return pinned, None

    if locked_version is not None:
        if warn:
            satisfies = _satisfies_constraint(req, locked_version)
            if satisfies is None:
                log.warning(
                    "Dependency %r declared as %r couldn't be parsed -- its"
                    " constraint (if any) can't be verified against locked"
                    " version %r, using it anyway",
                    dep_name,
                    dep,
                    locked_version,
                )
            elif not satisfies:
                log.warning(
                    "Locked version %r for dependency %r does not satisfy declared"
                    " constraint %r -- using locked version",
                    locked_version,
                    dep_name,
                    dep,
                )
        return locked_version, "Version resolved: Project lock file"

    try:
        return get_package_version(dep_name), (
            "Version resolved: Build-time environment (importlib.metadata)"
        )
    except PackageNotFoundError:
        pass

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
    expected_version: str | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    offline: bool = False,
    content_type_method: str = "auto",
) -> set[str]:
    """Populate optional fields on a dependency package from installed metadata."""
    try:
        pkg_meta: PackageMetadata = get_pkg_metadata(dep_name)
    except PackageNotFoundError:
        return set()

    installed_version = pkg_meta_get(pkg_meta, "Version")
    target_version = expected_version or dep_package.software_packageVersion
    if (
        installed_version
        and target_version
        and target_version != "unknown"
        and not is_same_version(installed_version, target_version)
    ):
        return set()

    filled: set[str] = set()
    project_urls = _parse_project_urls(pkg_meta)

    summary = pkg_meta_get(pkg_meta, "Summary")
    if summary and summary != "UNKNOWN":
        dep_package.description = summary

    home_page = _resolve_metadata_url(
        pkg_meta_get(pkg_meta, "Home-page"), project_urls, _HOMEPAGE_LABELS
    )
    if home_page:
        dep_package.software_homePage = home_page
    download_url = _resolve_metadata_url(
        pkg_meta_get(pkg_meta, "Download-URL"), project_urls, _DOWNLOAD_LABELS
    )
    if download_url:
        dep_package.software_downloadLocation = download_url

    repo_url = _resolve_metadata_url(
        "", project_urls, ("repository", "source", "source code")
    )
    if not repo_url:
        repo_url = home_page

    version = dep_package.software_packageVersion
    if version and version != "unknown":
        dep_package.software_packageUrl = build_pypi_purl(dep_name, version)

    originators = _resolve_author_or_maintainer(pkg_meta)
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

    copyright_text = _find_license_copyright(dep_name, pkg_meta)
    if copyright_text:
        dep_package.software_copyrightText = copyright_text
        filled.add("copyright")

    license_id = pkg_meta_get(pkg_meta, "License-Expression") or pkg_meta_get(
        pkg_meta, "License"
    )
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
