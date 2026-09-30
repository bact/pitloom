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
import operator
import os
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.inert_options import PARAM_TO_FLAG
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract._reader_log import capture_reader_logs
from pitloom.extract.ai_model import detect_ai_model_format_from_header, read_ai_model
from pitloom.extract.ai_model.archive_member import ArchiveMemberTooLarge
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

# UNREADABLE_FILE_WARNING with the model format first, as every
# FORMAT=%s FILE=%s scan warning reads.
_UNREADABLE_MODEL_WARNING = "FORMAT=%s " + UNREADABLE_FILE_WARNING

# Said once per run when a producer gates a model's native reader.
_NATIVE_GATE_INFO = (
    "%s models in a wheel are listed without metadata: their native loader "
    "is not run on a wheel's files. Pass %s for a wheel you trust."
)

# Extensions that might genuinely be AI models.
_ALLOWED_EXTS: frozenset[str] = frozenset(
    {".zip", ".bin"}
    | {
        ext.lower()
        for fmt in AiModelFormat.__members__.values()
        for ext in fmt.extensions
    }
)

# A usage source larger than this is skipped, not read whole.
_USAGE_SCAN_MAX_BYTES = 1024 * 1024

# Model order: distribution path, then the stable physical path as the
# tie-break. Plain str compare, never Path (Windows compares Path
# case-insensitively). Positional consumers (enrichment results, registry
# claims in pitloom.assemble.spdx3.ai) rely on this order.
_PATH_ORDER = operator.attrgetter("distribution_path", "physical_path")


def is_model_candidate_name(distribution_path: str) -> bool:
    """Whether *distribution_path*'s suffix could be an AI model file."""
    return PurePosixPath(distribution_path).suffix.lower() in _ALLOWED_EXTS


