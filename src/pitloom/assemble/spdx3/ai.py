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

# Valid SPDX 3 ai_safetyRiskAssessmentType enum values (lowercase).
_SAFETY_RISK_VALUES = {"high", "medium", "low", "serious"}


def _build_ai_package(
    ai_model: AiModelMetadata,
    creation_info: spdx3.CreationInfo,
    doc_name: str,
    doc_uuid: str,
) -> spdx3.ai_AIPackage:
    """Build an ``ai_AIPackage`` SPDX 3 element from an :class:`AiModelMetadata`.

    Field mapping:

    **Core identification**

    - ``name`` → ``name`` (falls back to ``format_info.model_format`` string)
    - ``version`` → ``software_packageVersion``
    - ``description`` → ``description``

    **Technical model metadata**

    - ``type_of_model`` and/or ``architecture`` → ``ai_typeOfModel`` (list)
    - ``quantization`` → ``ai_hyperparameter`` (key="quantization")
    - ``hyperparameters`` → ``ai_hyperparameter`` (list of DictionaryEntry)
    - ``inputs`` / ``outputs`` → ``ai_informationAboutApplication`` (JSON)

    **Use-case and safety** (from ``usage`` sub-object)

    - ``usage.domains`` → ``ai_domain``
    - ``usage.limitations`` → ``ai_limitation`` (joined with "; ")
    - ``usage.safety_risk_assessment`` → ``ai_safetyRiskAssessment``
      (enum: high | medium | low | serious)
    - ``usage.intended_use`` + ``usage.unintended_use``
      → merged into ``ai_informationAboutApplication`` JSON
    - ``usage.known_biases`` → appended to ``comment``

    **Provenance**

    - ``provenance`` → ``comment``

    Args:
        ai_model: Extracted AI model metadata.
        creation_info: The shared CreationInfo node.
        doc_name: The parent document/package name (for deterministic spdxId).
        doc_uuid: The document UUID (for deterministic spdxId).

    Returns:
        A populated :class:`spdx3.ai_AIPackage` instance.
    """
    pkg_name = ai_model.name or str(ai_model.format_info.model_format)
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

    # ai_typeOfModel: collect both the general type and the specific architecture.
    type_of_model_values: list[str] = []
    if ai_model.type_of_model:
        type_of_model_values.append(ai_model.type_of_model)
    if ai_model.architecture:
        type_of_model_values.append(ai_model.architecture)
    if type_of_model_values:
        ai_pkg.ai_typeOfModel = type_of_model_values

    # ai_hyperparameter: quantization first (if present), then training hyperparams.
    hyperparameter_entries: list[spdx3.DictionaryEntry] = []
    if ai_model.quantization:
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key="quantization", value=ai_model.quantization)
        )
    for key, val in ai_model.hyperparameters.items():
        hyperparameter_entries.append(
            spdx3.DictionaryEntry(key=str(key), value=str(val))
        )
    if hyperparameter_entries:
        ai_pkg.ai_hyperparameter = hyperparameter_entries

    # ai_domain: directly from usage.domains (List[String]).
    if ai_model.usage.domains:
        ai_pkg.ai_domain = list(ai_model.usage.domains)

    # ai_limitation: SPDX 3 field is a single String; join list with "; ".
    if ai_model.usage.limitations:
        ai_pkg.ai_limitation = "; ".join(ai_model.usage.limitations)

    # ai_safetyRiskAssessment: enum (high | medium | low | serious).
    if ai_model.usage.safety_risk_assessment:
        risk_val = ai_model.usage.safety_risk_assessment.lower()
        if risk_val in _SAFETY_RISK_VALUES:
            ai_pkg.ai_safetyRiskAssessment = getattr(
                spdx3.ai_SafetyRiskAssessmentType, risk_val, None
            )

    # ai_informationAboutApplication: JSON dict combining I/O specs and use-case info.
    io_parts: dict[str, Any] = {}
    if ai_model.inputs:
        io_parts["inputs"] = ai_model.inputs
    if ai_model.outputs:
        io_parts["outputs"] = ai_model.outputs
    if ai_model.usage.intended_use:
        io_parts["intended_use"] = ai_model.usage.intended_use
    if ai_model.usage.unintended_use:
        io_parts["unintended_use"] = ai_model.usage.unintended_use
    if io_parts:
        ai_pkg.ai_informationAboutApplication = json.dumps(io_parts, ensure_ascii=False)

    # comment: provenance + known_biases.
    comment_parts: list[str] = []
    if ai_model.provenance:
        prov_str = "; ".join(
            f"{field}: {src}" for field, src in ai_model.provenance.items()
        )
        comment_parts.append(f"Metadata provenance: {prov_str}")
    if ai_model.usage.known_biases:
        biases_str = "; ".join(ai_model.usage.known_biases)
        comment_parts.append(f"Known biases: {biases_str}")
    if comment_parts:
        ai_pkg.comment = "\n".join(comment_parts)

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
    - ``type_of_model`` and ``architecture`` are both stored in
      ``ai_typeOfModel``.
    - ``quantization`` and hyperparameters are stored as ``ai_hyperparameter``
      DictionaryEntry list (quantization first).
    - ``usage.domains`` → ``ai_domain``.
    - ``usage.limitations`` → ``ai_limitation`` (joined string).
    - ``usage.safety_risk_assessment`` → ``ai_safetyRiskAssessment`` enum.
    - ``usage.intended_use`` / ``usage.unintended_use`` → merged into
      ``ai_informationAboutApplication`` JSON alongside I/O specs.
    - ``usage.known_biases`` and provenance → SPDX ``comment``.

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
