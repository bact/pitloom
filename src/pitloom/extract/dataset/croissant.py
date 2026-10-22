# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Croissant JSON-LD dataset metadata extractor.

Parses metadata from Croissant-formatted JSON-LD documents (local files or
URLs) and returns a :class:`~pitloom.core.dataset_metadata.DatasetMetadata`.

Croissant is a JSON-LD extension of ``schema.org/Dataset`` adopted by
Hugging Face, Kaggle, and OpenML.
See: https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html
See: https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html

This module is stdlib-only -- no third-party packages are required.
To work with Croissant RDF as Python dataclass,
we can use https://github.com/mlcommons/croissant/tree/main/python/mlcroissant

Key alias tables live in :mod:`pitloom.extract.dataset.croissant_key`.
Generic I/O and string utilities live in :mod:`pitloom.extract._extract_utils`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.untrusted_text import escape_lone_surrogates_in
from pitloom.extract._extract_utils import fetch_json, get_first, quote_source
from pitloom.extract.dataset.croissant_key import (
    CREATOR_KEYS,
    DATA_TYPE_KEYS,
    DESCRIPTION_KEYS,
    KEYWORDS_KEYS,
    LICENSE_KEYS,
    NAME_KEYS,
    RAI_BIASES_KEYS,
    RAI_COLLECTION_KEYS,
    RAI_PREPROCESSING_KEYS,
    RAI_SENSITIVITY_KEYS,
    RECORD_SET_KEYS,
    SCHEMA_TYPE_TO_DATASET_TYPE,
    TOTAL_ITEMS_KEYS,
    URL_KEYS,
    VERSION_KEYS,
)
from pitloom.extract.dataset.licence import (
    DatasetLicence,
    apply_dataset_licence,
    dataset_licence,
)
from pitloom.extract.dataset.values import (
    stated_count,
    stated_name,
    stated_text,
    stated_texts,
    stated_total,
    stated_url,
    stated_version,
    text_of,
)
from pitloom.logging_config import (
    LONE_SURROGATES_WARNING,
    Cap,
    loggable,
    one_line,
)

log = logging.getLogger(__name__)

#: Most levels of arrays and objects a Croissant file may nest: real files
#: nest about ten. Checked before parsing, so a file is read or refused the
#: same on every Python version.
CROISSANT_MAX_NESTING = 64

CROISSANT_NESTING_CAP = Cap(CROISSANT_MAX_NESTING, "level", "Croissant-nesting")


def _extract_creator_name(value: Any, source: str = "Croissant") -> str | None:
    """A plain name from a ``schema:creator`` value: a ``Person`` or
    ``Organization`` node's ``name``, the first of a list, or a string
    (:func:`~pitloom.extract.dataset.values.stated_name`)."""
    return stated_name(value, source, "creator")


def _normalize_sensitivity(value: Any, source: str = "Croissant") -> str | None:
    """Map a RAI sensitivity value (text, a boolean, ``0`` or ``1``) to
    ``"yes"``, ``"no"``, or ``"noAssertion"`` (other text).

    Returns ``None`` when *value* is ``None`` or blank, and, with one
    ``WARNING:``, when it is of another type.
    """
    if isinstance(value, bool) or (isinstance(value, int) and value in (0, 1)):
        value = str(value)
    s = stated_text(value, source, "rai:personalSensitiveInformation")
    if s is None:
        return None
    s = s.lower()
    if s in ("yes", "true", "1"):
        return "yes"
    if s in ("no", "false", "0"):
        return "no"
    return "noAssertion"


def _data_type_values(obj: Any) -> list[Any]:
    """Every ``dataType`` value in *obj*, in document order, a list's items
    one by one. Walked with an explicit stack, so no nesting depth the JSON
    parser accepts can exhaust Python's recursion limit."""
    found: list[Any] = []
    stack: list[Any] = [obj]
    while stack:
        node = stack.pop()
        children: list[Any] = []
        if isinstance(node, dict):
            for key, val in node.items():
                if key in DATA_TYPE_KEYS:
                    found += val if isinstance(val, list) else [val]
                else:
                    children.append(val)
        elif isinstance(node, list):
            children = node
        stack.extend(reversed(children))
    return found


