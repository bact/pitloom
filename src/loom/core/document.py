# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Format-neutral document model for assembled SBOM content.

``DocumentModel`` is the format-neutral internal document model that decouples
metadata extraction from output serialization. It holds all captured information
so that any serializer can use what it needs without touching the extractors.

Architecture::

    Extractors → DocumentModel → Serializers / Assemblers
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loom.core.ai_metadata import AiModelMetadata
from loom.core.creation import CreationMetadata
from loom.core.project import ProjectMetadata


@dataclass
class DocumentModel:
    """Format-neutral assembled document ready for serialization.

    Holds everything that *could* appear in any output format. Serializers
    pick the fields they understand and ignore the rest.

    Attributes:
        project: Python project metadata from ``pyproject.toml``.
        creation: Creator and timestamp metadata for the SBOM document.
        ai_models: AI model metadata, one entry per model file processed.
    """

    project: ProjectMetadata
    creation: CreationMetadata = field(default_factory=CreationMetadata)
    ai_models: list[AiModelMetadata] = field(default_factory=list)