@dataclass(frozen=True)
class NativeReaderGate:
    """Formats a producer does not read, because their reader is a native
    loader that a hostile file can hang or exhaust memory in (and Ctrl-C
    cannot interrupt). Such a model keeps a format-only entry.

    Attributes:
        formats: The gated formats.
        announce: Called when a gated model is met; returns whether to log
            the ``INFO:`` line saying so. The producer makes it claim a
            once-per-run slot.
    """

    formats: frozenset[AiModelFormat]
    announce: Callable[[], bool]


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
        read_path: The file ``sniff`` reads, when it is one; the scanner
            removes it, in every spelling, from the messages it logs.
        gate: Formats left unread (see :class:`NativeReaderGate`); the
            header sniff alone decides, and nothing is materialised.
    """

    distribution_path: str
    physical_path: str
    sniff: Callable[[], bytes]
    materialize: Callable[[], AbstractContextManager[Path]]
    read_path: Path | None = None
    gate: NativeReaderGate | None = None


@dataclass(frozen=True)
class UsageSource:
    """A file that may reference model files by name.

    Attributes:
        distribution_path: Path recorded in ``usage_files``; the ``.py``
            filter applies to it.
        physical_path: Stable path (never a temporary one), printed as
            ``FILE=`` in warnings.
        open: Returns a context manager yielding a binary stream. May raise.
        read_path: The file ``open`` reads, when it is one; as
            :attr:`ModelCandidate.read_path`.
    """

    distribution_path: str
    physical_path: str
    open: Callable[[], AbstractContextManager[IO[bytes]]]
    read_path: Path | None = None


class ModelTooLarge(Exception):
    """Raised by a candidate's ``materialize`` when the file exceeds the size
    ceiling, before or while copying it. The scanner logs it and keeps a
    format-only entry, so every ``FORMAT=``/``FILE=`` string has one owner.

    Attributes:
        size: The declared size; ``None`` when the copy was aborted after
            reading more than *limit* bytes, so the size is not known.
        limit: The ceiling in bytes.
    """

    def __init__(self, size: int | None, limit: int) -> None:
        super().__init__(f"{size} bytes exceeds the {limit}-byte limit")
        self.size = size
        self.limit = limit


class ScanBudgetExceeded(Exception):
    """Raised by a candidate's ``materialize`` when the producer's overall
    extraction budget is spent. The producer has already logged the one
    warning for it; the scanner keeps a format-only entry, quietly."""


def _path_forms(path: Path) -> list[str]:
    """Every spelling of *path* an exception text may quote, longest first:
    as given and resolved, each raw, as ``repr`` escapes it (a Windows
    path's backslashes doubled) and with forward slashes."""
    real = os.path.realpath(path)
    forms = {path.as_posix(), Path(real).as_posix()}
    for spelling in (str(path), real):
        forms |= {spelling, repr(spelling)[1:-1]}
    return sorted(filter(None, forms), key=len, reverse=True)


def _scrub(text: str, path: Path | None, stable_path: str) -> str:
    """*text*, printable, with the temporary *path* replaced by *stable_path*."""
    if path is not None:
        for form in _path_forms(path):
            text = text.replace(form, stable_path)
    return loggable(text)


def _detail(exc: BaseException, path: Path | None, stable_path: str) -> str:
    """*exc*'s text, see :func:`_scrub`."""
    return _scrub(str(exc), path, stable_path)


def _restore_source_name(meta: AiModelMetadata, path: Path, dist_name: str) -> None:
    """Rewrite the ``Source: <file name>`` prefix a reader derived from
    *path* to *dist_name*, when a copy under another name was read.

    Exact prefix only: a model's own metadata may contain the same text.
    """
    if path.name == dist_name:
        return
    copied = f"Source: {sanitize_provenance_text(path.name)}"
    real = f"Source: {sanitize_provenance_text(dist_name)}"
    for key, value in meta.provenance.items():
        if value == copied or value.startswith(copied + " |"):
            meta.provenance[key] = real + value[len(copied) :]


def _set_paths(info: AiModelFormatInfo, candidate: ModelCandidate) -> None:
    """Record the candidate's stable names on *info*."""
    info.file_name = PurePosixPath(candidate.distribution_path).name
    info.file_path_relative = candidate.distribution_path
    info.physical_path = candidate.physical_path


def _stub(fmt: AiModelFormat, candidate: ModelCandidate) -> AiModelMetadata:
    """A format-only entry: the model's file and format, no metadata read."""
    stub = AiModelMetadata(format_info=AiModelFormatInfo(model_format=fmt))
    _set_paths(stub.format_info, candidate)
    return stub


def _relog_reader_records(
    records: Iterable[logging.LogRecord],
    fmt: AiModelFormat,
    candidate: ModelCandidate,
    path: Path,
) -> None:
    """Log what a reader logged, as the scanner's own messages: the stable
    ``FORMAT=``/``FILE=`` prefix on a warning, the text escaped, the
    temporary copy's path and name replaced by the model's."""
    dist_name = PurePosixPath(candidate.distribution_path).name
    copied = f"Source: {sanitize_provenance_text(path.name)}"
    for record in records:
        text = record.getMessage()
        if path.name != dist_name:
            text = text.replace(
                copied, f"Source: {sanitize_provenance_text(dist_name)}"
            )
        text = _scrub(text, path, candidate.physical_path)
        if record.levelno >= logging.WARNING:
            log.log(
                record.levelno,
                "FORMAT=%s FILE=%s: %s",
                fmt,
                loggable(candidate.physical_path),
                text,
            )
        else:
            log.log(record.levelno, "%s", text)


def _read_materialized(
    candidate: ModelCandidate, fmt: AiModelFormat, path: Path
) -> AiModelMetadata:
    """Read the file at *path*, relaying the reader's log records."""
    with capture_reader_logs() as records:
        try:
            meta = read_ai_model(path, model_format=fmt)
        finally:
            _relog_reader_records(records, fmt, candidate, path)
    _restore_source_name(meta, path, PurePosixPath(candidate.distribution_path).name)
    return meta


def _sniff_format(candidate: ModelCandidate) -> AiModelFormat | None:
    """The candidate's format from its header; ``None`` (with a warning when
    the header cannot be read) when it is not a model."""
    try:
        header = candidate.sniff()
    except OSError as e:
        log.warning(
            _UNREADABLE_MODEL_WARNING,
            detect_ai_model_format_from_header(b"", candidate.distribution_path),
            loggable(candidate.physical_path),
            "header",
            _detail(e, candidate.read_path, candidate.physical_path),
        )
        return None
    fmt = detect_ai_model_format_from_header(header, candidate.distribution_path)
    return None if fmt == AiModelFormat.UNKNOWN else fmt


def _read_candidate(candidate: ModelCandidate) -> AiModelMetadata | None:
    """Detect and read one candidate; ``None`` when it is not a model."""
    if not is_model_candidate_name(candidate.distribution_path):
        return None
    where = loggable(candidate.physical_path)
    fmt = _sniff_format(candidate)
    if fmt is None:
        return None
    if candidate.gate is not None and fmt in candidate.gate.formats:
        if candidate.gate.announce():
            log.info(_NATIVE_GATE_INFO, fmt, PARAM_TO_FLAG["trust_wheel_model"])
        return _stub(fmt, candidate)

    path: Path | None = None
    try:
        with candidate.materialize() as path:
            meta = _read_materialized(candidate, fmt, path)
        _set_paths(meta.format_info, candidate)
        log.debug(
            "Discovered AI model: %s (format: %s)", candidate.distribution_path, fmt
        )
        return meta
    except ModelTooLarge as e:
        if e.size is None:
            size = f"read more than {e.limit} bytes, over"
        else:
            size = f"{e.size} bytes exceeds"
        log.warning(
            "FORMAT=%s FILE=%s: %s the %d-byte scan ceiling; metadata not read",
            fmt,
            where,
            size,
            e.limit,
        )
    except ScanBudgetExceeded:
        log.debug("Scan budget spent; %s kept without metadata", where)
    except ArchiveMemberTooLarge as e:
        log.warning(
            "FORMAT=%s FILE=%s: archive member %s larger than %d bytes; "
            "metadata not read",
            fmt,
            where,
            loggable(e.member),
            e.limit,
        )
    except ImportError as e:
        log.warning(
            "FORMAT=%s FILE=%s: required library not installed; %s",
            fmt,
            where,
            _detail(e, path, candidate.physical_path),
        )
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        log.warning(
            "FORMAT=%s FILE=%s: failed to extract metadata; %s",
            fmt,
            where,
            _detail(e, path, candidate.physical_path),
        )
        return None
    return _stub(fmt, candidate)


def discover_ai_models(candidates: Iterable[ModelCandidate]) -> list[AiModelMetadata]:
    """Detect and read AI models among *candidates*.

    Returns models sorted by (distribution_path, physical_path), whatever the
    order of *candidates*; reads and warnings follow the same order.
    """
    models: list[AiModelMetadata] = []
    for candidate in sorted(candidates, key=_PATH_ORDER):
        meta = _read_candidate(candidate)
        if meta is not None:
            models.append(meta)
    return models


def attach_usage_references(
    models: Sequence[AiModelMetadata], sources: Iterable[UsageSource]
) -> None:
    """Record which ``.py`` sources mention each model's file name.

    Reads every source even when *models* is empty, so unreadable sources
    are still reported; callers skip it altogether when usage scanning is
    off (see :func:`scan_ai_models`). Each model's ``usage_files`` ends
    sorted and deduplicated by distribution path.
    """
    for source in sorted(sources, key=_PATH_ORDER):
        if not source.distribution_path.endswith(".py"):
            continue
        try:
            with source.open() as fh:
                raw = fh.read(_USAGE_SCAN_MAX_BYTES + 1)
            if len(raw) > _USAGE_SCAN_MAX_BYTES:
                log.warning(
                    "FILE=%s: larger than the %d-byte usage-scan cap; skipped",
                    loggable(source.physical_path),
                    _USAGE_SCAN_MAX_BYTES,
                )
                continue
            content = raw.decode("utf-8")
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
                loggable(source.physical_path),
                "for usage scanning",
                _detail(e, source.read_path, source.physical_path),
            )
    for meta in models:
        meta.usage_files = sorted(set(meta.usage_files))


def scan_ai_models(
    candidates: Iterable[ModelCandidate],
    sources: Iterable[UsageSource],
    *,
    scan_usage: bool,
    usage_hint: Callable[[], bool],
) -> list[AiModelMetadata]:
    """Discover AI models, then attach their usages if *scan_usage*.

    Discovery always runs. The usage pass reads every Python source, so it
    runs only on request. Otherwise, with models found, *usage_hint* is
    called -- only then, so it may claim a once-per-run slot -- and when it
    returns true one ``INFO:`` line names the setting.
    Order: see :func:`discover_ai_models`.
    """
    models = discover_ai_models(candidates)
    if scan_usage:
        attach_usage_references(models, sources)
    elif models and usage_hint():
        log.info(
            "Found %d AI model file(s); pass --scan-model-usage (or set "
            "scan-model-usage = true) to also record which Python files "
            "reference them.",
            len(models),
        )
    return models
