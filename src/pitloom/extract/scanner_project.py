# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Project-directory producer for the AI model scanner.

In a Git URL's temporary clone the formats a wheel scan does not read
either are listed without metadata (:func:`remote_reader_gate`) unless the
user vouches for the model files (``--trust-model-files``); a local
project, the Hatchling hook and ``embed-wheel`` read every format.

See also: :mod:`pitloom.extract.scanner`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.clone_mark import in_remote_clone, remote_clone_trusted
from pitloom.core.lfs_pointer import LfsPointer, read_lfs_pointer
from pitloom.core.project import ProjectFile, project_relative_or_fallback
from pitloom.extract.ai_model import read_ai_model_header
from pitloom.extract.scanner import (
    ModelCandidate,
    ReaderGate,
    UsageSource,
    scan_ai_models,
)
from pitloom.extract.scanner_wheel import reader_gate
from pitloom.messages.models import READER_UNSAFE_REMOTE


def remote_reader_gate() -> ReaderGate | None:
    """The gate of model files read from a Git URL's temporary clone
    (:func:`~pitloom.core.lfs_pointer.reading_remote_clone`), on the model
    route and the project route alike: the formats a wheel scan does not
    read either are listed without metadata, and
    :meth:`~pitloom.extract.scanner.ReaderGate.report` says
    ``reader-unsafe/remote``; ``None`` (every format read) elsewhere, and in
    a clone whose caller vouched for its model files
    (:func:`~pitloom.core.clone_mark.remote_clone_trusted`)."""
    if not in_remote_clone():
        return None
    return reader_gate(
        trusted=remote_clone_trusted(),
        announce=lambda _fmt: True,
        message=READER_UNSAFE_REMOTE,
    )


def _stable_path(pf: ProjectFile) -> str:
    """Project-relative path, or the distribution path for an absolute one."""
    return project_relative_or_fallback(pf.physical_path, pf.distribution_path)


def _sniffer(path: Path) -> Callable[[], bytes]:
    def _sniff() -> bytes:
        return read_ai_model_header(path)

    return _sniff


def _pointer_reader(path: Path) -> Callable[[], LfsPointer | None]:
    def _pointer() -> LfsPointer | None:
        try:
            return read_lfs_pointer(path)
        except OSError:
            return None

    return _pointer


def _materializer(path: Path) -> Callable[[], AbstractContextManager[Path]]:
    def _materialize() -> AbstractContextManager[Path]:
        return contextlib.nullcontext(path)

    return _materialize


def _opener(path: Path) -> Callable[[], AbstractContextManager[IO[bytes]]]:
    def _open() -> AbstractContextManager[IO[bytes]]:
        return path.open("rb")

    return _open


def local_model_candidate(
    path: Path, *, shown: str | None = None, gate: ReaderGate | None = None
) -> ModelCandidate:
    """A single local model file as a :class:`ModelCandidate`, for the
    surfaces that name one file (``loom model``, ``loom enrich``) and a
    folder's files (:mod:`pitloom.extract.model_target`): the one read rule
    of a scan, with *shown* (default: *path* as given) for the physical
    path, its name as the distribution path, and *gate* (none: every
    format read). The scan's suffix filter
    (:func:`~pitloom.extract.scanner.is_model_candidate_name`) is not applied:
    a file named explicitly is read by its content."""
    return ModelCandidate(
        distribution_path=path.name,
        physical_path=str(path) if shown is None else shown,
        sniff=_sniffer(path),
        materialize=_materializer(path),
        read_path=path,
        gate=gate,
        pointer=_pointer_reader(path),
    )


def project_candidates(
    project_dir: Path,
    files: Iterable[ProjectFile],
    *,
    gate: ReaderGate | None = None,
) -> Iterator[ModelCandidate]:
    """One :class:`ModelCandidate` per file, in *files* order, each under
    *gate* (none: every format read)."""
    for pf in files:
        # An absolute physical_path (--allow-build) drops project_dir here.
        path = project_dir / pf.physical_path
        yield ModelCandidate(
            distribution_path=pf.distribution_path,
            physical_path=_stable_path(pf),
            sniff=_sniffer(path),
            materialize=_materializer(path),
            read_path=path,
            gate=gate,
            pointer=_pointer_reader(path),
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
    usage_hint: Callable[[], bool],
) -> list[AiModelMetadata]:
    """Scan project files for AI models; with *scan_usage*, their script usages.

    *usage_hint* is asked before the one-line ``INFO:`` naming the setting (see
    :func:`pitloom.extract.scanner.scan_ai_models`).

    In a Git URL's temporary clone the formats of :func:`remote_reader_gate`
    are listed without metadata, said in one ``INFO:`` after a scan that
    succeeded (a failed one writes no SBOM for the line to describe).

    Models come back sorted; see
    :func:`pitloom.extract.scanner.discover_ai_models`.
    """
    gate = remote_reader_gate()
    models = scan_ai_models(
        project_candidates(project_dir, files, gate=gate),
        project_sources(project_dir, files),
        scan_usage=scan_usage,
        usage_hint=usage_hint,
    )
    if gate is not None:
        gate.report()
    return models
