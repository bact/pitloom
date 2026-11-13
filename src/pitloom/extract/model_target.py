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

See also: :mod:`pitloom.extract._model_named` (a file named on its own,
whose public names this module re-exports),
:mod:`pitloom.extract.scanner` (the read rule),
:mod:`pitloom.core.project_markers` (what makes a project) and
:mod:`pitloom.core.lfs_pointer` (a Git LFS pointer in place of a model).
"""

from __future__ import annotations

import logging
import operator
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.clone_mark import in_remote_clone
from pitloom.core.internal_error import InternalError
from pitloom.core.lfs_pointer import refuse_named_pointer, warn_pointers_not_read
from pitloom.core.project import is_sdist_archive
from pitloom.core.project_markers import has_project_config
from pitloom.core.wheel_dist_info import looks_like_wheel_path
from pitloom.extract._model_named import (
    ModelFile,
    has_model_suffix,
    named_file,
    named_model_file,
    read_model_file,
    refuse_not_a_model,
    require_model_file,
)
from pitloom.extract.ai_model import (
    detect_ai_model_format_from_header,
    detect_ai_model_format_from_name,
    read_ai_model_header,
)
from pitloom.extract.scanner import (
    is_model_candidate_name,
    scan_step,
    sniff_model_format,
)
from pitloom.extract.scanner_project import (
    local_model_candidate,
    remote_reader_gate,
)
from pitloom.messages import (
    CodedValueError,
    emit,
)
from pitloom.messages.files import (
    Cap,
    file_unreadable_error,
    warn_over_cap,
)
from pitloom.messages.models import (
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
)
from pitloom.messages.targets import (
    MODEL_AMBIGUOUS,
    MODEL_AMBIGUOUS_OVER_CAP,
    NAMED_NOT_A_MODEL_LINE,
    NO_PROJECT_ONE_MODEL_LINE,
    NO_SBOM_TARGET,
    ONE_MODEL_LINE,
    TARGET_AMBIGUOUS,
)

__all__ = [
    "AUTO",
    "MAX_FOLDER_CANDIDATES",
    "MODEL",
    "PROJECT",
    "ModelFile",
    "SbomTarget",
    "has_model_suffix",
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
    "say_reading_folder",
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
#: one ``over-cap`` warning, and refused (``model-ambiguous/over-cap``).
MAX_FOLDER_CANDIDATES = 1000


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


def say_reading_folder(shown: str) -> None:
    """Say, in one ``INFO:``, that the file named *shown* is not read as a
    model and its folder is read instead."""
    emit(log, TARGET_AMBIGUOUS, logging.INFO, line=NAMED_NOT_A_MODEL_LINE, file=shown)


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
    pointers beside a model get one summary ``WARNING:``; a folder of
    pointers and no model is refused as its first pointer, with no warning.

    Raises:
        pitloom.messages.CodedValueError: ``model-ambiguous/over-cap``
            naming *subject* (default: *folder*), when more than
            :data:`MAX_FOLDER_CANDIDATES` names could be models (after one
            ``over-cap`` warning: no file is read); ``lfs-pointer``, for
            pointers only; ``file-unreadable``, when no file is a model and
            one could not be read (each said in its ``WARNING:`` first).
        OSError: *folder* cannot be listed.
    """
    names = _candidate_names(folder)
    if len(names) > MAX_FOLDER_CANDIDATES:
        where = str(folder) if subject is None else subject
        cap = Cap(MAX_FOLDER_CANDIDATES, "entry", "model-candidate", "DIR")
        warn_over_cap(log, cap, where, "no file read")
        raise CodedValueError(
            MODEL_AMBIGUOUS_OVER_CAP, path=where, limit=MAX_FOLDER_CANDIDATES
        )
    found: list[ModelFile] = []
    pointers: list[str] = []
    unreadable: list[tuple[str, OSError]] = []
    paths: dict[str, Path] = {}
    for name in names:
        path, shown = folder / name, _shown(shown_prefix, name)
        paths[shown] = path
        candidate = local_model_candidate(path, shown=shown)
        fmt = scan_step(candidate, sniff_model_format, pointers, unreadable)
        if fmt is not None:
            found.append(ModelFile(path, shown, fmt))
    if found:
        warn_pointers_not_read(pointers)
    else:
        # The refusal of a folder of pointers names the first and says what
        # to do, so a summary warning would repeat it with other advice.
        _refuse_unread(paths, pointers, unreadable)
    return found


def _refuse_unread(
    paths: dict[str, Path],
    pointers: list[str],
    unreadable: list[tuple[str, OSError]],
) -> None:
    """For a folder with no model file: refuse it as its first Git LFS
    pointer, else as its first candidate that could not be read; return
    when there is neither (*paths*: each candidate by its shown name)."""
    if pointers:
        first = min(pointers)
        refuse_named_pointer(paths[first], shown=first)
    if unreadable:
        shown, exc = min(unreadable, key=operator.itemgetter(0))
        model_format = detect_ai_model_format_from_name(shown)
        raise file_unreadable_error(exc, file=shown, model_format=model_format)


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
    if has_model_suffix(target):
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
       refused, and so under :data:`AUTO` is one whose name has a model
       suffix (:func:`has_model_suffix`: an empty ``x.gguf``); under
       :data:`AUTO` any other name (``pyproject.toml``, ``README.md``),
       plainly not a model or no regular file, leaves the folder to
       decide, said in one ``INFO:``.
    2. :data:`PROJECT`, or :data:`AUTO` with a project config
       (:func:`~pitloom.core.project_markers.has_project_config`): the
       project; its reader keeps its own errors.
    3. The folder's one model file (:func:`model_files_in`), said in one
       ``INFO:``.

    Messages name a file *shown_prefix* ``/`` its name, and the folder
    *subject* (a path, or a URL with no credentials). In a Git URL's clone a
    named file that is a link, or whose real path is out of *folder*, is
    never opened: refused when strict, else the folder decides.

    Raises:
        pitloom.messages.CodedValueError: ``model-ambiguous`` (several model
            files, one ``INFO:`` naming each first), ``project-or-model-not-found``
            (none, under :data:`AUTO`), ``model-wrong-format`` (none, or
            the named file not a model, under :data:`MODEL`),
            ``file-unreadable`` (none, and a candidate could not be read:
            :func:`model_files_in`), or a refusal of the named file
            (:func:`named_model_file`).
        pitloom.messages.CodedFileNotFoundError: The named file does not
            exist, under :data:`MODEL` or with a model suffix
            (``input-not-found``).
        OSError: The folder cannot be listed, or a named file's header
            cannot be read.
        pitloom.core.internal_error.InternalError: *mode* is unknown.
    """
    if mode not in _MODES:
        raise InternalError(f"unknown SBOM target mode {mode!r}")
    where = Path(folder)
    if file and mode != PROJECT:
        shown = _shown(shown_prefix, file)
        strict = mode == MODEL or has_model_suffix(file)
        model = named_file(where / file, shown, strict=strict, root=where)
        if model is not None:
            return SbomTarget(MODEL, where, model)
        say_reading_folder(shown)
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
