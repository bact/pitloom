# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Supplier/originator resolution for dependency enrichment.

See also: :mod:`pitloom.assemble.spdx3.deps`, which calls into this module
to populate a dependency package's ``originatedBy``.
"""

from __future__ import annotations

import functools
import http.client
import re
import urllib.request
from email.utils import getaddresses
from importlib.metadata import PackageMetadata, PackageNotFoundError
from importlib.metadata import distribution as get_pkg_distribution
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract._file_headers import guess_content_type

# A permissive (MIT/BSD-style) LICENSE file's copyright line, e.g.
# "Copyright (c) 2021 Taneli Hukkinen" or "Copyright © 2019 Filipe Laíns".
_COPYRIGHT_LINE_RE = re.compile(
    r"^\s*Copyright\s+(?:\(c\)|©)?\s*\S.*$", re.IGNORECASE | re.MULTILINE
)
# Only the file's head is searched -- see _find_license_copyright.
_COPYRIGHT_SEARCH_HEAD_CHARS = 500


def _extract_suppliers(
    name: str, email_raw: str
) -> list[tuple[str | None, str | None]]:
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
        results = _extract_suppliers(
            pkg_meta[name_field] or "", pkg_meta[email_field] or ""
        )
        if results:
            return results
    return []


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


@functools.lru_cache(maxsize=256)
def _resolve_remote_authors_file(
    repo_url: str,
    filename: str,
    offline: bool,
    content_type_method: str,
) -> tuple[str, str | None, str | None]:
    """Resolve the URL locator and content type for a remote authors file."""
    base_url = repo_url[:-4] if repo_url.endswith(".git") else repo_url
    base_url = base_url.rstrip("/")
    parsed = urlparse(base_url)
    host = parsed.netloc.lower()
    path_parts = [p for p in parsed.path.split("/") if p]

    branch = "HEAD"

    if len(path_parts) >= 2:
        if host == "github.com":
            locator = f"{base_url}/blob/{branch}/{filename}"
            raw_url = (
                f"https://raw.githubusercontent.com/{path_parts[0]}/"
                f"{path_parts[1]}/{branch}/{filename}"
            )
        elif host == "gitlab.com":
            locator = f"{base_url}/-/blob/{branch}/{filename}"
            raw_url = f"{base_url}/-/raw/{branch}/{filename}"
        else:
            return base_url, None, None
    else:
        return base_url, None, None

    if offline or content_type_method == "extension":
        ctype, _ = guess_content_type(b"", filename, method="extension")
        return locator, ctype, None

    try:
        if not raw_url.startswith(("http://", "https://")):
            raise ValueError(f"Disallowed scheme in URL: {raw_url}")
        req = urllib.request.Request(raw_url, headers={"User-Agent": "pitloom"})
        with urllib.request.urlopen(req, timeout=5) as res:  # nosec B310
            content = res.read(1024 * 64)
        ctype, _ = guess_content_type(content, filename, method=content_type_method)
        return (
            locator,
            ctype,
            content.decode("utf-8", errors="replace"),
        )
    except (URLError, http.client.HTTPException, OSError, ValueError):
        ctype, _ = guess_content_type(b"", filename, method="extension")
        return locator, ctype, None


# pylint: disable=too-many-arguments,too-many-locals
# pylint: disable-next=too-many-positional-arguments
def _get_or_create_originator_agent(
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
) -> tuple[str, str | None]:
    """Get or create an Agent for a dependency's originator, deduped
    by ``name``/``email`` so packages sharing an author reuse one Agent."""
    key = f"{name or ''}|{email or ''}"
    is_others = bool(name and "others" in name.lower())
    if is_others:
        key += f"|{repo_url or package_name or 'unknown'}"
    existing = exporter.find_agent(key)
    if existing:
        return existing, None

    agent_type = "Organization" if is_others else "Person"
    kwargs = {
        "spdxId": generate_spdx_id(agent_type, doc_name=doc_name, doc_uuid=doc_uuid),
        "name": name or email,
        "creationInfo": creation_info,
    }
    agent: spdx3.Agent
    if is_others:
        kwargs["comment"] = (
            "Represents a group of additional contributors referenced externally."
        )
        agent = spdx3.Organization(**kwargs)  # type: ignore[arg-type]
    else:
        agent = spdx3.Person(**kwargs)  # type: ignore[arg-type]
    if email:
        agent.externalIdentifier = [
            spdx3.ExternalIdentifier(
                externalIdentifierType=spdx3.ExternalIdentifierType.email,
                identifier=email,
            )
        ]
    attribution_text = None
    if is_others and repo_url:
        match = re.search(r"see\s+([a-zA-Z0-9_.-]+)", str(name), re.IGNORECASE)
        filename = match.group(1) if match else "AUTHORS"

        locator, ctype, fetched_text = _resolve_remote_authors_file(
            repo_url, filename, offline, content_type_method
        )

        ref_kwargs: dict[str, Any] = {
            "externalRefType": spdx3.ExternalRefType.documentation,
            "locator": [locator],
            "comment": f"Refers to {filename}",
        }
        if ctype:
            ref_kwargs["contentType"] = ctype

        agent.externalRef = [spdx3.ExternalRef(**ref_kwargs)]

        attribution_text = fetched_text
        if not attribution_text:
            attribution_text = (
                "Attribution: This package includes contributions from additional "
                f"authors detailed in the {filename} file at {repo_url}."
            )

    exporter.add_agent(agent, key=key)
    return require_spdx_id(agent), attribution_text


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _apply_originator(
    originators: list[tuple[str | None, str | None]],
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
    """Set ``originatedBy`` to a list of Agent(s) built from *originators*.
    Returns whether it was set."""
    if not originators:
        return False

    originator_ids = []
    for name, email in originators:
        if name or email:
            agent_id, attribution_text = _get_or_create_originator_agent(
                name,
                email,
                creation_info,
                doc_name,
                doc_uuid,
                exporter,
                repo_url=repo_url,
                package_name=dep_package.name,
                offline=offline,
                content_type_method=content_type_method,
            )
            originator_ids.append(agent_id)
            if attribution_text:
                if not dep_package.software_attributionText:
                    dep_package.software_attributionText = [attribution_text]
                else:
                    dep_package.software_attributionText.append(attribution_text)

    if not originator_ids:
        return False

    dep_package.originatedBy = originator_ids

    if provenance_source:
        method = "parsed_author_list" if len(originators) > 1 else ""
        prov_str = (
            f"{provenance_source} | Method: {method}" if method else provenance_source
        )
        prov_dict = {"originatedBy": prov_str}

        if dep_package.software_attributionText and repo_url:
            prov_dict["software_attributionText"] = (
                f"Fetched from AUTHORS at {repo_url}"
            )

        emit_provenance(
            subject=dep_package,
            provenance=prov_dict,
            creation_info=creation_info,
            doc_name=doc_name,
            doc_uuid=doc_uuid,
            exporter=exporter,
            provenance_config=provenance_config,
            encoder=encoder,
        )
    return True
