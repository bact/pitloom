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
for _fmt in AiModelFormat:
    # mypy may complain if not checking hasattr, but extensions is defined.
    for _ext in _fmt.extensions:
        _ALLOWED_EXTS.add(_ext.lower())


def scan_project_for_ai_models(
    project_dir: Path, files: list[ProjectFile]
) -> list[AiModelMetadata]:
    """Scan project files for AI models and detect their usages in scripts.

    For performance, files are only checked against their magic bytes via
    :func:`~pitloom.extract.ai_model.detect_ai_model_format` if their
    extension matches known formats or generic data extensions
    (``.zip``, ``.bin``).

    Args:
        project_dir: Root directory of the project.
        files: List of files discovered for inclusion in the package or wheel.

    Returns:
        List of populated :class:`~pitloom.core.ai_metadata.AiModelMetadata`
        instances, each with a ``usage_files`` list of referencing Scripts.
    """
    ai_models: list[AiModelMetadata] = []

    # 1. Identify AI models
    for pf in files:
        phys_path = project_dir / pf.physical_path
        suffix = phys_path.suffix.lower()

        if suffix not in _ALLOWED_EXTS:
            continue

        fmt = detect_ai_model_format(phys_path)
        if fmt != AiModelFormat.UNKNOWN:
            try:
                meta = read_ai_model(phys_path)
                meta.format_info.file_name = phys_path.name
                meta.format_info.file_path_relative = pf.distribution_path
                ai_models.append(meta)
                log.debug(
                    "Discovered AI model: %s (format: %s)", pf.distribution_path, fmt
                )
            except ImportError as e:
                log.warning(
                    "FORMAT=%s FILE=%s: required library not installed; %s",
                    fmt,
                    phys_path,
                    e,
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                log.warning(
                    "FORMAT=%s FILE=%s: failed to extract metadata; %s",
                    fmt,
                    phys_path,
                    e,
                )

    # 2. Find usages in code
    for pf in files:
        if pf.distribution_path.endswith(".py"):
            phys_path = project_dir / pf.physical_path
            try:
                content = phys_path.read_text(encoding="utf-8")
                for meta in ai_models:
                    file_name = meta.format_info.file_name
                    # Basic string matching heuristic for file loading.
                    if file_name and file_name in content:
                        meta.usage_files.append(pf.distribution_path)
                        log.debug(
                            "Found usage of %s inside %s",
                            file_name,
                            pf.distribution_path,
                        )
            except Exception as e:  # pylint: disable=broad-exception-caught
                log.warning(
                    "Could not read text from %s for usage scanning: %s", phys_path, e
                )

    return ai_models
