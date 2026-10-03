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

Invariant: one confirmed model file (its header agrees with a model format)
gives exactly one entry, whatever its read outcome. A read that fails (a
parse error, a bound, a missing library, a wheel gate) keeps a format-only
entry and one ``WARNING:``; it is never dropped, so the entry set does not
depend on the order of the files, the budget or the installed libraries. A
file that is not a confirmed model gives no entry
(:class:`~pitloom.extract.ai_model.NotAModel`).

See also: :mod:`pitloom.extract.scanner_project`,
:mod:`pitloom.extract.scanner_wheel` and :mod:`pitloom.extract._scanner_messages`.
"""

from __future__ import annotations

import logging
import operator
import os
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO

from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.inert_options import PARAM_TO_FLAG
from pitloom.core.path_probe import UNREADABLE_FILE_WARNING
from pitloom.extract._extract_utils import sanitize_provenance_text
from pitloom.extract._reader_log import capture_reader_logs
from pitloom.extract._scanner_messages import detail, scrub
from pitloom.extract.ai_model import (
    NotAModel,
    contradicted_format,
    detect_ai_model_format_from_header,
    detect_ai_model_format_from_name,
    not_a_model_reason,
    read_ai_model,
    refusal_reason,
)
from pitloom.extract.ai_model.archive_member import ArchiveMemberTooLarge
from pitloom.extract.ai_model.limits import (
    ModelLimitExceeded,
    ScanBudgetExceeded,
    cap_and_warn,
)
from pitloom.extract.ai_model.reader_requirements import require_library
from pitloom.logging_config import loggable

log = logging.getLogger(__name__)

# UNREADABLE_FILE_WARNING with the model format first, as every
# FORMAT=%s FILE=%s scan warning reads.
_UNREADABLE_MODEL_WARNING = "FORMAT=%s " + UNREADABLE_FILE_WARNING

# Said once per scan, listing the gated formats met that were not announced
# before.
_GATE_INFO = (
    "AI models in a wheel in these formats are listed without metadata, "
    "their reader not being run on a wheel's files: %s. Pass %s for a "
    "wheel you trust."
)

# The usage hint. The setting is spelt per producer: a project reads its own
# config; a wheel reads none implicitly, so its setting needs a named one.
_USAGE_HINT = (
    "Found %d AI model file(s); pass --scan-model-usage (or set %s) to also "
    "record which Python files reference them."
)
USAGE_SETTING_PROJECT = "scan-model-usage = true"
USAGE_SETTING_WHEEL = "scan-model-usage = true in a --config file or pitloom_config"

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
class ReaderGate:
    """Formats a producer does not read, because their reader can crash,
    hang or exhaust memory on a hostile file, and Ctrl-C cannot interrupt
    it. Such a model keeps a format-only entry.

    Attributes:
        formats: The gated formats.
        announce: Called by :meth:`report` once per gated format met, with
            that format; returns whether to name it in the ``INFO:`` line. The
            producer makes it claim a once-per-run slot for the format.
        met: The gated formats met so far.
    """

    formats: frozenset[AiModelFormat]
    announce: Callable[[AiModelFormat], bool]
    met: set[AiModelFormat] = field(default_factory=set)

    def report(self) -> None:
        """Log one line naming the gated formats met (sorted) that *announce*
        allows; nothing when it allows none."""
        named = [str(fmt) for fmt in sorted(self.met, key=str) if self.announce(fmt)]
        if named:
            log.info(_GATE_INFO, ", ".join(named), PARAM_TO_FLAG["trust_wheel_model"])


@dataclass(frozen=True)
class ModelCandidate:
    """A file that may be an AI model, as seen by one producer.

    Attributes:
        distribution_path: POSIX in-distribution path. Decides the suffix
            filter, the suffix check on the header and ``file_name``.
        physical_path: Stable display/lookup path: project-relative
            (``distribution_path`` for an absolute one), or the raw archive
            member name in a wheel. Never a temporary path; the shared code
            trusts this. Printed as ``FILE=`` in warnings.
        sniff: Returns at most ``SNIFF_BYTES`` leading bytes, ``b""`` when
            the file is absent. Raises :class:`OSError` when it exists but
            cannot be read; a scan warns and skips the candidate,
            :func:`read_model_candidate` lets it propagate.
        materialize: Returns a context manager yielding a real path for
            :func:`pitloom.extract.ai_model.read_ai_model`. May raise.
        read_path: The file ``sniff`` reads, when it is one; the scanner
            removes it, in every spelling, from the messages it logs.
        gate: Formats left unread (see :class:`ReaderGate`); the
            header sniff alone decides, and nothing is materialised.
    """

    distribution_path: str
    physical_path: str
    sniff: Callable[[], bytes]
    materialize: Callable[[], AbstractContextManager[Path]]
    read_path: Path | None = None
    gate: ReaderGate | None = None


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
        text = scrub(text, path, candidate.physical_path)
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


def _sniff_format(candidate: ModelCandidate) -> AiModelFormat:
    """The candidate's format from its header.

    Raises:
        NotAModel: The header does not confirm a model format.
        OSError: The header cannot be read.
    """
    header = candidate.sniff()
    name = candidate.distribution_path
    fmt = detect_ai_model_format_from_header(header, name)
    if fmt != AiModelFormat.UNKNOWN:
        return fmt
    path = candidate.read_path
    message = refusal_reason(
        header, name, is_file=path is not None and os.path.isfile(path)
    )
    raise NotAModel(
        contradicted_format(header, name), not_a_model_reason(header, name), message
    )


def read_model_candidate(candidate: ModelCandidate) -> AiModelMetadata:
    """Detect and read one candidate, the one rule for every surface.

    Returns the model, or, when it is a confirmed model whose read fails or is
    over a limit, a format-only entry (one ``WARNING:`` for the failure kinds
    that have one).

    Raises:
        NotAModel: The header does not confirm a model format.
        OSError: The header cannot be read, so the format is not known.
    """
    fmt = _sniff_format(candidate)
    where = loggable(candidate.physical_path)
    if candidate.gate is not None and fmt in candidate.gate.formats:
        candidate.gate.met.add(fmt)
        return _stub(fmt, candidate)

    path: Path | None = None
    try:
        # Before the model is copied out of its archive.
        require_library(fmt)
        with candidate.materialize() as path:
            meta = _read_materialized(candidate, fmt, path)
        _set_paths(meta.format_info, candidate)
        cap_and_warn(meta, fmt, where)
        log.debug(
            "Discovered AI model: %s (format: %s)",
            loggable(candidate.distribution_path),
            fmt,
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
    except ModelLimitExceeded as e:
        log.warning(
            "FORMAT=%s FILE=%s: %s; metadata not read",
            fmt,
            where,
            loggable(e.reason),
        )
    except ImportError as e:
        log.warning(
            "FORMAT=%s FILE=%s: required library not installed; %s",
            fmt,
            where,
            detail(e, path, candidate.physical_path),
        )
    # pylint: disable-next=broad-exception-caught
    except Exception as e:
        log.warning(
            "FORMAT=%s FILE=%s: failed to extract metadata; %s",
            fmt,
            where,
            detail(e, path, candidate.physical_path),
        )
    return _stub(fmt, candidate)


def _discover_one(candidate: ModelCandidate) -> AiModelMetadata | None:
    """:func:`read_model_candidate` for a scan: ``None`` for a file that is
    not a model, a candidate whose suffix could not be one is not even read.
    The warning for an unreadable header or a header contradicting a model
    suffix is said here, in the scan's words."""
    if not is_model_candidate_name(candidate.distribution_path):
        return None
    try:
        return read_model_candidate(candidate)
    except OSError as e:
        log.warning(
            _UNREADABLE_MODEL_WARNING,
            detect_ai_model_format_from_name(candidate.distribution_path),
            loggable(candidate.physical_path),
            "header",
            detail(e, candidate.read_path, candidate.physical_path),
        )
    except NotAModel as e:
        if e.reason is not None:
            # A pointer named x.bin has no format to name.
            key = "" if e.model_format is None else f"FORMAT={e.model_format} "
            log.warning(
                "%sFILE=%s: %s; not listed as an AI model",
                key,
                loggable(candidate.physical_path),
                e.reason,
            )
    return None


