# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""AI model package and relationship creation for SPDX 3 SBOM documents."""

from __future__ import annotations

import json
from typing import Any

from spdx_python_model import v3_0_1 as spdx3

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.models import generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter


def _build_ai_package(
    ai_model: AiModelMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.ai_AIPackage:
    """Build an ``ai_AIPackage`` SPDX 3 element from an :class:`AiModelMetadata`.

    Maps available fields as follows:

    - ``name`` → ``name`` (falls back to the format value string)
    - ``version`` → ``software_packageVersion``
    - ``description`` → ``description``
    - ``type_of_model`` → ``ai_typeOfModel``
    - ``hyperparameters`` → ``ai_hyperparameter`` (list of DictionaryEntry)
    - ``inputs`` / ``outputs`` → ``ai_informationAboutApplication`` (JSON string)
    - ``provenance`` → ``comment``

    Args:
        ai_model: Extracted AI model metadata.
        creation_info: The shared CreationInfo node.
        doc_name: The parent document/package name (for deterministic spdxId).
        doc_uuid: The document UUID (for deterministic spdxId).

    Returns:
        A populated :class:`spdx3.ai_AIPackage` instance.
    """
    pkg_name = ai_model.name or str(ai_model.format)
    ai_pkg = spdx3.ai_AIPackage(
        spdxId=generate_spdx_id(
            f"AIPackage-{pkg_name}", doc_name=doc_name, doc_uuid=doc_uuid
        ),
        name=pkg_name,
        creationInfo=creation_info,
    )

    if ai_model.version:
        ai_pkg.software_packageVersion = ai_model.version

    if ai_model.description:
        ai_pkg.description = ai_model.description

    if ai_model.type_of_model:
        ai_pkg.ai_typeOfModel = [ai_model.type_of_model]

    # Hyperparameters → ai_hyperparameter (list of DictionaryEntry)
    if ai_model.hyperparameters:
        entries: list[spdx3.DictionaryEntry] = []
        for key, val in ai_model.hyperparameters.items():
            entry = spdx3.DictionaryEntry(key=str(key), value=str(val))
            entries.append(entry)
        ai_pkg.ai_hyperparameter = entries

    # Inputs / outputs → ai_informationAboutApplication as JSON string.
    io_parts: dict[str, Any] = {}
    if ai_model.inputs:
        io_parts["inputs"] = ai_model.inputs
    if ai_model.outputs:
        io_parts["outputs"] = ai_model.outputs
    if io_parts:
        ai_pkg.ai_informationAboutApplication = json.dumps(io_parts, ensure_ascii=False)

    # Provenance → comment.
    if ai_model.provenance:
        parts = [f"{field}: {src}" for field, src in ai_model.provenance.items()]
        ai_pkg.comment = "Metadata provenance: " + "; ".join(parts)

    return ai_pkg


def add_ai_models(
    ai_models: list[AiModelMetadata],
    main_package_spdx_id: str,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
    exporter: Spdx3JsonExporter,
) -> None:
    """Build ``ai_AIPackage`` and ``contains`` relationship elements for each
    AI model and add them to the exporter.

    For each entry in ``ai_models``:

    - An ``ai_AIPackage`` element is built from the extracted metadata.
    - A ``contains`` relationship links the main Python package to the AI model.
    - Hyperparameters are stored as ``ai_hyperparameter`` DictionaryEntry list.
    - Inputs and outputs are serialised as a JSON string in
      ``ai_informationAboutApplication``.
    - Provenance is recorded in the SPDX ``comment`` attribute.

    The caller is responsible for appending
    ``ProfileIdentifierType.ai`` to the document's ``profileConformance``
    when at least one AI model is present.

    Args:
        ai_models: List of extracted :class:`~pitloom.core.ai_metadata.AiModelMetadata`.
        main_package_spdx_id: SPDX ID of the parent Python package.
        creation_info: Shared ``CreationInfo`` for all new elements.
        doc_name: Document name (project name) for SPDX ID generation.
        doc_uuid: Document-scoped UUID used in SPDX ID generation.
        exporter: Receives the new package and relationship elements.
    """
    for ai_model in ai_models:
        ai_pkg = _build_ai_package(ai_model, creation_info, doc_name, doc_uuid)
        exporter.add_package(ai_pkg)

        rel = spdx3.Relationship(
            spdxId=generate_spdx_id(
                f"Relationship-contains-{ai_pkg.name}",
                doc_name=doc_name,
                doc_uuid=doc_uuid,
            ),
            from_=main_package_spdx_id,
            to=[ai_pkg.spdxId],
            relationshipType=spdx3.RelationshipType.contains,
            creationInfo=creation_info,
        )
        exporter.add_relationship(rel)
