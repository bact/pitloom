# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Dependency package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from email.utils import getaddresses
from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import distribution as get_pkg_distribution
from importlib.metadata import metadata as get_pkg_metadata
from importlib.metadata import version as get_package_version
from typing import Any
from urllib.parse import quote as url_quote

from packaging.requirements import InvalidRequirement, Requirement
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import (
    TRANSPARENT_SOURCES,
    ConflictCandidate,
    ProvenanceEncoder,
    build_conflict_annotation,
    emit_provenance,
    parse_provenance_value,
)
from pitloom.core.models import build_pypi_purl, generate_spdx_id
from pitloom.core.project import PhantomDependency
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id, sha256_hash
from pitloom.extract._extract_utils import fetch_json
from pitloom.extract._license import (
    normalize_license_expression,
    tag_license_normalization,
)
from pitloom.extract._file_headers import guess_content_type
import urllib.request
from urllib.error import URLError
from urllib.parse import urlparse

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

# A permissive (MIT/BSD-style) LICENSE file's copyright line, e.g.
# "Copyright (c) 2021 Taneli Hukkinen" or "Copyright © 2019 Filipe Laíns".
_COPYRIGHT_LINE_RE = re.compile(
    r"^\s*Copyright\s+(?:\(c\)|©)?\s*\S.*$", re.IGNORECASE | re.MULTILINE
)
# Only the file's head is searched -- see _find_license_copyright.
_COPYRIGHT_SEARCH_HEAD_CHARS = 500

# Best-effort PyPI JSON API fetch timeout -- short enough that a blocked or
# slow network doesn't meaningfully stall a build; see _fetch_pypi_release_info.
_PYPI_TIMEOUT_SECONDS = 5.0

# A `license` field this long is almost certainly a project pasting its
# entire LICENSE file into PyPI's free-text `license` metadata (a known,
# common anti-pattern) rather than a short identifier/expression -- treated
# as absent rather than polluting the license/copyright fields with it.
_PYPI_LICENSE_FIELD_MAX_LEN = 200


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


def _extract_suppliers(name: str, email_raw: str) -> list[tuple[str | None, str | None]]:
    """Return a list of ``(name, email)`` tuples from metadata fields.

    *email_raw* may carry an RFC 5322 ``"Name <email>"`` form (how PEP 621
    ``[project.authors]`` round-trips through core metadata / PyPI's JSON
    API), a bare address, or -- commonly for a maintainer field -- a
    comma-separated list of several such entries; :func:`email.utils.
    getaddresses` handles all three (unlike :func:`email.utils.parseaddr`,
    which mis-parses a multi-entry list as one malformed address and
    silently returns nothing).

    If *email_raw* is empty but *name* contains a comma-separated list of
    names, it splits them into individual tuples.
    """
    name = name.strip()
    email_raw = email_raw.strip()
    results: list[tuple[str | None, str | None]] = []

    if email_raw:
        addresses = getaddresses([email_raw])
        for parsed_name, parsed_email in addresses:
            resolved_name = parsed_name.strip() or name or None
            resolved_email = parsed_email.strip() or None
            if resolved_name or resolved_email:
                results.append((resolved_name, resolved_email))
        return results

    if name:
        for part in re.split(r",|\band\b", name):
            part = part.strip()
            if part:
                results.append((part, None))
    return results


def _resolve_supplier(pkg_meta: PackageMetadata) -> list[tuple[str | None, str | None]]:
    """Return a list of ``(name, email)`` tuples for a dependency's supplier from
    installed metadata, or an empty list. Tries ``Author``/``Author-email`` first,
    then falls back to ``Maintainer``/``Maintainer-email``."""
    for name_field, email_field in (
        ("Author", "Author-email"),
        ("Maintainer", "Maintainer-email"),
    ):
        results = _extract_suppliers(pkg_meta[name_field] or "", pkg_meta[email_field] or "")
        if results:
            return results
    return []


