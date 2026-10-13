# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Originator resolution for dependency enrichment.

See also: :mod:`pitloom.assemble.spdx3.deps`, which calls into this module
to populate a dependency package's ``originatedBy``.
"""

from __future__ import annotations

import functools
import http.client
import re
import urllib.request
from importlib.metadata import PackageNotFoundError
from importlib.metadata import distribution as get_pkg_distribution
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import URLError
from urllib.parse import urlparse

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.provenance import ProvenanceEncoder, emit_provenance
from pitloom.core._models_wheel_types import is_dist_info_path
from pitloom.core.models import generate_spdx_id
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import (
    Spdx3JsonExporter,
    agent_key,
    require_spdx_id,
)
from pitloom.extract._core_metadata import parse_project_urls
from pitloom.extract._extract_utils import close_http_error, pkg_meta_get
from pitloom.extract._file_headers import guess_content_type
from pitloom.extract.authors import dependency_author_pairs, is_contributor_group
from pitloom.extract.copyright_notices import (
    join_copyright_notices,
    read_license_text,
)

if TYPE_CHECKING:
    from pitloom.extract._extract_utils import CoreMetadata


def _resolve_author_or_maintainer(
    pkg_meta: CoreMetadata, package: str
) -> list[tuple[str | None, str | None]]:
    """Return a list of ``(name, email)`` tuples for the dependency
    *package*'s originator from installed metadata, or an empty list.
    Tries ``Author``/``Author-email`` first, then falls back to
    ``Maintainer``/``Maintainer-email``; each pair is read as a package's
    own authors are (:func:`~pitloom.extract.authors.dependency_author_pairs`)."""
    for name_field, email_field in (
        ("Author", "Author-email"),
        ("Maintainer", "Maintainer-email"),
    ):
        results = dependency_author_pairs(
            package,
            pkg_meta_get(pkg_meta, name_field),
            pkg_meta_get(pkg_meta, email_field),
        )
        if results:
            return results
    return []


def _read_candidate_text(candidate: Any) -> str | None:
    """The text of the installed file *candidate* (an
    :class:`importlib.metadata.PackagePath`) when it is under a
    ``.dist-info`` (:func:`~pitloom.extract.copyright_notices.read_license_text`:
    capped, a present file that cannot be read warned about); else ``None``."""
    if not is_dist_info_path(str(candidate)):
        return None
    return read_license_text(Path(candidate.locate()))


def _find_license_copyright(dist_name: str, pkg_meta: CoreMetadata) -> str | None:
    """The copyright notices in the dependency's installed ``License-File``
    files (:func:`~pitloom.extract.copyright_notices.join_copyright_notices`,
    in ``License-File`` order), or ``None`` when none holds one."""
    license_files = pkg_meta.get_all("License-File") or []
    if not license_files:
        return None
    try:
        dist = get_pkg_distribution(dist_name)
    except PackageNotFoundError:
        return None

    package_files = dist.files or []
    texts = (
        (license_file, text)
        for license_file in license_files
        for candidate in package_files
        if candidate.name == license_file
        and (text := _read_candidate_text(candidate)) is not None
    )
    found = join_copyright_notices(texts)
    return None if found is None else found[0]


def _parse_project_urls(pkg_meta: CoreMetadata) -> dict[str, str]:
    """Return a lowercased-label -> URL dict from ``Project-URL`` metadata
    entries. Delegates to the shared
    :func:`pitloom.extract._core_metadata.parse_project_urls` helper; this
    wrapper is kept since other code in this module imports it."""
    return parse_project_urls(pkg_meta, lowercase_labels=True, include_homepage=False)


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
    except (URLError, http.client.HTTPException, OSError, ValueError) as exc:
        close_http_error(exc)
        ctype, _ = guess_content_type(b"", filename, method="extension")
        return locator, ctype, None


# pylint: disable=too-many-arguments,too-many-locals
# pylint: disable-next=too-many-positional-arguments
def get_or_create_originator_agent(
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
    """Get or create an Agent for a dependency's originator, deduped by
    :func:`~pitloom.export.spdx3_json.agent_key` so packages sharing an
    author reuse one Agent; a contributor group is an Organization, one per
    repository or package."""
    is_others = is_contributor_group(name)
    agent_cls: type[spdx3.Agent] = spdx3.Organization if is_others else spdx3.Person
    scope = (repo_url or package_name or "unknown") if is_others else ""
    key = agent_key(agent_cls, name, email, scope)
    existing = exporter.find_agent(key)
    if existing:
        return existing, None

    kwargs = {
        "spdxId": generate_spdx_id(
            agent_cls.__name__, doc_name=doc_name, doc_uuid=doc_uuid
        ),
        "name": name or email,
        "creationInfo": creation_info,
    }
    if is_others:
        kwargs["comment"] = (
            "Represents a group of additional contributors referenced externally."
        )
    agent = agent_cls(**kwargs)  # type: ignore[arg-type]
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
def _collect_originator_agents(
    originators: list[tuple[str | None, str | None]],
    dep_package: spdx3.software_Package,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    repo_url: str | None,
    offline: bool,
    content_type_method: str,
) -> list[str]:
    """Create originator agents and append attribution texts."""
    originator_ids = []
    for name, email in originators:
        if not (name or email):
            continue
        agent_id, attribution_text = get_or_create_originator_agent(
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
    return originator_ids


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _emit_originator_provenance(
    dep_package: spdx3.software_Package,
    originators_count: int,
    provenance_source: str,
    repo_url: str | None,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    provenance_config: ProvenanceConfig | None,
    encoder: ProvenanceEncoder | None,
) -> None:
    """Emit provenance annotations for originator assignment."""
    if not provenance_source:
        return
    method = "parsed_author_list" if originators_count > 1 else ""
    prov_str = (
        f"{provenance_source} | Method: {method}" if method else provenance_source
    )
    prov_dict = {"originatedBy": prov_str}
    if dep_package.software_attributionText and repo_url:
        prov_dict["software_attributionText"] = f"Fetched from AUTHORS at {repo_url}"
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

    originator_ids = _collect_originator_agents(
        originators,
        dep_package,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        repo_url,
        offline,
        content_type_method,
    )
    if not originator_ids:
        return False

    dep_package.originatedBy = originator_ids
    _emit_originator_provenance(
        dep_package,
        len(originators),
        provenance_source,
        repo_url,
        creation_info,
        doc_name,
        doc_uuid,
        exporter,
        provenance_config,
        encoder,
    )
    return True
