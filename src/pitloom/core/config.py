# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Pitloom tool configuration read from ``[tool.pitloom]`` in ``pyproject.toml``.

See Also:
    :mod:`pitloom.core._config_types` for the ``PitloomConfig`` class definition.
    :mod:`pitloom.core._config_parse` for internal TOML parsing routines.
"""

from __future__ import annotations

from pitloom.core._config_legacy import (
    _MOVED_CREATION_KEYS,
    _MOVED_CREATION_KEYS_LIST_VALID,
    _MOVED_TOP_LEVEL_TABLES,
    _check_moved_creation_keys,
    _check_moved_top_level_tables,
)
from pitloom.core._config_parse import (
    _VALID_PRESERVE_SOURCE_METADATA,
    _VALID_PROVENANCE_DETAIL,
    _VALID_PROVENANCE_FORMATS,
    _read_content_type_overrides,
    _read_content_type_settings,
    _read_creators,
    _read_enrich_settings,
    _read_extract_file_header,
    _read_fragments,
    _read_ids_file,
    _read_offline_setting,
    _read_provenance_settings,
    _read_tools,
    parse_pitloom_config,
    read_pitloom_config,
)
from pitloom.core._config_types import (
    _DEFAULT_PROVENANCE_SCHEMA,
    VALID_CONTENT_TYPE_METHODS,
    PitloomConfig,
)
from pitloom.core.content_type_config import ContentTypeConfig, ContentTypeOverride
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.provenance import ProvenanceConfig

__all__ = [
    "ContentTypeConfig",
    "ContentTypeOverride",
    "CreationMetadata",
    "Creator",
    "EnrichConfig",
    "PitloomConfig",
    "ProvenanceConfig",
    "Tool",
    "VALID_CONTENT_TYPE_METHODS",
    "_DEFAULT_PROVENANCE_SCHEMA",
    "_MOVED_CREATION_KEYS",
    "_MOVED_CREATION_KEYS_LIST_VALID",
    "_MOVED_TOP_LEVEL_TABLES",
    "_VALID_PRESERVE_SOURCE_METADATA",
    "_VALID_PROVENANCE_DETAIL",
    "_VALID_PROVENANCE_FORMATS",
    "_check_moved_creation_keys",
    "_check_moved_top_level_tables",
    "_read_content_type_overrides",
    "_read_content_type_settings",
    "_read_creators",
    "_read_enrich_settings",
    "_read_extract_file_header",
    "_read_fragments",
    "_read_ids_file",
    "_read_offline_setting",
    "_read_provenance_settings",
    "_read_tools",
    "parse_pitloom_config",
    "read_pitloom_config",
]
