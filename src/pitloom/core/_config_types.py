# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Type definitions and data structures for Pitloom configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

from pitloom.core.content_type_config import ContentTypeConfig, ContentTypeOverride
from pitloom.core.creation import CreationMetadata, Creator, Tool
from pitloom.core.enrich_config import EnrichConfig
from pitloom.core.provenance import ProvenanceConfig

_DEFAULT_PROVENANCE_SCHEMA = "pitloom/1"
VALID_CONTENT_TYPE_METHODS: frozenset[str] = frozenset({"auto", "magika", "extension"})


@dataclass
# pylint: disable=too-many-instance-attributes
class PitloomConfig:
    """Settings from the ``[tool.pitloom]`` section of ``pyproject.toml``.

    All fields have safe defaults so that a project without a ``[tool.pitloom]``
    section works out of the box.  Adding new ``[tool.pitloom]`` options in
    future versions only requires adding a new field here with a default value.
    """

    fragments: list[str] = field(default_factory=list)
    pretty: bool = False
    describe_relationship: bool | None = None
    sbom_basename: str | None = None
    creators: list[Creator] = field(default_factory=list)
    tools: list[Tool] | None = None
    creation_datetime: str | None = None
    creation_comment: str | None = None
    ids_file: str | None = None
    update_registry: bool = True
    provenance_format: str = "both"
    provenance_schema: str = _DEFAULT_PROVENANCE_SCHEMA
    provenance_detail: str = "minimal"
    provenance_preserve_source_metadata: str = "auto"
    enrich_local: bool = False
    extract_file_header: bool = True
    content_type_enabled: bool = False
    content_type_method: str = "auto"
    content_type_overrides: tuple[ContentTypeOverride, ...] = ()
    offline: bool = False

    @property
    def provenance(self) -> ProvenanceConfig:
        """Return ProvenanceConfig constructed from current config settings."""
        return ProvenanceConfig(
            format=self.provenance_format,
            schema=self.provenance_schema,
            detail=self.provenance_detail,
            preserve_source_metadata=self.provenance_preserve_source_metadata,
        )

    @property
    def content_type(self) -> ContentTypeConfig:
        """Return ContentTypeConfig constructed from current config settings."""
        return ContentTypeConfig(
            enabled=self.content_type_enabled,
            method=self.content_type_method,
            overrides=self.content_type_overrides,
        )

    @property
    def enrich(self) -> EnrichConfig:
        """Return EnrichConfig constructed from current config settings."""
        return EnrichConfig(local=self.enrich_local)

    @property
    def creation_metadata(self) -> CreationMetadata:
        """Return CreationMetadata constructed from current config settings."""
        return CreationMetadata(
            creators=self.creators,
            tools=self.tools,
            creation_datetime=self.creation_datetime,
            creation_comment=self.creation_comment,
        )