def _collect_data_types(obj: Any, source: str = "Croissant") -> list[str]:
    """All ``dataType`` texts in a nested structure (each item read as
    :func:`~pitloom.extract.dataset.values.stated_texts` reads it: one
    ``WARNING:`` for those of no text)."""
    return stated_texts(_data_type_values(obj), source, "dataType", split=False)


def _infer_dataset_types(data: dict[str, Any], source: str = "Croissant") -> list[str]:
    """Infer ``dataset_types`` by walking all ``dataType`` values in *data*.

    Maps schema.org type references to SPDX ``dataset_DatasetType`` enum name
    strings (e.g. ``"text"``, ``"image"``).  Falls back to ``"other"`` for
    unrecognised types.  Returns a deduplicated list preserving first-seen order.
    """
    raw_types = _collect_data_types(data, source)
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_types:
        mapped = SCHEMA_TYPE_TO_DATASET_TYPE.get(raw, "other")
        if mapped not in seen:
            seen.add(mapped)
            result.append(mapped)
    return result


def _extract_croissant_core_fields(
    data: dict[str, Any], src_label: str, provenance: dict[str, str]
) -> tuple[
    str | None,
    str | None,
    str | None,
    DatasetLicence | None,
    list[str],
    str | None,
]:
    """Extract version, description, download_url, license, keywords, creator."""
    version = stated_version(get_first(data, *VERSION_KEYS), src_label, numbers=True)
    if version:
        provenance["version"] = f"Source: {src_label} | Field: version"

    description = stated_text(
        get_first(data, *DESCRIPTION_KEYS), src_label, "description"
    )
    if description:
        provenance["description"] = f"Source: {src_label} | Field: description"

    download_url = stated_url(get_first(data, *URL_KEYS), src_label, "url")
    if download_url:
        provenance["download_url"] = f"Source: {src_label} | Field: url"

    licence = dataset_licence(
        get_first(data, *LICENSE_KEYS), source=src_label, lister="Croissant file"
    )
    if licence is not None:  # set again, in place, by apply_dataset_licence
        provenance["license"] = licence.provenance

    keywords = stated_texts(get_first(data, *KEYWORDS_KEYS), src_label, "keywords")
    if keywords:
        provenance["keywords"] = f"Source: {src_label} | Field: keywords"

    creator = _extract_creator_name(get_first(data, *CREATOR_KEYS), src_label)
    if creator:
        provenance["creator"] = f"Source: {src_label} | Field: creator"

    return version, description, download_url, licence, keywords, creator


def _extract_croissant_rai_fields(
    data: dict[str, Any], src_label: str, provenance: dict[str, str]
) -> tuple[str | None, list[str], list[str], str | None]:
    """Extract RAI collection, preprocessing, bias, and sensitivity fields."""
    data_collection_process = stated_text(
        get_first(data, *RAI_COLLECTION_KEYS), src_label, "rai:dataCollection"
    )
    if data_collection_process:
        provenance["data_collection_process"] = (
            f"Source: {src_label} | Field: rai:dataCollection"
        )

    data_preprocessing = stated_texts(
        get_first(data, *RAI_PREPROCESSING_KEYS),
        src_label,
        "rai:dataPreprocessingProtocol",
    )
    if data_preprocessing:
        provenance["data_preprocessing"] = (
            f"Source: {src_label} | Field: rai:dataPreprocessingProtocol"
        )

    known_bias = stated_texts(
        get_first(data, *RAI_BIASES_KEYS), src_label, "rai:dataBiases"
    )
    if known_bias:
        provenance["known_bias"] = f"Source: {src_label} | Field: rai:dataBiases"

    has_sensitive = _normalize_sensitivity(
        get_first(data, *RAI_SENSITIVITY_KEYS), src_label
    )
    if has_sensitive is not None:
        provenance["has_sensitive_personal_information"] = (
            f"Source: {src_label} | Field: rai:personalSensitiveInformation"
        )

    return (
        data_collection_process,
        data_preprocessing,
        known_bias,
        has_sensitive,
    )


