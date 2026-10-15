# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's originators and supplier as SPDX 3 ``originatedBy`` and
``suppliedBy`` Agents.

One helper for every surface that builds an ``ai_AIPackage``
(:func:`pitloom.assemble.spdx3.ai.add_ai_models` and
:func:`pitloom.assemble.spdx3.document.build_model`).

See also: :mod:`pitloom.core.model_originators` (the names a reader keeps).
"""

from __future__ import annotations

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._ai_package import warn_related_name_cut
from pitloom.assemble.spdx3._display_text import MODEL_ORIGINATOR, MODEL_SUPPLIER
from pitloom.core.ai_metadata import AiModelMetadata, cap_model_name
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, agent_key, require_spdx_id

_Doc = tuple[spdx3.CreationInfo, str, str]


def _capped(raw: object) -> tuple[str, bool] | None:
    """*raw* stripped and cut as a model's own name is, and whether it was
    cut; ``None`` for a blank name or one that is not a ``str``."""
    stripped = raw.strip() if isinstance(raw, str) else ""
    if not stripped:
        return None
    name = cap_model_name(stripped)
    return name, name != stripped


def _agent(
    name: str, doc: _Doc, exporter: Spdx3JsonExporter
) -> tuple[str, spdx3.Agent | None]:
    """The id of the generic ``Agent`` named *name*, and the Agent when it
    is minted here (``None`` when *exporter* already holds one)."""
    key = agent_key(spdx3.Agent, name, None)
    spdx_id = exporter.find_agent(key)
    if spdx_id is not None:
        return spdx_id, None
    creation_info, doc_name, doc_uuid = doc
    agent = spdx3.Agent(
        spdxId=generate_spdx_id("Agent", doc_name=doc_name, doc_uuid=doc_uuid),
        name=name,
        creationInfo=creation_info,
    )
    exporter.add_agent(agent, key=key)
    return require_spdx_id(agent), agent


def add_model_originators(
    ai_pkg: spdx3.ai_AIPackage,
    ai_model: AiModelMetadata,
    doc: _Doc,
    exporter: Spdx3JsonExporter,
) -> list[tuple[str, spdx3.Element]]:
    """Set *ai_pkg*'s ``originatedBy`` to one generic ``Agent`` per name in
    *ai_model*'s ``originators``, in source order, then its ``suppliedBy``
    to the Agent of its ``supplier``; return the Agents created, labelled
    for :func:`~pitloom.assemble.spdx3._ai_package.finish_ai_package`.

    *doc* is the creation info, document name and uuid. A name is cut as
    the model's own name is, all cuts said in one ``WARNING:``; a blank name
    or one that is not a ``str`` is skipped. An Agent of the same name
    already in *exporter* (an originator, another model's) is reused, so a
    supplier that is also an originator is one element. Only a source that
    states a supplier (a hub repository owner) gives a ``suppliedBy``.
    """
    created: list[tuple[str, spdx3.Element]] = []
    ids: list[str] = []
    cut: list[str] = []
    for raw in ai_model.originators:
        capped = _capped(raw)
        if capped is None:
            continue
        spdx_id, agent = _agent(capped[0], doc, exporter)
        if agent is not None:
            created.append((MODEL_ORIGINATOR, agent))
        if capped[1] and not cut:
            cut.append(f"{MODEL_ORIGINATOR} name")
        ids.append(spdx_id)
    if ids:
        ai_pkg.originatedBy = list(dict.fromkeys(ids))
    supplier = _capped(ai_model.supplier)
    if supplier is not None:
        spdx_id, agent = _agent(supplier[0], doc, exporter)
        if agent is not None:
            created.append((MODEL_SUPPLIER, agent))
        if supplier[1] and spdx_id not in ids:
            cut.append(f"{MODEL_SUPPLIER} name")
        ai_pkg.suppliedBy = spdx_id
    if cut:
        warn_related_name_cut(", ".join(cut), ai_model)
    return created