def _extract_pypi_supplier(info: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    """Return a list of ``(name, email)`` tuples for a dependency's supplier from a
    PyPI JSON API ``info`` object, or an empty list. Same author-then-maintainer
    precedence as :func:`_resolve_supplier`."""
    for name_key, email_key in (
        ("author", "author_email"),
        ("maintainer", "maintainer_email"),
    ):
        results = _extract_suppliers(info.get(name_key) or "", info.get(email_key) or "")
        if results:
            return results
    return []


def _extract_pypi_license(info: dict[str, Any]) -> str | None:
    """Return a license expression/identifier from a PyPI JSON API ``info``
    object, or ``None``. Prefers PEP 639 ``license_expression``, then the
    legacy free-text ``license`` field (skipped if implausibly long -- see
    :data:`_PYPI_LICENSE_FIELD_MAX_LEN`), then an OSI/other ``License ::``
    trove classifier.
    """
    license_expression = (info.get("license_expression") or "").strip()
    if license_expression and license_expression.upper() != "UNKNOWN":
        return license_expression

    license_field = (info.get("license") or "").strip()
    if (
        license_field
        and license_field.upper() != "UNKNOWN"
        and len(license_field) <= _PYPI_LICENSE_FIELD_MAX_LEN
    ):
        return license_field

    classifiers: list[str] = info.get("classifiers") or []
    for classifier in classifiers:
        if classifier.startswith("License ::"):
            return classifier.rsplit("::", maxsplit=1)[-1].strip()
    return None


def _fetch_pypi_release_info(name: str, version: str | None) -> dict[str, Any] | None:
    """Best-effort fetch of PyPI JSON API release info for *name*, optionally
    pinned to *version* (the unversioned endpoint returns the latest
    release). Returns ``None`` on any failure -- no network, DNS blocked,
    timeout, non-200, or a malformed response -- so this is always a
    silent, non-blocking enrichment layer, never a hard requirement.

    Delegates the actual fetch to :func:`~pitloom.extract._extract_utils.
    fetch_json` (also used for Croissant metadata) rather than a second
    urlopen/json.loads implementation, so the scheme-restriction and
    HTTP-exception handling only need to be reviewed and gotten right once.
    """
    path = (
        f"{url_quote(name)}/{url_quote(version)}/json"
        if version
        else f"{url_quote(name)}/json"
    )
    url = f"https://pypi.org/pypi/{path}"
    try:
        return fetch_json(url, timeout=_PYPI_TIMEOUT_SECONDS)
    except ValueError:
        return None


def _extract_release_hash(release_info: dict[str, Any]) -> str | None:
    """Return the hex SHA-256 digest of the release's wheel (preferred) or
    sdist artifact from a PyPI JSON API response, or ``None``."""
    urls = release_info.get("urls") or []
    by_type = {u.get("packagetype"): u for u in urls if isinstance(u, dict)}
    entry = by_type.get("bdist_wheel") or by_type.get("sdist")
    if entry is None and urls:
        entry = urls[0]
    if entry is None:
        return None
    digest = (entry.get("digests") or {}).get("sha256")
    return digest or None


# Cap on concurrent PyPI JSON API requests, so a project with hundreds of
# dependencies doesn't open hundreds of sockets at once.
_PYPI_MAX_CONCURRENT_FETCHES = 8


def _prefetch_pypi_release_infos(
    name_versions: Iterable[tuple[str, str]],
) -> dict[tuple[str, str | None], dict[str, Any] | None]:
    """Concurrently fetch PyPI JSON API release info for each distinct
    ``(name, version)`` pair, so N dependencies cost roughly one network
    round-trip's worth of wall time instead of N sequential ones (each
    with its own TCP+TLS handshake and up to a
    :data:`_PYPI_TIMEOUT_SECONDS` timeout on failure).

    ``version == "unknown"`` is normalized to ``None`` here, matching
    :func:`_fetch_pypi_release_info`'s own "no pin -> latest release"
    semantics -- so two dependencies that both have an unresolved version
    share a single fetch instead of one per occurrence.
    """
    keys = {
        (name, version if version != "unknown" else None)
        for name, version in name_versions
    }
    if not keys:
        return {}
    results: dict[tuple[str, str | None], dict[str, Any] | None] = {}
    with ThreadPoolExecutor(
        max_workers=min(_PYPI_MAX_CONCURRENT_FETCHES, len(keys))
    ) as pool:
        futures = {
            pool.submit(_fetch_pypi_release_info, name, version): (name, version)
            for name, version in keys
        }
        for future, key in futures.items():
            results[key] = future.result()
    return results
def _resolve_remote_authors_file(
    repo_url: str,
    filename: str,
    offline: bool,
    content_type_method: str,
) -> tuple[str, str]:
    """Resolve the URL locator and content type for a remote authors file."""
    base_url = repo_url[:-4] if repo_url.endswith(".git") else repo_url
    base_url = base_url.rstrip("/")
    parsed = urlparse(base_url)
    host = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]
    
    branch = "HEAD"
    if not offline and len(path_parts) >= 2:
        owner, repo = path_parts[0], path_parts[1]
        try:
            if host == "github.com":
                data = fetch_json(f"https://api.github.com/repos/{owner}/{repo}", timeout=5)
                branch = data.get("default_branch", "HEAD")
            elif host == "gitlab.com":
                data = fetch_json(f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}", timeout=5)
                branch = data.get("default_branch", "HEAD")
        except ValueError:
            pass

    if host == "github.com":
        locator = f"{base_url}/blob/{branch}/{filename}"
        raw_url = f"https://raw.githubusercontent.com/{path_parts[0]}/{path_parts[1]}/{branch}/{filename}"
    elif host == "gitlab.com":
        locator = f"{base_url}/-/blob/{branch}/{filename}"
        raw_url = f"{base_url}/-/raw/{branch}/{filename}"
    else:
        return base_url, "text/plain"

    if offline or content_type_method == "extension":
        ctype, _ = guess_content_type(b"", filename, method="extension")
        return locator, (ctype or "text/plain")

    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "pitloom"})
        with urllib.request.urlopen(req, timeout=5) as res:
            content = res.read()
        ctype, _ = guess_content_type(content, filename, method=content_type_method)
        return locator, (ctype or "text/plain")
    except URLError:
        ctype, _ = guess_content_type(b"", filename, method="extension")
        return locator, (ctype or "text/plain")


