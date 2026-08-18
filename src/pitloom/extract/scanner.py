# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Heuristic scanner for AI model files and their usage in Python codebase.

Provides discovery capabilities for extracting model metadata and identifying
relationships between source files and model files without requiring manual
configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata
from pitloom.core.project import ProjectFile
from pitloom.extract.ai_model import detect_ai_model_format, read_ai_model

log = logging.getLogger(__name__)

# Extensions that might genuinely be AI models.
_ALLOWED_EXTS = {".zip", ".bin"}
for _fmt in AiModelFormat.__members__.values():
    # mypy may complain if not checking hasattr, but extensions is defined.
    for _ext in _fmt.extensions:
        _ALLOWED_EXTS.add(_ext.lower())


def _scan_single_file_for_model(
    pf: ProjectFile, project_dir: Path
) -> AiModelMetadata | None:
    """Detect and extract metadata from a potential AI model file."""
    phys_path = project_dir / pf.physical_path
    suffix = phys_path.suffix.lower()
    if suffix not in _ALLOWED_EXTS:
        return None

    fmt = detect_ai_model_format(phys_path)
    if fmt == AiModelFormat.UNKNOWN:
        return None

    try:
        meta = read_ai_model(phys_path)
        meta.format_info.file_name = phys_path.name
        meta.format_info.file_path_relative = pf.distribution_path
        meta.format_info.physical_path = pf.physical_path
        log.debug("Discovered AI model: %s (format: %s)", pf.distribution_path, fmt)
        return meta
    except ImportError as e:
        log.warning(
            "FORMAT=%s FILE=%s: required library not installed; %s",
            fmt,
            phys_path,
            e,
        )
    # pylint: disable=broad-exception-caught
    except Exception as e:
        log.warning(
            "FORMAT=%s FILE=%s: failed to extract metadata; %s",
            fmt,
            phys_path,
            e,
        )
    return None


def _scan_python_file_usages(
    pf: ProjectFile, project_dir: Path, ai_models: list[AiModelMetadata]
) -> None:
    """Scan a Python file for string references to discovered AI models."""
    if not pf.distribution_path.endswith(".py"):
        return
    phys_path = project_dir / pf.physical_path
    try:
        content = phys_path.read_text(encoding="utf-8")
        for meta in ai_models:
            file_name = meta.format_info.file_name
            if file_name and file_name in content:
                meta.usage_files.append(pf.distribution_path)
                log.debug(
                    "Found usage of %s inside %s",
                    file_name,
                    pf.distribution_path,
                )
    # pylint: disable=broad-exception-caught
    except Exception as e:
        log.warning("Could not read text from %s for usage scanning: %s", phys_path, e)


def scan_project_for_ai_models(
    project_dir: Path, files: list[ProjectFile]
) -> list[AiModelMetadata]:
    """Scan project files for AI models and detect their usages in scripts."""
    ai_models: list[AiModelMetadata] = []

    for pf in files:
        meta = _scan_single_file_for_model(pf, project_dir)
        if meta is not None:
            ai_models.append(meta)

    for pf in files:
        _scan_python_file_usages(pf, project_dir, ai_models)

    return ai_models
