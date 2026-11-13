# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model file named on its own: whether it is there and a regular file,
whether its name is a model's, its read, and its refusal in the words every
surface uses. In a Git URL's clone a named link, or a path out of the
folder read, is never opened.

See also: :mod:`pitloom.extract.model_target` (the rule that uses it, and
re-exports its public names).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata, model_file_suffixes
from pitloom.core.clone_mark import in_remote_clone
from pitloom.core.lfs_pointer import refuse_named_pointer
from pitloom.core.path_confine import regular_file_inside
from pitloom.core.path_probe import is_missing_errno
from pitloom.extract.ai_model import LFS_POINTER_REASON, NotAModel, refusal_error
from pitloom.extract.scanner import read_model_candidate, sniff_model_format
from pitloom.extract.scanner_project import local_model_candidate, remote_reader_gate
from pitloom.messages import (
    CodedFileNotFoundError,
    CodedValueError,
)
from pitloom.messages.models import (
    MODEL_WRONG_FORMAT,
    NOT_A_MODEL_LINE,
)
from pitloom.messages.targets import (
    INPUT_NOT_FOUND,
    MODEL_FILE_NOT_FOUND_LINE,
)

__all__ = [
    "ModelFile",
    "has_model_suffix",
    "named_file",
    "named_model_file",
    "read_model_file",
    "refuse_not_a_model",
    "require_model_file",
]


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
    # shown is POSIX: a Path would write it with backslashes on Windows.
    named: str | os.PathLike[str] = path if shown is None else shown
    raise refusal_error(named, exc.model_format, str(exc)) from exc


def require_model_file(path: Path, shown: str | os.PathLike[str]) -> None:
    """Refuse the model file *path*, named on its own, when it does not
    exist (a link is followed), or is no regular file (a FIFO, whose open
    would wait for a writer; a device); the error names it *shown*. A path
    that is there but cannot be looked at is no missing file: its error
    stands.

    Raises:
        pitloom.messages.CodedFileNotFoundError: ``input-not-found``.
        pitloom.messages.CodedValueError: ``model-wrong-format``, no regular
            file.
        OSError: *path* cannot be looked at (permission denied).
    """
    try:
        found = os.stat(path)
    except OSError as exc:
        if not is_missing_errno(exc):
            raise
        raise CodedFileNotFoundError(
            INPUT_NOT_FOUND, line=MODEL_FILE_NOT_FOUND_LINE, path=shown
        ) from None
    if not stat.S_ISREG(found.st_mode):
        raise CodedValueError(MODEL_WRONG_FORMAT, line=NOT_A_MODEL_LINE, path=shown)


def read_model_file(path: Path, *, shown: str | None = None) -> AiModelMetadata:
    """Read the model file at *path*, named on its own, by the rule a scan
    applies (:func:`~pitloom.extract.scanner.read_model_candidate`), its
    messages naming it *shown* (default: *path*). In a Git URL's temporary
    clone the formats of
    :func:`~pitloom.extract.scanner_project.remote_reader_gate` are listed
    without metadata, said in one ``INFO:`` after the read.

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


def has_model_suffix(name: str | os.PathLike[str]) -> bool:
    """Whether the file name *name* has the suffix of a model file of a
    supported format (:func:`~pitloom.core.ai_metadata.model_file_suffixes`,
    the suffix :func:`~pitloom.extract.model_target.is_model_file_target`
    reads a file by): a file so named, but not a model, is refused, not
    passed over."""
    return Path(name).suffix.lower() in model_file_suffixes()


def _outside_clone_folder(path: Path, root: Path | None) -> bool:
    """Whether, in a Git URL's clone, *path* is a link (not followed) or,
    under the folder *root*, no regular file inside it spelled as on disk
    (:func:`~pitloom.core.path_confine.regular_file_inside`): it is not
    opened. Elsewhere, ``False``."""
    if not in_remote_clone():
        return False
    if os.path.islink(path):
        return True
    if root is None:
        return False
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:  # an absolute name replaced the folder
        return True
    return not regular_file_inside(root, relative)


def named_file(
    path: Path, shown: str, *, strict: bool, root: Path | None = None
) -> ModelFile | None:
    """The model file named *path*, by its content; ``None`` for a file that
    is plainly not a model, or is no regular file (gone, a folder, or in a
    Git URL's clone a link or a path out of the folder *root*, none of them
    opened), unless *strict*, which refuses it. A Git LFS pointer, or a
    header that contradicts a model suffix, is refused either way."""
    if _outside_clone_folder(path, root):
        if strict:
            raise CodedFileNotFoundError(
                INPUT_NOT_FOUND, line=MODEL_FILE_NOT_FOUND_LINE, path=shown
            )
        return None
    if not strict and not os.path.isfile(path):
        return None
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
    one); ``None`` for a file whose name no model file has
    (:func:`has_model_suffix`) and that is plainly not a model
    (``README.md``, ``pyproject.toml``), or is no regular file. Messages
    name it *shown*.

    Raises:
        pitloom.messages.CodedFileNotFoundError: *path*, with a model
            suffix, does not exist (``input-not-found``).
        ValueError: It has a model suffix and is not a model (an empty
            ``x.gguf``), or is a Git LFS pointer, or its header contradicts
            a model suffix: see :func:`refuse_not_a_model`.
        OSError: Its header cannot be read.
    """
    return named_file(path, shown, strict=has_model_suffix(path.name))
