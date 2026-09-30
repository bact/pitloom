# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Heuristic scanner for AI model files and their usage in Python codebase.

This module is the surface-agnostic policy: which files are model candidates,
how their format is decided, and how ``.py`` files are matched against the
discovered models. Producers (e.g. the project-directory one) turn their own
files into :class:`ModelCandidate` and :class:`UsageSource` objects; this
module imports no producer.

See also: :mod:`pitloom.extract.scanner_project`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING
from pitloom.extract.ai_model import detect_ai_model_format_from_header, read_ai_model

log = logging.getLogger(__name__)

# Extensions that might genuinely be AI models.
_ALLOWED_EXTS: frozenset[str] = frozenset(
    {".zip", ".bin"}
    | {
        ext.lower()
        for fmt in AiModelFormat.__members__.values()
        for ext in fmt.extensions
    }
)


def is_model_candidate_name(distribution_path: str) -> bool:
    """Whether *distribution_path*'s suffix could be an AI model file."""
    return PurePosixPath(distribution_path).suffix.lower() in _ALLOWED_EXTS


@dataclass(frozen=True)
class ModelCandidate:
    """A file that may be an AI model, as seen by one producer.

    Attributes:
        distribution_path: POSIX in-distribution path. Decides the suffix
            filter, the extension fallback and ``file_name``.
        physical_path: Stable display/lookup path: project-relative, or
            ``distribution_path`` when the file has no project-relative
            path. Never a temporary path; the shared code trusts this.
            Printed as ``FILE=`` in warnings.
        sniff: Returns at most ``SNIFF_BYTES`` leading bytes, ``b""`` when
            the file is absent. Raises :class:`OSError` when it exists but
            cannot be read; the scanner warns and skips the candidate.
        materialize: Returns a context manager yielding a real path for
            :func:`pitloom.extract.ai_model.read_ai_model`. May raise.
    """

    distribution_path: str
    physical_path: str
    sniff: Callable[[], bytes]
    materialize: Callable[[], AbstractContextManager[Path]]


@dataclass(frozen=True)
class UsageSource:
    """A file that may reference model files by name.

    Attributes:
        distribution_path: Path recorded in ``usage_files``; the ``.py``
            filter applies to it.
        physical_path: Stable path (never a temporary one), printed as
            ``FILE=`` in warnings.
        open: Returns a context manager yielding a binary stream. May raise.
    """

    distribution_path: str
    physical_path: str
    open: Callable[[], AbstractContextManager[IO[bytes]]]


def _set_paths(info: AiModelFormatInfo, candidate: ModelCandidate) -> None:
    """Record the candidate's stable names on *info*."""
    info.file_name = PurePosixPath(candidate.distribution_path).name
    info.file_path_relative = candidate.distribution_path
    info.physical_path = candidate.physical_path


def _read_candidate(candidate: ModelCandidate) -> AiModelMetadata | None:
    """Detect and read one candidate; ``None`` when it is not a model."""
    if not is_model_candidate_name(candidate.distribution_path):
        return None
    try:
        header = candidate.sniff()
    except OSError as e:
        log.warning(
            "FORMAT=%s " + UNREADABLE_FILE_WARNING,
            detect_ai_model_format_from_header(b"", candidate.distribution_path),
            candidate.physical_path,
            "header",
            e,
        )
        return None
    fmt = detect_ai_model_format_from_header(header, candidate.distribution_path)
    if fmt == AiModelFormat.UNKNOWN:
        return None

    try:
        with candidate.materialize() as path:
            meta = read_ai_model(path, model_format=fmt)
        _set_paths(meta.format_info, candidate)
        log.debug(
            "Discovered AI model: %s (format: %s)", candidate.distribution_path, fmt
        )
        return meta
    except ImportError as e:
        log.warning(
            "FORMAT=%s FILE=%s: required library not installed; %s",
            fmt,
            candidate.physical_path,
            e,
        )
        stub = AiModelMetadata(format_info=AiModelFormatInfo(model_format=fmt))
        _set_paths(stub.format_info, candidate)
        return stub
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        log.warning(
            "FORMAT=%s FILE=%s: failed to extract metadata; %s",
            fmt,
            candidate.physical_path,
            e,
        )
    return None


def discover_ai_models(candidates: Iterable[ModelCandidate]) -> list[AiModelMetadata]:
    """Detect and read AI models among *candidates*, in candidate order."""
    models: list[AiModelMetadata] = []
    for candidate in candidates:
        meta = _read_candidate(candidate)
        if meta is not None:
            models.append(meta)
    return models


def attach_usage_references(
    models: Sequence[AiModelMetadata], sources: Iterable[UsageSource]
) -> None:
    """Record which ``.py`` sources mention each model's file name.

    Runs even when *models* is empty, so unreadable sources are still
    reported.
    """
    for source in sources:
        if not source.distribution_path.endswith(".py"):
            continue
        try:
            with source.open() as fh:
                content = fh.read().decode("utf-8")
            for meta in models:
                file_name = meta.format_info.file_name
                if file_name and file_name in content:
                    meta.usage_files.append(source.distribution_path)
                    log.debug(
                        "Found usage of %s inside %s",
                        file_name,
                        source.distribution_path,
                    )
        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            log.warning(
                UNREADABLE_FILE_WARNING,
                source.physical_path,
                "for usage scanning",
                e,
            )


def scan_ai_models(
    candidates: Iterable[ModelCandidate], sources: Iterable[UsageSource]
) -> list[AiModelMetadata]:
    """Discover AI models, then attach their usages in Python sources."""
    models = discover_ai_models(candidates)
    attach_usage_references(models, sources)
    return models
