# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Which earlier SBOMs a wheel embed replaces.

See also: :mod:`pitloom._embed_wheel` (the embed, which calls
:func:`stale_sboms`).
"""

from __future__ import annotations

import json
import logging
import zipfile

from pitloom._sbom_format import check_spdx3_name_version, detect_sbom_format
from pitloom._wheel_sbom_location import read_wheel_member, read_wheel_name_version
from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)


def looks_like_pitloom_sbom(content: bytes) -> bool:
    """Check whether an SPDX 3 JSON-LD payload was created by Pitloom."""
    try:
        doc = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return False
    graph = doc.get("@graph") if isinstance(doc, dict) else None
    if not isinstance(graph, list):
        return False
    return any(
        isinstance(node, dict)
        and node.get("type") in ("Tool", "SoftwareAgent")
        and node.get("name") == "Pitloom"
        for node in graph
    )


#: ``software_sbomType`` values of an SBOM a re-embed supersedes.
_REPLACEABLE_SBOM_TYPES = frozenset({"build", "analyzed"})


def _is_replaceable_sbom(content: bytes, name: str | None, version: str | None) -> bool:
    """Whether *content*, a Pitloom SBOM (:func:`looks_like_pitloom_sbom`),
    is of type build or analyzed and for the wheel *name* and *version*: the
    SBOM a new embed supersedes. One of another type, or of another project
    or version (or one whose subject cannot be told), is somebody's own,
    shipped on purpose."""
    graph = json.loads(content)["@graph"]
    types = {
        t
        for node in graph
        if isinstance(node, dict) and node.get("type") == "software_Sbom"
        for t in (node.get("software_sbomType") or [])
        if isinstance(t, str)
    }
    if not types & _REPLACEABLE_SBOM_TYPES:
        return False
    mismatches, warnings = check_spdx3_name_version(
        name, version, content, detect_sbom_format(content)
    )
    return not mismatches and not warnings


def stale_sboms(
    zf: zipfile.ZipFile,
    members: dict[str, zipfile.ZipInfo],
    dist_info: str,
    keep: str,
    identity: tuple[str | None, str | None] | None,
) -> frozenset[str]:
    """The Pitloom SBOMs under ``<dist_info>sboms/`` (other than *keep*) a
    new embed removes: those :func:`_is_replaceable_sbom` accepts. Any other
    Pitloom SBOM stays, with one ``WARNING:`` each."""
    candidates = [
        (name, info)
        for name, info in members.items()
        if name.startswith(f"{dist_info}sboms/")
        and name.endswith(SPDX3_JSONLD_EXTENSION)
        and name != keep
    ]
    stale: set[str] = set()
    wheel_id = identity
    for name, info in candidates:
        content = read_wheel_member(zf, info)
        if not looks_like_pitloom_sbom(content):
            continue
        if wheel_id is None:
            wheel_id = read_wheel_name_version(
                zf, dist_info, members=list(members.items())
            )
        if _is_replaceable_sbom(content, *wheel_id):
            stale.add(name)
        else:
            log.warning(
                "%s: kept, not a build or analyzed SBOM of this wheel's "
                "name and version",
                loggable(name),
            )
    return frozenset(stale)
