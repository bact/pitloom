# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Extractor for dataset metadata from Croissant JSON-LD files or URLs.

Croissant is a JSON-LD metadata format for machine learning datasets,
adopted by Hugging Face, Kaggle, and OpenML.
See https://docs.mlcommons.org/croissant/ for the specification.

Requires the ``mlcroissant`` package:

    pip install loom[croissant]
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CroissantDatasetMetadata:
    """Metadata extracted from a Croissant JSON-LD document.

    Fields align with the Croissant spec (https://docs.mlcommons.org/croissant/)
    and the SPDX 3.0 Dataset profile where applicable.
    See https://spdx.github.io/spdx-spec/v3.0.1/model/Dataset/Classes/DatasetPackage/
    """

    # Core identification
    name: str | None = None
    description: str | None = None
    url: str | None = None
    version: str | None = None

    # License: list of SPDX identifiers or URLs
    license: list[str] = field(default_factory=list)

    # Keywords/topics
    keywords: list[str] = field(default_factory=list)

    # Languages
    in_language: list[str] = field(default_factory=list)

    # Dates (ISO-8601 strings)
    date_published: str | None = None
    date_created: str | None = None
    date_modified: str | None = None

    # Citation
    cite_as: str | None = None

    # Creator/publisher names (plain strings)
    creators: list[str] = field(default_factory=list)
    publishers: list[str] = field(default_factory=list)

    # Responsible AI (RAI) fields from the Croissant RAI spec
    # https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html
    data_collection: str | None = None
    data_collection_type: list[str] = field(default_factory=list)
    data_preprocessing_protocol: list[str] = field(default_factory=list)
    data_annotation_protocol: list[str] = field(default_factory=list)
    data_biases: list[str] = field(default_factory=list)
    data_use_cases: list[str] = field(default_factory=list)
    data_limitations: list[str] = field(default_factory=list)
    data_social_impact: str | None = None
    personal_sensitive_information: list[str] = field(default_factory=list)

    # Provenance: field name -> source description
    provenance: dict[str, str] = field(default_factory=dict)


def extract_croissant_metadata(
    source: str | Path | dict[str, Any],
) -> CroissantDatasetMetadata:
    """Extract dataset metadata from a Croissant JSON-LD source.

    The source can be:
    - A URL string pointing to a Croissant JSON-LD document
    - A local file path (``str`` or ``pathlib.Path``)
    - A pre-parsed ``dict`` (the JSON-LD object)

    Args:
        source: URL, file path, or JSON-LD dict of a Croissant document.

    Returns:
        CroissantDatasetMetadata populated with available fields.

    Raises:
        ImportError: If the ``mlcroissant`` package is not installed.
        FileNotFoundError: If a file path is given and the file does not exist.
        ValueError: If the source cannot be parsed as a valid Croissant document.
    """
    try:
        import mlcroissant as mlc
    except ImportError as exc:
        raise ImportError(
            "The 'mlcroissant' package is required to extract Croissant metadata. "
            "Install it with: pip install 'loom[croissant]'"
        ) from exc

    if isinstance(source, Path):
        if not source.exists():
            raise FileNotFoundError(f"Croissant file not found: {source}")
        source_label = str(source)
    elif isinstance(source, str) and not source.startswith(("{", "[")):
        # Treat as a URL or file path string
        path = Path(source)
        if path.exists():
            source_label = source
        else:
            source_label = source  # URL
    else:
        source_label = "<dict>"

    try:
        dataset = mlc.Dataset(jsonld=source)
    except mlc.ValidationError as exc:
        raise ValueError(
            f"Invalid Croissant document from {source_label!r}: {exc}"
        ) from exc
    except Exception as exc:
        raise ValueError(
            f"Failed to load Croissant document from {source_label!r}: {exc}"
        ) from exc

    return _map_metadata(dataset.metadata, source_label)