def _get_or_create_supplier_agent(
    name: str | None,
    email: str | None,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    repo_url: str | None = None,
    package_name: str | None = None,
    *,
    offline: bool = False,
    content_type_method: str = "auto",
) -> str:
    """Get or create a ``Person`` Agent for a dependency's supplier, deduped
    by ``name``/``email`` so packages sharing an author reuse one Agent."""
    key = f"{name or ''}|{email or ''}"
    is_others = bool(name and "others" in name.lower())
    if is_others:
        key += f"|{repo_url or package_name or 'unknown'}"
    existing = exporter.find_agent(key)
    if existing:
        return existing

    kwargs = {
        "spdxId": generate_spdx_id("Person", doc_name=doc_name, doc_uuid=doc_uuid),
        "name": name or email,
        "creationInfo": creation_info,
    }
    if is_others:
        kwargs["comment"] = "Represents a group of additional contributors referenced externally."
    agent = spdx3.Person(**kwargs)
    if email:
        agent.externalIdentifier = [
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.email,
                identifier=email,
            )
        ]
    if is_others and repo_url:
        import re
        match = re.search(r"see\s+([a-zA-Z0-9_.-]+)", name, re.IGNORECASE)
        filename = match.group(1) if match else "AUTHORS"

        locator, ctype = _resolve_remote_authors_file(
            repo_url, filename, offline, content_type_method
        )

        agent.externalRef = [
            spdx3.ExternalRef(
                externalRefType=spdx3.ExternalRefType.documentation,
                locator=[locator],
                contentType=ctype,
                comment=f"Refers to {filename}"
            )
        ]

    exporter.add_agent(agent, key=key)
    return require_spdx_id(agent)


