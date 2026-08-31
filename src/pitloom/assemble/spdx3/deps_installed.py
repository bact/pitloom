# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Local installed metadata enrichment and PEP 508 parsing for dependencies.

See also: :mod:`pitloom.assemble.spdx3.deps` for the public facade and PyPI enrichment.
"""

from __future__ import annotations

from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version

from packaging.requirements import InvalidRequirement, Requirement
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_license import _apply_license
from pitloom.assemble.spdx3.deps_originator import (
    _apply_originator,
    _find_license_copyright,
    _parse_project_urls,
    _resolve_author_or_maintainer,
    _resolve_metadata_url,
)
from pitloom.assemble.spdx3.provenance import ProvenanceEncoder
from pitloom.core.models import build_pypi_purl
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract._extract_utils import pkg_meta_get

_VERSION_OPERATORS = ("===", "~=", "!=", "==", ">=", "<=", ">", "<")
_HOMEPAGE_LABELS = ("homepage", "home page", "home")
_DOWNLOAD_LABELS = ("download",)


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


def _resolve_version(dep_name: str, dep: str) -> tuple[str, str | None]:
    """Return ``(version_string, resolved_from)`` for a dependency.

    An exact ``==``/``===`` pin already present in *dep* -- e.g. a resolved
    ``poetry.lock`` entry, or any dependency the project itself pins
    exactly -- is authoritative and checked first: it reflects a decision
    already resolved by the dependency's own source and must never be
    silently overridden by whatever happens to be installed in Pitloom's
    own execution environment, which has no relationship to the target
    project's environment. The installed-environment lookup is a fallback
    for the common case where the constraint doesn't pin an exact version
    (e.g. ``requests>=2.0``).
    """
    try:
        pinned = [
            spec.version
            for spec in Requirement(dep).specifier
            if spec.operator in ("==", "===")
        ]
    except InvalidRequirement:
        pinned = []
        unparseable = True
    else:
        unparseable = False
    if pinned:
        return pinned[0], None

    try:
        return get_package_version(dep_name), (
            "Version resolved: Build-time environment (importlib.metadata)"
        )
    except PackageNotFoundError:
        pass

    if unparseable and "==" in dep:
        return dep.split("==")[1].strip(), None
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
    """Populate optional fields on a dependency package from installed metadata."""
    try:
        pkg_meta: PackageMetadata = get_pkg_metadata(dep_name)
    except PackageNotFoundError:
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
