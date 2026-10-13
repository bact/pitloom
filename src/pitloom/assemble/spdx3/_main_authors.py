# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The main package's authors as its ``originatedBy`` Agents, the same on
every route (wheel, sdist, directory, Hatchling hook, ``embed-wheel``).
The authors never make its copyright text: that is a notice found in its
licence files (:mod:`pitloom.extract.copyright_notices`).

See also: :mod:`pitloom.assemble.spdx3.document` (the caller) and
:mod:`pitloom.assemble.spdx3.deps_originator` (the Agent dedup shared with
dependency originators).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.deps_originator import get_or_create_originator_agent
from pitloom.core.creation import Creator
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, agent_key


def _author_identity(author: dict[str, str]) -> tuple[str | None, str | None]:
    """``(name, email)``, stripped, blank as ``None``: the identity an
    author's ``originatedBy`` Agent is deduped on."""
    name, email = author.get("name"), author.get("email")
    return (name or "").strip() or None, (email or "").strip() or None


# pylint: disable-next=too-many-arguments
def add_main_package_originators(
    main_package: spdx3.software_Package,
    metadata: ProjectMetadata,
    creators: list[tuple[Creator, spdx3.Agent]],
    creation_info: spdx3.CreationInfo,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
    *,
    offline: bool = False,
) -> None:
    """Set *main_package*'s ``originatedBy`` to one Agent per author, in
    order.

    Call last, after every other Agent is minted: Agent ids are per-type
    sequence numbers, so minting here keeps the ids of creator, dependency
    and AI-model Agents unchanged. An author with the same agent type, name and
    address as an SBOM creator (*creators*, each with its Agent) or a
    dependency originator is that Agent, not a second one (an author is a
    Person, or an Organization for a contributor group); a creator is registered
    for this only now, so dependency originators are not affected.
    """
    for creator, agent in creators:
        key = agent_key(type(agent), creator.name, creator.email)
        if exporter.find_agent(key) is None:
            exporter.add_agent(agent, key=key)
    originators: list[str] = []
    for author in metadata.authors:
        name, email = _author_identity(author)
        if not (name or email):
            continue
        agent_id, _ = get_or_create_originator_agent(
            name,
            email,
            creation_info,
            metadata.name,
            doc_uuid,
            exporter,
            package_name=metadata.name,
            offline=offline,
        )
        originators.append(agent_id)
    if originators:
        main_package.originatedBy = list(dict.fromkeys(originators))


__all__ = [
    "add_main_package_originators",
]
