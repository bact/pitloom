# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What an SBOM describes when a user names a path, a folder, or a folder
and a file in it: a Python project or one AI model file. The one rule of
``loom model``, :func:`pitloom.assemble.generate` and a Git URL, for every
model format: a file is a model by its content (the scan's header sniff),
a folder's candidates are chosen by the scan's suffix filter
(:func:`~pitloom.extract.scanner.is_model_candidate_name`), and a refusal is
worded as for a model file named on its own.

A folder is read non-recursively. Under :data:`AUTO` a named model file
wins over the folder's project; a folder with a project config is a
project; else its one model file is the target. Several model files, or
none, are refused (``model-ambiguous``, ``project-or-model-not-found``).

See also: :mod:`pitloom.extract.scanner` (the read rule),
:mod:`pitloom.core.project_markers` (what makes a project) and
:mod:`pitloom.core.lfs_pointer` (a Git LFS pointer in place of a model).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata, model_file_suffixes
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import (
    in_remote_clone,
    refuse_named_pointer,
    warn_pointers_not_read,
)
from pitloom.core.path_probe import is_missing_errno
from pitloom.core.project import is_sdist_archive
from pitloom.core.project_markers import has_project_config
from pitloom.core.wheel_dist_info import looks_like_wheel_path
from pitloom.extract.ai_model import (
    LFS_POINTER_REASON,
    NotAModel,
    detect_ai_model_format_from_header,
    read_ai_model_header,
    refusal_error,
)
from pitloom.extract.scanner import (
    ReaderGate,
    is_model_candidate_name,
    read_model_candidate,
    scan_step,
    sniff_model_format,
)
from pitloom.extract.scanner_project import local_model_candidate
from pitloom.extract.scanner_wheel import WHEEL_GATED_FORMATS
from pitloom.messages import (
    INPUT_NOT_FOUND,
    MODEL_AMBIGUOUS,
    MODEL_FILE_NOT_FOUND_LINE,
    MODEL_WRONG_FORMAT,
    NAMED_NOT_A_MODEL_LINE,
    NO_PROJECT_ONE_MODEL_LINE,
    NO_SBOM_TARGET,
    NOT_A_MODEL_LINE,
    ONE_MODEL_LINE,
    READER_UNSAFE_REMOTE,
    TARGET_AMBIGUOUS,
    Cap,
    CodedFileNotFoundError,
    CodedValueError,
    emit,
    warn_over_cap,
)

__all__ = [
    "AUTO",
    "MAX_FOLDER_CANDIDATES",
    "MODEL",
    "PROJECT",
    "ModelFile",
    "SbomTarget",
    "is_model_file_target",
    "model_files_in",
    "model_path_of",
    "named_model_file",
    "read_model_file",
    "refuse_not_a_model",
    "remote_reader_gate",
    "require_model_file",
    "resolve_model_file",
    "resolve_sbom_target",
]

log = logging.getLogger(__name__)

#: The kind of SBOM wanted: whichever the folder holds, a project's only, or
#: a model's only.
AUTO: Final = "auto"
PROJECT: Final = "project"
MODEL: Final = "model"
_MODES: Final = frozenset({AUTO, PROJECT, MODEL})

#: Most files a folder may hold whose name could be a model's: each is
#: sniffed (a bounded header read), so a folder of more is not read, said in
#: one ``over-cap`` warning, and refused as several models are.
MAX_FOLDER_CANDIDATES = 1000


@dataclass(frozen=True)
class ModelFile:
    """A file whose header confirms an AI model format.

    Attributes:
        path: The file on disk (possibly in a temporary clone).
        shown: How messages name it: never a temporary path.
        model_format: The format its header confirms.
    """

    path: Path
    shown: str
    model_format: AiModelFormat


@dataclass(frozen=True)
class SbomTarget:
    """What an SBOM describes.

    Attributes:
        kind: :data:`PROJECT` or :data:`MODEL`.
        folder: The folder that was resolved.
        model: The model file, for :data:`MODEL`; else ``None``.
    """

    kind: str
    folder: Path
    model: ModelFile | None = None


def _shown(prefix: str, name: str) -> str:
    """*name* under the POSIX *prefix* (none: *name* alone)."""
    return f"{prefix}/{name}" if prefix else name


def remote_reader_gate() -> ReaderGate | None:
    """The gate of a model file read from a Git URL's temporary clone
    (:func:`~pitloom.core.lfs_pointer.reading_remote_clone`): the formats a
    wheel scan does not read either are listed without metadata, and
    :meth:`~pitloom.extract.scanner.ReaderGate.report` says
    ``reader-unsafe/remote``; ``None`` (every format read) elsewhere."""
    if not in_remote_clone():
        return None
    return ReaderGate(
        WHEEL_GATED_FORMATS, lambda _fmt: True, message=READER_UNSAFE_REMOTE
    )


def refuse_not_a_model(
    path: Path, exc: NotAModel, *, shown: str | None = None
) -> NoReturn:
    """Refuse the file at *path*, named on its own, that *exc* says is not a
    model, in the words every surface uses: a Git LFS pointer as
    :func:`~pitloom.core.lfs_pointer.refuse_named_pointer` says it, else
    :func:`~pitloom.extract.ai_model.refusal_error`. The error names the
    file *shown* (default: *path*).

    Raises:
        ValueError: Always (see :func:`~pitloom.extract.ai_model.refusal_error`).
    """
    if exc.reason == LFS_POINTER_REASON:
        refuse_named_pointer(path, exc, shown=shown)
    named = path if shown is None else Path(shown)
    raise refusal_error(named, exc.model_format, str(exc)) from exc


def require_model_file(path: Path, shown: str | os.PathLike[str]) -> None:
    """Refuse the model file *path*, named on its own, when it does not
    exist (a link is followed); the error names it *shown*. A path that is
    there but cannot be looked at is no missing file: its error stands.

    Raises:
        pitloom.messages.CodedFileNotFoundError: ``input-not-found``.
        OSError: *path* cannot be looked at (permission denied).
    """
    try:
        os.stat(path)
    except OSError as exc:
        if not is_missing_errno(exc):
            raise
        raise CodedFileNotFoundError(
            INPUT_NOT_FOUND, line=MODEL_FILE_NOT_FOUND_LINE, path=shown
        ) from None


def read_model_file(path: Path, *, shown: str | None = None) -> AiModelMetadata:
    """Read the model file at *path*, named on its own, by the rule a scan
    applies (:func:`~pitloom.extract.scanner.read_model_candidate`), its
    messages naming it *shown* (default: *path*). In a Git URL's temporary
    clone the formats of :func:`remote_reader_gate` are listed without
    metadata, said in one ``INFO:`` after the read.

    Raises:
        pitloom.messages.CodedFileNotFoundError: *path* does not exist
            (:func:`require_model_file`).
        ValueError: The file is not a model (:func:`refuse_not_a_model`).
        OSError: The header cannot be read.
    """
    require_model_file(path, path if shown is None else shown)
    gate = remote_reader_gate()
    candidate = local_model_candidate(path, shown=shown, gate=gate)
    try:
        model = read_model_candidate(candidate)
    except NotAModel as exc:
        refuse_not_a_model(path, exc, shown=shown)
    if gate is not None:
        gate.report()
    return model


def _named(path: Path, shown: str, *, strict: bool) -> ModelFile | None:
    """The model file named *path*, by its content; ``None`` for a file that
    is plainly not a model unless *strict*, which refuses it. A Git LFS
    pointer, or a header that contradicts a model suffix, is refused
    either way."""
    require_model_file(path, shown)
    try:
        fmt = sniff_model_format(local_model_candidate(path, shown=shown))
    except NotAModel as exc:
        if strict or exc.reason == LFS_POINTER_REASON or exc.model_format is not None:
            refuse_not_a_model(path, exc, shown=shown)
        return None
    return ModelFile(path, shown, fmt)


def named_model_file(path: Path, shown: str) -> ModelFile | None:
    """The file at *path*, named on its own, as a model file when its header
    confirms a format (whatever its suffix: ``x.dat`` with GGUF magic is
    one); ``None`` for a file that is plainly not a model (``README.md``,
    ``pyproject.toml``). Messages name it *shown*.

    Raises:
        pitloom.messages.CodedFileNotFoundError: *path* does not exist
            (``input-not-found``).
        ValueError: It is a Git LFS pointer, or its header contradicts its
            model suffix (an empty ``x.gguf`` is plainly not a model): see
            :func:`refuse_not_a_model`.
        OSError: Its header cannot be read.
    """
    return _named(path, shown, strict=False)


def _candidate_names(folder: Path) -> list[str]:
    """The names of *folder*'s regular files whose suffix could be a
    model's, sorted as plain ``str``. In a Git URL's temporary clone a link
    is not followed: it could lead out of the clone."""
    follow = not in_remote_clone()
    with os.scandir(folder) as entries:
        return sorted(
            entry.name
            for entry in entries
            if entry.is_file(follow_symlinks=follow)
            and is_model_candidate_name(entry.name)
        )


def model_files_in(
    folder: Path, shown_prefix: str = "", *, subject: str | None = None
) -> list[ModelFile]:
    """The model files directly in *folder* (no subfolder), in name order:
    each file the scan's suffix filter keeps whose header confirms a format,
    a file that is not one said in the scan's words. Each is named
    *shown_prefix* ``/`` its name (its name alone for ``""``). Git LFS
    pointers get one summary ``WARNING:``; a folder of pointers and no
    model is refused as its first pointer.

    Raises:
        pitloom.messages.CodedValueError: ``model-ambiguous`` naming
            *subject* (default: *folder*), when more than
            :data:`MAX_FOLDER_CANDIDATES` names could be models (after one
            ``over-cap`` warning: no file is read); ``lfs-pointer``, for
            pointers only.
        OSError: *folder* cannot be listed.
    """
    names = _candidate_names(folder)
    if len(names) > MAX_FOLDER_CANDIDATES:
        where = str(folder) if subject is None else subject
        cap = Cap(MAX_FOLDER_CANDIDATES, "entry", "model-candidate", "DIR")
        warn_over_cap(log, cap, where, "no file read")
        raise CodedValueError(MODEL_AMBIGUOUS, path=where, count=len(names))
    found: list[ModelFile] = []
    pointers: list[str] = []
    paths: dict[str, Path] = {}
    for name in names:
        path, shown = folder / name, _shown(shown_prefix, name)
        paths[shown] = path
        candidate = local_model_candidate(path, shown=shown)
        fmt = scan_step(candidate, sniff_model_format, pointers)
        if fmt is not None:
            found.append(ModelFile(path, shown, fmt))
    warn_pointers_not_read(pointers)
    if not found and pointers:
        first = min(pointers)
        refuse_named_pointer(paths[first], shown=first)
    return found


def is_model_file_target(path: str | os.PathLike[str]) -> bool:
    """Whether :func:`pitloom.assemble.generate` reads the existing file
    *path* as a model file: not an sdist or wheel, and a model suffix or a
    header that confirms a format. Silent (a classifier asks it more than
    once per run); a header that cannot be read leaves the suffix alone to
    decide."""
    target = Path(path)
    if (
        not os.path.isfile(target)
        or is_sdist_archive(target)
        or looks_like_wheel_path(target)
    ):
        return False
    if target.suffix.lower() in model_file_suffixes():
        return True
    try:
        header = read_ai_model_header(target)
    except OSError:
        return False
    fmt = detect_ai_model_format_from_header(header, target.name)
    return fmt != AiModelFormat.UNKNOWN


def _refuse_folder(subject: str, mode: str) -> NoReturn:
    """Refuse the folder *subject*, which holds no model file: for a model
    only, as a path that is not a model (``model-wrong-format``); else as
    neither a project nor a model (``project-or-model-not-found``)."""
    if mode == MODEL:
        raise CodedValueError(MODEL_WRONG_FORMAT, line=NOT_A_MODEL_LINE, path=subject)
    raise CodedValueError(NO_SBOM_TARGET, path=subject)


def resolve_sbom_target(
    folder: str | os.PathLike[str],
    *,
    subject: str,
    file: str = "",
    mode: str = AUTO,
    shown_prefix: str = "",
) -> SbomTarget:
    """What an SBOM of *folder* (and its file *file*, when named) describes.

    1. A named *file* (not under :data:`PROJECT`) whose header confirms a
       model format is the model. Under :data:`MODEL` any other file is
       refused; under :data:`AUTO` a file plainly not a model
       (``pyproject.toml``) leaves the folder to decide, said in one
       ``INFO:``.
    2. :data:`PROJECT`, or :data:`AUTO` with a project config
       (:func:`~pitloom.core.project_markers.has_project_config`): the
       project; its reader keeps its own errors.
    3. The folder's one model file (:func:`model_files_in`), said in one
       ``INFO:``.

    Messages name a file *shown_prefix* ``/`` its name, and the folder
    *subject* (a path, or a URL with no credentials).

    Raises:
        pitloom.messages.CodedValueError: ``model-ambiguous`` (several model
            files, one ``INFO:`` naming each first), ``project-or-model-not-found``
            (none, under :data:`AUTO`), ``model-wrong-format`` (none, or
            the named file not a model, under :data:`MODEL`), or a refusal of
            the named file (:func:`named_model_file`).
        pitloom.messages.CodedFileNotFoundError: The named file does not
            exist (``input-not-found``).
        OSError: The folder cannot be listed, or a named file's header
            cannot be read.
        pitloom.core.internal_error.InternalError: *mode* is unknown.
    """
    if mode not in _MODES:
        raise InternalError(f"unknown SBOM target mode {mode!r}")
    where = Path(folder)
    if file and mode != PROJECT:
        shown = _shown(shown_prefix, file)
        model = _named(where / file, shown, strict=mode == MODEL)
        if model is not None:
            return SbomTarget(MODEL, where, model)
        emit(
            log, TARGET_AMBIGUOUS, logging.INFO, line=NAMED_NOT_A_MODEL_LINE, file=shown
        )
    if mode == PROJECT or (mode == AUTO and has_project_config(where)):
        return SbomTarget(PROJECT, where)
    models = model_files_in(where, shown_prefix, subject=subject)
    if len(models) == 1:
        model = models[0]
        line = NO_PROJECT_ONE_MODEL_LINE if mode == AUTO else ONE_MODEL_LINE
        emit(log, TARGET_AMBIGUOUS, logging.INFO, line=line, file=model.shown)
        return SbomTarget(MODEL, where, model)
    if not models:
        _refuse_folder(subject, mode)
    for model in models:
        emit(log, MODEL_AMBIGUOUS, logging.INFO, file=model.shown)
    raise CodedValueError(MODEL_AMBIGUOUS, path=subject, count=len(models))


def resolve_model_file(
    folder: str | os.PathLike[str],
    *,
    subject: str,
    file: str = "",
    shown_prefix: str = "",
) -> ModelFile:
    """:func:`resolve_sbom_target` under :data:`MODEL`: the model file of
    *folder* (its named *file*, else its one model file).

    Raises:
        As :func:`resolve_sbom_target`.
    """
    target = resolve_sbom_target(
        folder, subject=subject, file=file, mode=MODEL, shown_prefix=shown_prefix
    )
    if target.model is None:
        raise InternalError("a model target without its model file")
    return target.model


def model_path_of(source: Path, *, subject: str) -> Path:
    """*source*, or for a folder its model file (:func:`resolve_model_file`,
    the folder named *subject* in messages)."""
    if os.path.isdir(source):
        return resolve_model_file(source, subject=subject).path
    return source
