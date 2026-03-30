# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Croissant JSON-LD key alias tables.

Croissant files use different prefix styles in practice:
- bare keys when ``@vocab`` is ``"https://schema.org/"`` (Hugging Face style)
- ``sc:``/``schema:`` prefixes in Croissant spec examples
- ``rai:``/``cr:`` prefixes for RAI and Croissant-specific fields

The alias tuples below enumerate the variants for each semantic field,
ordered most-common first.  The :func:`~pitloom.extract._extract_utils.get_first`
helper picks the first matching key found in a given document dict.

We deliberately do not resolve ``@context`` prefix declarations — alias-based
lookup covers the overwhelming majority of real-world files without requiring
a JSON-LD processor.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# schema.org field aliases
# ---------------------------------------------------------------------------

NAME_KEYS = ("name", "sc:name", "schema:name")
DESCRIPTION_KEYS = ("description", "sc:description", "schema:description")
VERSION_KEYS = ("version", "sc:version", "schema:version")
LICENSE_KEYS = ("license", "sc:license", "schema:license")
URL_KEYS = ("url", "sc:url", "schema:url")
KEYWORDS_KEYS = ("keywords", "sc:keywords", "schema:keywords")
CREATOR_KEYS = ("creator", "sc:creator", "schema:creator")

# ---------------------------------------------------------------------------
# RAI extension field aliases
# ---------------------------------------------------------------------------

RAI_COLLECTION_KEYS = ("rai:dataCollection", "rai:DataCollection")
RAI_BIASES_KEYS = ("rai:dataBiases", "rai:DataBiases")
RAI_PREPROCESSING_KEYS = (
    "rai:dataPreprocessingStrategies",
    "rai:DataPreprocessingStrategies",
)
RAI_SENSITIVITY_KEYS = (
    "rai:personalSensitiveInformation",
    "rai:PersonalSensitiveInformation",
)
RAI_ANONYMIZATION_KEYS = (
    "rai:anonymizationMethodUsed",
    "rai:AnonymizationMethodUsed",
)
RAI_INTENDED_USE_KEYS = ("rai:intendedUse", "rai:IntendedUse")

# ---------------------------------------------------------------------------
# Croissant structure field aliases
# ---------------------------------------------------------------------------

RECORD_SET_KEYS = ("cr:recordSet", "recordSet", "ml:RecordSet")
TOTAL_ITEMS_KEYS = ("cr:totalItems", "totalItems", "schema:totalItems")
DATA_TYPE_KEYS = ("sc:dataType", "dataType", "schema:dataType", "cr:dataType")

# ---------------------------------------------------------------------------
# schema.org type IRI → SPDX dataset_DatasetType enum name
# ---------------------------------------------------------------------------

SCHEMA_TYPE_TO_DATASET_TYPE: dict[str, str] = {
    # Text / NLP
    "sc:Text": "text",
    "schema:Text": "text",
    "https://schema.org/Text": "text",
    # Images
    "sc:ImageObject": "image",
    "schema:ImageObject": "image",
    "https://schema.org/ImageObject": "image",
    # Audio
    "sc:AudioObject": "audio",
    "schema:AudioObject": "audio",
    "https://schema.org/AudioObject": "audio",
    # Numeric
    "sc:Number": "numeric",
    "sc:Float": "numeric",
    "sc:Integer": "numeric",
    "schema:Number": "numeric",
    "schema:Float": "numeric",
    "schema:Integer": "numeric",
    "https://schema.org/Number": "numeric",
    "https://schema.org/Float": "numeric",
    "https://schema.org/Integer": "numeric",
    # Timestamps / dates
    "sc:Date": "timestamp",
    "sc:DateTime": "timestamp",
    "schema:Date": "timestamp",
    "schema:DateTime": "timestamp",
    "https://schema.org/Date": "timestamp",
    "https://schema.org/DateTime": "timestamp",
    # Video
    "sc:VideoObject": "video",
    "schema:VideoObject": "video",
    "https://schema.org/VideoObject": "video",
}
