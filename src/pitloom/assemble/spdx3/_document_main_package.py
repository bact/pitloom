# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SPDX 3 creation objects and the main package of a project SBOM.

Shared by :func:`pitloom.assemble.spdx3.document.build` and
:func:`pitloom.assemble.spdx3._document_deployed.build_deployed`, so both
describe the main package by one rule.
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.creation_info import (
    build_creation_info,
    parse_iso_datetime,
    to_spdx3_datetime,
)
from pitloom.core.document import DocumentModel
from pitloom.core.models import build_pypi_purl, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, agent_key, sha256_hash
from pitloom.extract.copyright_notices import COPYRIGHT_NOASSERTION
from pitloom.messages.config import Parameter

#: Creator Agent types a dependency originator or an author can be.
_KEYED_CREATORS = (spdx3.Person, spdx3.Organization)


def add_creation_bundle(
    exporter: Spdx3JsonExporter, doc: DocumentModel, doc_uuid: str
) -> tuple[spdx3.CreationInfo, list[spdx3.Agent]]:
    """Build the creation info, its creator Agents and its tools, add them
    to *exporter*, and return the creation info and the Agents.

    A named Person or Organization creator (one Agent per creator, in order)
    is registered under its :func:`~pitloom.export.spdx3_json.agent_key`
    before any other Agent is minted, so a dependency originator or a
    main-package author of the same type, name and address is that Agent, not
    a second one. (Every Organization an originator route mints today is a
    contributor group, keyed with its package as scope, so only a Person
    merges until another route mints an unscoped Organization.) A generic
    Agent or SoftwareAgent creator is registered under no key: an AI-model
    originator is keyed on its name alone and stays apart. With no named
    creator the one Agent is the SoftwareAgent "Pitloom".
    """
    creators = doc.creation_metadata.creators
    spdx_ci, agents, tools = build_creation_info(
        doc.creation_metadata, doc.project.name, doc_uuid
    )
    exporter.add_creation_info(spdx_ci)
    if not creators:
        for agent in agents:
            exporter.add_agent(agent)
    for creator, agent in zip(creators, agents, strict=bool(creators)):
        key = agent_key(type(agent), creator.name, creator.email)
        # Two creators of one identity: the first keeps the key.
        keyed = isinstance(agent, _KEYED_CREATORS) and not exporter.find_agent(key)
        exporter.add_agent(agent, key=key if keyed else None)
    for tool in tools:
        exporter.object_set.add(tool)
    return spdx_ci, agents


def build_main_package(
    doc: DocumentModel,
    spdx_ci: spdx3.CreationInfo,
    agents: list[spdx3.Agent],
    doc_uuid: str,
    merkle_root: str | None = None,
    resolved_id: str | None = None,
) -> spdx3.software_Package:
    """Create the SPDX package representing the Python project.

    *resolved_id* is the pre-resolved registry id (see
    :func:`~pitloom.assemble.spdx3._package_ids.resolve_project_package_ids`);
    ``None`` mints one.
    """
    metadata = doc.project
    creation_metadata = doc.creation_metadata
    download_location = metadata.urls.get("Source") or metadata.urls.get("Homepage")
    main_package = spdx3.software_Package(
        spdxId=resolved_id
        or generate_spdx_id("Package", doc_name=metadata.name, doc_uuid=doc_uuid),
        name=metadata.name,
        creationInfo=spdx_ci,
    )
    main_package.software_packageVersion = metadata.version or "unknown"
    # suppliedBy names who supplied the package, so only assert it for a named
    # person, organisation or generic agent -- not for a software agent (the
    # default "Pitloom", or a service that ran Pitloom), which made the SBOM and
    # did not supply the package.  suppliedBy is single-valued in SPDX 3, so
    # when several are named, the *first* of those is used.  With no creator
    # named, *agents* holds only the default "Pitloom" and the zip is empty.
    supplier = next(
        (
            agent
            for creator, agent in zip(creation_metadata.creators, agents, strict=False)
            if creator.type != "software-agent"
        ),
        None,
    )
    if supplier is not None:
        main_package.suppliedBy = supplier.spdxId
    if metadata.description:
        main_package.description = metadata.description
    if download_location:
        main_package.software_downloadLocation = download_location
    if metadata.urls.get("Homepage"):
        main_package.software_homePage = metadata.urls.get("Homepage")
    # The notices found in its licence files; none found is no assertion.
    main_package.software_copyrightText = (
        metadata.copyright_text or COPYRIGHT_NOASSERTION
    )
    main_package.software_primaryPurpose = spdx3.software_SoftwarePurpose.library
    if creation_metadata.build_datetime:
        # The same parse as CreationInfo.created: "Z" on every Python,
        # offsets converted to UTC, whole seconds.
        main_package.builtTime = to_spdx3_datetime(
            parse_iso_datetime(
                creation_metadata.build_datetime, Parameter("build_datetime")
            )
        )

    # packageUrl -- PyPI PURL (pkg:pypi/<name>@<version>), only when a real
    # version is known.  Mirrors the dependency PURL logic in deps.py.
    if metadata.version and metadata.version != "unknown":
        main_package.software_packageUrl = build_pypi_purl(
            metadata.name, metadata.version
        )

    # verifiedUsing -- the same Merkle root already folded into doc_uuid
    # (see compute_doc_uuid), asserted here as the package's own integrity
    # hash so NTIA/CISA "integrity hash" coverage extends to the main
    # package itself, not just its individual files.
    if merkle_root is not None:
        main_package.verifiedUsing = [
            sha256_hash(
                merkle_root,
                comment=(
                    "SHA-256 Merkle root over the payload files; "
                    "not a hash of a single artifact"
                ),
            )
        ]

    return main_package