def _find_license_copyright(dist_name: str, pkg_meta: PackageMetadata) -> str | None:
    """Return a copyright statement from the dependency's installed
    ``License-File``, or ``None`` if not found.

    Only the first :data:`_COPYRIGHT_SEARCH_HEAD_CHARS` of the file are
    searched: a permissive (MIT/BSD-style) license puts its copyright line
    right at the top, while a copyleft/Apache-style license's boilerplate
    body can contain the word "copyright" in an unrelated sentence deep in
    the file (e.g. Apache-2.0 SS4's "You must retain... all copyright...
    notices") -- restricting to the head avoids that false positive, at the
    cost of correctly finding nothing for those license families (which
    don't embed a per-project copyright line in ``LICENSE`` anyway; that
    text lives in an optional, non-standardized ``NOTICE`` file instead).
    """
    license_files = pkg_meta.get_all("License-File") or []
    if not license_files:
        return None
    try:
        dist = get_pkg_distribution(dist_name)
    except PackageNotFoundError:
        return None

    package_files = dist.files or []
    for license_file in license_files:
        for candidate in package_files:
            if candidate.name != license_file:
                continue
            # License-File-declared files live under the package's own
            # .dist-info directory (PEP 639, either directly or under its
            # licenses/ subdirectory) -- restricting to that prevents a
            # same-named LICENSE file elsewhere in the installed package
            # tree (e.g. a vendored third-party library at
            # mypkg/vendor/otherlib/LICENSE) from being matched instead of
            # the real one, misattributing that library's copyright.
            if not str(candidate).split("/", 1)[0].endswith(".dist-info"):
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not text:
                continue
            match = _COPYRIGHT_LINE_RE.search(text[:_COPYRIGHT_SEARCH_HEAD_CHARS])
            if match:
                return match.group(0).strip()
    return None


def _parse_project_urls(pkg_meta: PackageMetadata) -> dict[str, str]:
    """Return a lowercased-label -> URL dict from ``Project-URL`` metadata entries."""
    result: dict[str, str] = {}
    entries = pkg_meta.get_all("Project-URL") or []
    for entry in entries:
        if "," in entry:
            label, url = entry.split(",", 1)
            result[label.strip().lower()] = url.strip()
    return result


def _resolve_metadata_url(
    core_value: str, project_urls: dict[str, str], labels: tuple[str, ...]
) -> str | None:
    """Return *core_value* if set and not ``"UNKNOWN"``, else the first
    *project_urls* entry matching one of *labels* (checked in order --
    *labels* must be an ordered sequence, not a set, so which one wins
    when several match is deterministic), else ``None``."""
    value = core_value
    if not value or value == "UNKNOWN":
        for label in labels:
            if label in project_urls:
                value = project_urls[label]
                break
    return value if value and value != "UNKNOWN" else None


