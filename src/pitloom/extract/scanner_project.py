# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project-directory producer for the AI model scanner.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.project import ProjectFile, project_relative_or_fallback
from pitloom.extract.ai_model import read_ai_model_header
from pitloom.extract.scanner import ModelCandidate, UsageSource, scan_ai_models


def _stable_path(pf: ProjectFile) -> str:
    """Project-relative path, or the distribution path for an absolute one."""
    return project_relative_or_fallback(pf.physical_path, pf.distribution_path)


def _sniffer(path: Path) -> Callable[[], bytes]:
    def _sniff() -> bytes:
        return read_ai_model_header(path)

    return _sniff


def _materializer(path: Path) -> Callable[[], AbstractContextManager[Path]]:
    def _materialize() -> AbstractContextManager[Path]:
        return contextlib.nullcontext(path)

    return _materialize


def _opener(path: Path) -> Callable[[], AbstractContextManager[IO[bytes]]]:
    def _open() -> AbstractContextManager[IO[bytes]]:
        return path.open("rb")

    return _open


def project_candidates(
    project_dir: Path, files: Iterable[ProjectFile]
) -> Iterator[ModelCandidate]:
    """One :class:`ModelCandidate` per file, in *files* order."""
    for pf in files:
        # An absolute physical_path (--allow-build) drops project_dir here.
        path = project_dir / pf.physical_path
        yield ModelCandidate(
            distribution_path=pf.distribution_path,
            physical_path=_stable_path(pf),
            sniff=_sniffer(path),
            materialize=_materializer(path),
        )


def project_sources(
    project_dir: Path, files: Iterable[ProjectFile]
) -> Iterator[UsageSource]:
    """One :class:`UsageSource` per file, in *files* order."""
    for pf in files:
        path = project_dir / pf.physical_path
        yield UsageSource(
            distribution_path=pf.distribution_path,
            physical_path=_stable_path(pf),
            open=_opener(path),
        )


def scan_project_for_ai_models(
    project_dir: Path,
    files: list[ProjectFile],
    *,
    scan_usage: bool,
    usage_hint: bool,
) -> list[AiModelMetadata]:
    """Scan project files for AI models; with *scan_usage*, their script usages.

    *usage_hint* allows the one-line ``INFO:`` naming the setting (see
    :func:`pitloom.extract.scanner.scan_ai_models`).

    Models come back sorted; see
    :func:`pitloom.extract.scanner.discover_ai_models`.
    """
    return scan_ai_models(
        project_candidates(project_dir, files),
        project_sources(project_dir, files),
        scan_usage=scan_usage,
        usage_hint=usage_hint,
    )
