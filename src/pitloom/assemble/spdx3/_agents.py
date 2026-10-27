# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one generic ``Agent`` per name of a document.

A model's originator and supplier and a dataset's creator are named, not
typed: a name does not say a person from an organisation. Every such name is
one generic ``Agent`` however many elements name it, so an Alice who produced
a model and published its dataset is one element, not two.

See also: :mod:`pitloom.assemble.spdx3._ai_originators` and
:mod:`pitloom.assemble.spdx3.dataset` (the callers).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, agent_key, require_spdx_id

#: The creation info, document name and document uuid an element is minted with.
Doc = tuple[spdx3.CreationInfo, str, str]


def generic_agent(
    name: str, doc: Doc, exporter: Spdx3JsonExporter
) -> tuple[str, spdx3.Agent | None]:
    """The id of the generic ``Agent`` named *name*, and the Agent when it is
    minted here (``None`` when *exporter* already holds one). The id carries
    the name (``Agent-<name>-1``), so it depends on neither the order the
    elements are built in nor on the Agents around it: one IRI never names two
    people in two versions of an SBOM."""
    key = agent_key(spdx3.Agent, name, None)
    spdx_id = exporter.find_agent(key)
    if spdx_id is not None:
        return spdx_id, None
    creation_info, doc_name, doc_uuid = doc
    agent = spdx3.Agent(
        spdxId=generate_spdx_id(f"Agent-{name}", doc_name=doc_name, doc_uuid=doc_uuid),
        name=name,
        creationInfo=creation_info,
    )
    exporter.add_agent(agent, key=key)
    return require_spdx_id(agent), agent