def _apply_supplier(
    suppliers: list[tuple[str | None, str | None]],
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    repo_url: str | None = None,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
    provenance_source: str = "",
    offline: bool = False,
    content_type_method: str = "auto",
) -> bool:
    """Set ``suppliedBy`` to a list of Agent(s) built from *suppliers*.
    Returns whether it was set."""
    if not suppliers:
        return False
        
    supplier_ids = []
    for name, email in suppliers:
        if name or email:
            agent_id = _get_or_create_supplier_agent(
                name, email, creation_info, doc_name, doc_uuid, exporter, repo_url=repo_url, package_name=dep_package.name, offline=offline, content_type_method=content_type_method
            )
            supplier_ids.append(agent_id)
            
    if not supplier_ids:
        return False
        
    if supplier_ids:
        dep_package.suppliedBy = supplier_ids[0]
    
    if provenance_source:
        method = "parsed_author_list" if len(suppliers) > 1 else ""
        prov_str = f"{provenance_source} | Method: {method}" if method else provenance_source
        emit_provenance(
            subject=dep_package,
            provenance={"suppliedBy": prov_str},
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
    return True


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _apply_license(
    license_id: str | None,
    license_provenance: str,
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> bool:
    """Build and add whichever declared/concluded license relationship(s)
    *license_id* resolves to (see :func:`build_license_elements`). Returns
    whether anything was added."""
    if not license_id or license_id == "UNKNOWN":
        return False
    rel_declared, rel_concluded = build_license_elements(
        license_id=license_id,
        package_spdx_id=require_spdx_id(dep_package),
        license_provenance=license_provenance,
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    for rel in (rel_declared, rel_concluded):
        if rel:
            exporter.add_relationship(rel)
    return True


# pylint: disable=too-many-arguments,too-many-positional-arguments
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

    repo_url = _resolve_metadata_url("", project_urls, ("repository", "source", "source code"))
    if not repo_url:
        repo_url = home_page

    # packageUrl -- PyPI PURL (pkg:pypi/<name>@<version>)
    version = dep_package.software_packageVersion
    if version and version != "unknown":
        dep_package.software_packageUrl = build_pypi_purl(dep_name, version)

    # suppliedBy -- Person built from Author/Maintainer metadata, when known
    suppliers = _resolve_supplier(pkg_meta)
    if _apply_supplier(
        suppliers,
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
        filled.add("supplier")

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
    unavailable; see :func:`_fetch_pypi_release_info`.

    *release_info_cache*, when given, must already contain an entry for
    this dependency's ``(name, version)`` key -- see
    :func:`_prefetch_pypi_release_infos`, which every current caller uses
    to fetch all of a document's dependencies concurrently before this
    function runs for any of them. Falls back to fetching individually
    when omitted (e.g. a direct unit-test call).
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
    repo_url = _resolve_metadata_url("", lower_project_urls, ("repository", "source", "source code"))
    if not repo_url:
        home_page = info.get("home_page") or _resolve_metadata_url(info.get("project_url") or "", lower_project_urls, _HOMEPAGE_LABELS)
        repo_url = home_page

    if "supplier" not in already_filled:
        suppliers = _extract_pypi_supplier(info)
        if _apply_supplier(
            suppliers,
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
            filled.add("supplier")

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
def _add_license_noassertion(
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> None:
    """Assert ``hasDeclaredLicense: NOASSERTION`` for a package whose license
    couldn't be determined locally or via PyPI -- an explicit "we checked
    and don't know" is more useful to a consumer than a silently absent
    field, and is the standard SPDX placeholder for exactly this case.
    Deduped like any other license value, so every such package shares one
    NOASSERTION element.
    """
    license_spdx_id = _get_or_create_license_element(
        "NOASSERTION",
        "Source: NOASSERTION (no license information found locally or via PyPI)",
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    exporter.add_relationship(
        _build_license_relationship(
            require_spdx_id(dep_package),
            license_spdx_id,
            spdx3.RelationshipType.hasDeclaredLicense,
            creation_info,
            doc_name,
            doc_uuid,
        )
    )


def _is_license_concluded(parsed_prov: dict[str, str]) -> bool:
    """Determine if a license is concluded rather than declared.

    A license is concluded if we used a heuristic/detection method,
    or if the source is not a transparent manifest (e.g. it was extracted
    from a LICENSE file directly).
    """
    if parsed_prov.get("method"):
        return True
    source = parsed_prov.get("source", "").strip().lower()
    if " (" in source:
        source = source.split(" (", 1)[0].strip()
    return not source or source not in TRANSPARENT_SOURCES


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _get_or_create_license_element(
    license_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> str:
    """Get or create a ``SimpleLicensingText`` element for *license_id*, deduped
    by license-id string, and return its spdxId."""
    existing_spdx_id = exporter.find_license(license_id)
    if existing_spdx_id:
        return existing_spdx_id

    name_str = license_id.strip()
    if "\n" in name_str:
        name_str = name_str.split("\n")[0]
    if len(name_str) > 60:
        name_str = name_str[:57] + "..."

    license_text = spdx3.simplelicensing_SimpleLicensingText(
        spdxId=generate_spdx_id("License", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
    )
    license_text.name = name_str
    license_text.simplelicensing_licenseText = license_id
    exporter.add_license(license_text)
    emit_provenance(
        subject=license_text,
        provenance={"license": license_provenance},
        creation_info=creation_info,
        doc_name=doc_name,
        doc_uuid=doc_uuid,
        exporter=exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    return require_spdx_id(license_text)


def _build_license_relationship(
    package_spdx_id: str,
    license_spdx_id: str,
    relationship_type: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.Relationship:
    return spdx3.Relationship(
        spdxId=generate_spdx_id("Relationship", doc_name=doc_name, doc_uuid=doc_uuid),
        creationInfo=creation_info,
        from_=package_spdx_id,
        relationshipType=relationship_type,
        to=[license_spdx_id],
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def build_license_elements(
    license_id: str,
    package_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    concluded_license_id: str | None = None,
    concluded_license_provenance: str | None = None,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> tuple[spdx3.Relationship | None, spdx3.Relationship | None]:
    """Get or create SimpleLicensingText element(s) and build declared/concluded
    license relationships.

    Single-candidate mode (*concluded_license_id* omitted, the default):
    unchanged behavior -- one element, classified as declared XOR concluded
    via :func:`_is_license_concluded` on *license_provenance*.

    Two-candidate mode (G2, *concluded_license_id* given -- currently only the
    main project package path supplies this, since it's the only one with a
    local directory to independently detect a second opinion from): *license_id*
    is always the declared value, *concluded_license_id* the independently
    detected one. Both relationships are built unconditionally, whether or not
    the two agree -- when they *do* agree, both point at the same deduped
    license element. When they disagree, an additional G2 conflict Annotation
    is emitted on *package_spdx_id* recording both candidates; see
    :func:`~pitloom.assemble.spdx3.provenance.build_conflict_annotation`.
    """
    if concluded_license_id is None:
        license_spdx_id = _get_or_create_license_element(
            license_id,
            license_provenance,
            creation_info,
            doc_name,
            doc_uuid,
            exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
        parsed_prov = parse_provenance_value(license_provenance)
        if _is_license_concluded(parsed_prov):
            return None, _build_license_relationship(
                package_spdx_id,
                license_spdx_id,
                spdx3.RelationshipType.hasConcludedLicense,
                creation_info,
                doc_name,
                doc_uuid,
            )
        return (
            _build_license_relationship(
                package_spdx_id,
                license_spdx_id,
                spdx3.RelationshipType.hasDeclaredLicense,
                creation_info,
                doc_name,
                doc_uuid,
            ),
            None,
        )

    # Normalize both candidates to a canonical SPDX license expression before
    # comparing or creating elements -- otherwise a mere casing difference
    # (declared "mit", detected "MIT") or an equivalent-but-differently-
    # spelled compound expression ("MIT AND MIT" vs "MIT") would be
    # misreported as a genuine conflict and create two separate license
    # elements for one license. Unrecognized values pass through unchanged
    # (see normalize_license_expression).
    canonical_declared_id = normalize_license_expression(license_id.strip())
    canonical_concluded_id = normalize_license_expression(concluded_license_id.strip())

    # Flag when normalization actually rewrote a candidate's value (e.g. a
    # casing fix or a dedup/reorder of a compound expression), and record
    # the py-spdx-license version that did it -- so a G2 candidate's
    # evidence stays auditable even when its stored value differs from what
    # the source literally said. No-op when normalization was a pass-through.
    declared_provenance = tag_license_normalization(
        license_provenance, license_id, canonical_declared_id
    )
    concluded_provenance = tag_license_normalization(
        concluded_license_provenance or license_provenance,
        concluded_license_id,
        canonical_concluded_id,
    )

    declared_spdx_id = _get_or_create_license_element(
        canonical_declared_id,
        declared_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    concluded_spdx_id = _get_or_create_license_element(
        canonical_concluded_id,
        concluded_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )

    rel_has_declared_license = _build_license_relationship(
        package_spdx_id,
        declared_spdx_id,
        spdx3.RelationshipType.hasDeclaredLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )
    rel_has_concluded_license = _build_license_relationship(
        package_spdx_id,
        concluded_spdx_id,
        spdx3.RelationshipType.hasConcludedLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )

    if canonical_declared_id != canonical_concluded_id:
        candidates: list[ConflictCandidate] = [
            {
                "value": canonical_declared_id,
                "role": "declared",
                "source": declared_provenance,
                "ref": declared_spdx_id,
            },
            {
                "value": canonical_concluded_id,
                "role": "detected",
                "source": concluded_provenance,
                "ref": concluded_spdx_id,
            },
        ]
        exporter.add_annotation(
            build_conflict_annotation(
                subject_spdx_id=package_spdx_id,
                field="license",
                candidates=candidates,
                creation_info=creation_info,
                annotation_spdx_id=generate_spdx_id(
                    "Annotation", doc_name=doc_name, doc_uuid=doc_uuid
                ),
            )
        )

    return rel_has_declared_license, rel_has_concluded_license


# pylint: disable=too-many-arguments,too-many-positional-arguments
def build_file_declared_license(
    license_id: str,
    file_spdx_id: str,
    license_provenance: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    provenance_config: ProvenanceConfig | None = None,
    encoder: ProvenanceEncoder | None = None,
) -> spdx3.Relationship:
    """Get-or-create a ``SimpleLicensingText`` element for *license_id* and
    return a ``hasDeclaredLicense`` Relationship from *file_spdx_id* to it.

    Unlike :func:`build_license_elements`, this never applies the
    declared/concluded classification heuristic
    (:func:`_is_license_concluded`): a file's own ``SPDX-License-Identifier``
    tag is always its own ``declared`` claim by construction -- there is
    exactly one candidate at file granularity, nothing to disambiguate
    against. Calling :func:`build_license_elements` here would silently
    misclassify it as ``hasConcludedLicense`` instead, since a file's own
    path is never in :data:`~pitloom.assemble.spdx3.provenance.TRANSPARENT_SOURCES`.

    Dedup is by license-id string via :func:`_get_or_create_license_element`
    -- a file whose license matches the project's or another file's reuses
    the same element.
    """
    license_spdx_id = _get_or_create_license_element(
        license_id,
        license_provenance,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config=provenance_config,
        encoder=encoder,
    )
    return _build_license_relationship(
        file_spdx_id,
        license_spdx_id,
        spdx3.RelationshipType.hasDeclaredLicense,
        creation_info,
        doc_name,
        doc_uuid,
    )


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
    of a prior :func:`_prefetch_pypi_release_infos` call covering this
    dependency to avoid a per-dependency blocking network round-trip.
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

        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            from_=main_package_spdx_id,
            to=[require_spdx_id(dep_package)],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
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
        dep_rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
            ),
            from_=main_package_spdx_id,
            to=[require_spdx_id(dep_package)],
            relationshipType=spdx3.RelationshipType.dependsOn,
            creationInfo=creation_info,
        )
        exporter.add_relationship(dep_rel)

        # Link the phantom package to the physical file if it was registered
        file_spdx_id = file_spdx_ids.get(dep.file_path)
        if file_spdx_id:
            file_rel = spdx3.Relationship(
                spdxId=generate_spdx_id(
                    "Relationship", doc_name=doc_name, doc_uuid=doc_uuid
                ),
                from_=require_spdx_id(dep_package),
                to=[file_spdx_id],
                relationshipType=spdx3.RelationshipType.contains,
                creationInfo=creation_info,
            )
            exporter.add_relationship(file_rel)