def discover_ai_models(candidates: Iterable[ModelCandidate]) -> list[AiModelMetadata]:
    """Detect and read AI models among *candidates*.

    Returns models sorted by (distribution_path, physical_path), whatever the
    order of *candidates*; reads and warnings follow the same order. See the
    module docstring for what becomes an entry.
    """
    models: list[AiModelMetadata] = []
    for candidate in sorted(candidates, key=_PATH_ORDER):
        meta = _discover_one(candidate)
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
                        loggable(file_name),
                        loggable(source.distribution_path),
                    )
        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            log.warning(
                UNREADABLE_FILE_WARNING,
                loggable(source.physical_path),
                "for usage scanning",
                detail(e, source.read_path, source.physical_path),
            )
    for meta in models:
        meta.usage_files = sorted(set(meta.usage_files))


def scan_ai_models(
    candidates: Iterable[ModelCandidate],
    sources: Iterable[UsageSource],
    *,
    scan_usage: bool,
    usage_hint: Callable[[], bool],
    usage_setting: str = USAGE_SETTING_PROJECT,
) -> list[AiModelMetadata]:
    """Discover AI models, then attach their usages if *scan_usage*.

    Discovery always runs. The usage pass reads every Python source, so it
    runs only on request. Otherwise, with models found, *usage_hint* is
    called -- only then, so it may claim a once-per-run slot -- and when it
    returns true one ``INFO:`` line names the setting, spelt *usage_setting*.
    Order: see :func:`discover_ai_models`.
    """
    models = discover_ai_models(candidates)
    if scan_usage:
        attach_usage_references(models, sources)
    elif models and usage_hint():
        log.info(_USAGE_HINT, len(models), usage_setting)
    return models