def load_croissant_from_url(url: str) -> dict[str, Any]:
    """Fetch a Croissant JSON-LD document from a URL.

    This helper performs a simple HTTP GET and returns the parsed JSON.
    It does not validate the document; pass the result to
    :func:`extract_croissant_metadata` for full parsing.

    Args:
        url: The URL of the Croissant JSON-LD document. Must use the
            ``http`` or ``https`` scheme.

    Returns:
        dict[str, Any]: The parsed JSON-LD object.

    Raises:
        ValueError: If the URL scheme is not ``http`` or ``https``, if the
            request fails, or if the response is not valid JSON.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme {parsed.scheme!r} is not allowed. "
            "Only 'http' and 'https' are supported."
        )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "loom-sbom/0.1 (https://github.com/bact/loom)"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except OSError as exc:
        raise ValueError(
            f"Failed to fetch Croissant document from {url!r}: {exc}"
        ) from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response from {url!r} is not valid JSON: {exc}") from exc


def _map_metadata(metadata: Any, source_label: str) -> CroissantDatasetMetadata:
    """Map a mlcroissant Metadata object to CroissantDatasetMetadata.

    Args:
        metadata: The mlcroissant Metadata instance.
        source_label: A human-readable label for provenance tracking.

    Returns:
        CroissantDatasetMetadata with fields populated from the source.
    """
    src = f"Source: {source_label} | Format: Croissant"
    provenance: dict[str, str] = {}

    # --- name ---
    name: str | None = None
    raw_name = getattr(metadata, "name", None)
    if raw_name:
        name = raw_name if isinstance(raw_name, str) else str(raw_name)
        provenance["name"] = f"{src} | Field: name"

    # --- description ---
    description: str | None = None
    raw_desc = getattr(metadata, "description", None)
    if raw_desc:
        description = (
            raw_desc
            if isinstance(raw_desc, str)
            else next(iter(raw_desc.values()), None)
        )
        if description:
            provenance["description"] = f"{src} | Field: description"

    # --- url ---
    url: str | None = getattr(metadata, "url", None)
    if url:
        provenance["url"] = f"{src} | Field: url"

    # --- version ---
    version: str | None = getattr(metadata, "version", None)
    if version:
        provenance["version"] = f"{src} | Field: version"

    # --- license ---
    license_list: list[str] = []
    raw_license = getattr(metadata, "license", None)
    if raw_license:
        for item in raw_license:
            if isinstance(item, str):
                license_list.append(item)
            elif hasattr(item, "url") and item.url:
                license_list.append(str(item.url))
            else:
                license_list.append(str(item))
        if license_list:
            provenance["license"] = f"{src} | Field: license"

    # --- keywords ---
    keywords: list[str] = list(getattr(metadata, "keywords", None) or [])
    if keywords:
        provenance["keywords"] = f"{src} | Field: keywords"

    # --- in_language ---
    in_language: list[str] = list(getattr(metadata, "in_language", None) or [])
    if in_language:
        provenance["in_language"] = f"{src} | Field: inLanguage"

    # --- dates ---
    date_published: str | None = None
    raw_dp = getattr(metadata, "date_published", None)
    if raw_dp:
        date_published = str(raw_dp.date()) if hasattr(raw_dp, "date") else str(raw_dp)
        provenance["date_published"] = f"{src} | Field: datePublished"

    date_created: str | None = None
    raw_dc = getattr(metadata, "date_created", None)
    if raw_dc:
        date_created = str(raw_dc.date()) if hasattr(raw_dc, "date") else str(raw_dc)
        provenance["date_created"] = f"{src} | Field: dateCreated"

    date_modified: str | None = None
    raw_dm = getattr(metadata, "date_modified", None)
    if raw_dm:
        date_modified = str(raw_dm.date()) if hasattr(raw_dm, "date") else str(raw_dm)
        provenance["date_modified"] = f"{src} | Field: dateModified"

    # --- citation ---
    cite_as: str | None = getattr(metadata, "cite_as", None)
    if cite_as:
        provenance["cite_as"] = f"{src} | Field: citeAs"

    # --- creators ---
    creators: list[str] = _extract_agent_names(getattr(metadata, "creators", None))
    if creators:
        provenance["creators"] = f"{src} | Field: creator"

    # --- publishers ---
    publishers: list[str] = _extract_agent_names(getattr(metadata, "publisher", None))
    if publishers:
        provenance["publishers"] = f"{src} | Field: publisher"

    # --- RAI fields ---
    data_collection: str | None = getattr(metadata, "data_collection", None)
    if data_collection:
        provenance["data_collection"] = f"{src} | Field: rai:dataCollection"

    data_collection_type: list[str] = list(
        getattr(metadata, "data_collection_type", None) or []
    )
    if data_collection_type:
        provenance["data_collection_type"] = f"{src} | Field: rai:dataCollectionType"

    data_preprocessing_protocol: list[str] = list(
        getattr(metadata, "data_preprocessing_protocol", None) or []
    )
    if data_preprocessing_protocol:
        provenance["data_preprocessing_protocol"] = (
            f"{src} | Field: rai:dataPreprocessingProtocol"
        )

    data_annotation_protocol: list[str] = list(
        getattr(metadata, "data_annotation_protocol", None) or []
    )
    if data_annotation_protocol:
        provenance["data_annotation_protocol"] = (
            f"{src} | Field: rai:dataAnnotationProtocol"
        )

    data_biases: list[str] = list(getattr(metadata, "data_biases", None) or [])
    if data_biases:
        provenance["data_biases"] = f"{src} | Field: rai:dataBiases"

    data_use_cases: list[str] = list(getattr(metadata, "data_use_cases", None) or [])
    if data_use_cases:
        provenance["data_use_cases"] = f"{src} | Field: rai:dataUseCases"

    data_limitations: list[str] = list(
        getattr(metadata, "data_limitations", None) or []
    )
    if data_limitations:
        provenance["data_limitations"] = f"{src} | Field: rai:dataLimitations"

    data_social_impact: str | None = getattr(metadata, "data_social_impact", None)
    if data_social_impact:
        provenance["data_social_impact"] = f"{src} | Field: rai:dataSocialImpact"

    personal_sensitive_information: list[str] = list(
        getattr(metadata, "personal_sensitive_information", None) or []
    )
    if personal_sensitive_information:
        provenance["personal_sensitive_information"] = (
            f"{src} | Field: rai:personalSensitiveInformation"
        )

    return CroissantDatasetMetadata(
        name=name,
        description=description,
        url=url,
        version=version,
        license=license_list,
        keywords=keywords,
        in_language=in_language,
        date_published=date_published,
        date_created=date_created,
        date_modified=date_modified,
        cite_as=cite_as,
        creators=creators,
        publishers=publishers,
        data_collection=data_collection,
        data_collection_type=data_collection_type,
        data_preprocessing_protocol=data_preprocessing_protocol,
        data_annotation_protocol=data_annotation_protocol,
        data_biases=data_biases,
        data_use_cases=data_use_cases,
        data_limitations=data_limitations,
        data_social_impact=data_social_impact,
        personal_sensitive_information=personal_sensitive_information,
        provenance=provenance,
    )


def _extract_agent_names(agents: Any) -> list[str]:
    """Convert a list of mlcroissant Organization/Person objects to name strings.

    Args:
        agents: A list of mlcroissant agent objects, or None.

    Returns:
        list[str]: List of agent name strings.
    """
    if not agents:
        return []
    names: list[str] = []
    for agent in agents:
        name = getattr(agent, "name", None)
        if name:
            names.append(str(name))
    return names


def enrich_dataset_package(
    dataset_pkg: Any,
    croissant_meta: CroissantDatasetMetadata,
) -> None:
    """Enrich a spdx3.dataset_DatasetPackage with Croissant metadata.

    Maps Croissant fields to SPDX 3.0 Dataset profile fields in-place.

    Args:
        dataset_pkg: The ``spdx_python_model.v3_0_1.dataset_DatasetPackage``
            instance to enrich.
        croissant_meta: The extracted Croissant metadata.
    """
    # Populate description if not already set
    if croissant_meta.description and not getattr(dataset_pkg, "description", None):
        dataset_pkg.description = croissant_meta.description

    # Populate download location / home page
    if croissant_meta.url:
        if not getattr(dataset_pkg, "software_downloadLocation", None):
            dataset_pkg.software_downloadLocation = croissant_meta.url
        if not getattr(dataset_pkg, "software_homePage", None):
            dataset_pkg.software_homePage = croissant_meta.url

    # Populate version
    if croissant_meta.version and not getattr(
        dataset_pkg, "software_packageVersion", None
    ):
        dataset_pkg.software_packageVersion = croissant_meta.version

    # Populate SPDX dataset-profile fields
    if croissant_meta.data_collection:
        dataset_pkg.dataset_dataCollectionProcess = croissant_meta.data_collection

    if croissant_meta.data_preprocessing_protocol:
        dataset_pkg.dataset_dataPreprocessing = (
            croissant_meta.data_preprocessing_protocol
        )

    if croissant_meta.data_biases:
        dataset_pkg.dataset_knownBias = croissant_meta.data_biases

    if croissant_meta.data_use_cases:
        dataset_pkg.dataset_intendedUse = "; ".join(croissant_meta.data_use_cases)

    # Build provenance comment
    prov_parts: list[str] = []
    for field_name, source in croissant_meta.provenance.items():
        prov_parts.append(f"{field_name}: {source}")

    if prov_parts:
        existing_comment: str | None = getattr(dataset_pkg, "comment", None)
        croissant_comment = "Croissant metadata provenance: " + "; ".join(prov_parts)
        if existing_comment:
            dataset_pkg.comment = f"{existing_comment}; {croissant_comment}"
        else:
            dataset_pkg.comment = croissant_comment