def _extract_dataset_size(
    data: dict[str, Any], src_label: str, provenance: dict[str, str]
) -> int | None:
    """Extract total record/item count from Croissant document."""
    top_total = stated_count(
        get_first(data, *TOTAL_ITEMS_KEYS), src_label, "cr:totalItems"
    )
    if top_total is not None:
        provenance["dataset_size"] = f"Source: {src_label} | Field: cr:totalItems"
        return top_total

    record_sets_raw = get_first(data, *RECORD_SET_KEYS)
    if isinstance(record_sets_raw, dict):
        record_sets: list[Any] = [record_sets_raw]
    elif isinstance(record_sets_raw, list):
        record_sets = record_sets_raw
    else:
        record_sets = []

    # A record set that is not a table states no count, so no total.
    total = stated_total(
        [
            get_first(rs, *TOTAL_ITEMS_KEYS) if isinstance(rs, dict) else None
            for rs in record_sets
        ],
        src_label,
        "cr:recordSet cr:totalItems",
    )
    if total is not None:
        provenance["dataset_size"] = (
            f"Source: {src_label} | Field: cr:recordSet, cr:totalItems"
        )
    return total


def read_croissant(source: str | Path, *, label: str | None = None) -> DatasetMetadata:
    """Extract metadata from a Croissant JSON-LD document, named *label*
    (default: *source* as given) in its provenance. A lone surrogate (a
    JSON ``\\ud800``) in its text is written as ``\\uXXXX``, with one
    ``WARNING:``.

    Raises:
        ValueError: *source* cannot be read, is not a Croissant document,
            nests over :data:`CROISSANT_MAX_NESTING` levels,
            or reading it fails in any other way; the message names it.
    """
    try:
        data = fetch_json(source, max_nesting=CROISSANT_NESTING_CAP)
    except ValueError as exc:
        message = str(exc)
        for generic, own in (
            ("Source ", "Croissant source "),
            ("Cannot read source ", "Cannot read Croissant source "),
        ):
            if message.startswith(generic):
                message = own + message[len(generic) :]
        raise ValueError(message) from exc
    src_label = str(source) if label is None else label
    try:
        return _metadata(data, source, src_label)
    except ValueError:
        raise
    # A hostile document must fail as the documented ValueError, naming it.
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        raise ValueError(
            f"Croissant source {quote_source(source)} cannot be read: "
            f"{type(exc).__name__}: {one_line(exc)}"
        ) from exc


def _name(data: dict[str, Any], source: str | Path) -> str:
    """The document's ``name``.

    Raises:
        ValueError: it has none, or one that is not text.
    """
    raw = get_first(data, *NAME_KEYS)
    name, holds_text = text_of(raw)
    if not holds_text:
        raise ValueError(
            f"Croissant source {quote_source(source)} field 'name' is of type "
            f"{type(raw).__name__}, not text."
        )
    if name is None:
        raise ValueError(
            f"Croissant source {quote_source(source)} has no 'name' field."
        )
    return name


# pylint: disable-next=too-many-locals
def _metadata(
    data: dict[str, Any], source: str | Path, src_label: str
) -> DatasetMetadata:
    """The :class:`DatasetMetadata` the Croissant *data* read from *source*
    states."""
    name = _name(data, source)
    provenance: dict[str, str] = {"name": f"Source: {src_label} | Field: name"}

    (
        version,
        description,
        download_url,
        licence,
        keywords,
        creator,
    ) = _extract_croissant_core_fields(data, src_label, provenance)

    dataset_types = _infer_dataset_types(data, src_label)
    if dataset_types:
        provenance["dataset_types"] = (
            f"Source: {src_label} | Field: cr:recordSet, sc:dataType"
        )

    (
        data_collection_process,
        data_preprocessing,
        known_bias,
        has_sensitive,
    ) = _extract_croissant_rai_fields(data, src_label, provenance)

    dataset_size = _extract_dataset_size(data, src_label, provenance)

    croissant_url: str | None = None
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        croissant_url = source

    meta = DatasetMetadata(
        name=name,
        version=version,
        description=description,
        download_url=download_url,
        keywords=keywords,
        creator=creator,
        dataset_types=dataset_types,
        dataset_size=dataset_size,
        data_collection_process=data_collection_process,
        data_preprocessing=data_preprocessing,
        known_bias=known_bias,
        intended_use=None,
        has_sensitive_personal_information=has_sensitive,
        anonymization_methods=[],
        croissant_url=croissant_url,
        provenance=provenance,
    )
    apply_dataset_licence(meta, licence)
    if escape_lone_surrogates_in(meta)[1]:
        log.warning(LONE_SURROGATES_WARNING, "", loggable(src_label))
    return meta
