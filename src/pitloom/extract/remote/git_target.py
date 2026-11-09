# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the SBOM of a fetched Git URL describes: the project of the folder
it names, or one AI model file (the one it names, or the folder's only one),
by the rule of :func:`pitloom.extract.model_target.resolve_sbom_target`.

Not imported by :mod:`pitloom.extract.remote`: it needs the model scanner,
which a caller fetching a project only does not.

See also: :mod:`pitloom.extract.remote.git` (the fetch) and
:mod:`pitloom.extract.model_target` (the rule for a local folder).
"""

from __future__ import annotations

import os
from typing import Final

from pitloom.core.project_markers import has_project_config
from pitloom.core.url_masking import sanitize_url
from pitloom.extract.model_target import (
    MODEL,
    PROJECT,
    SbomTarget,
    has_model_suffix,
    resolve_sbom_target,
    say_reading_folder,
)
from pitloom.extract.remote._git_folder import checkout_has_file, subproject_hint
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.scanner import is_model_candidate_name
from pitloom.logging_config import loggable
from pitloom.messages import (
    GIT_FILE_IS_LINK_LINE,
    GIT_FILE_NOT_FOUND_LINE,
    INPUT_NOT_FOUND,
    MODEL_FILES_LINE,
    NO_SBOM_TARGET,
    PROJECT_NOT_FOUND_MODEL_FILES,
    CodedValueError,
    code_of,
)

__all__ = ["resolve_git_target"]

#: How many model-like file names a refusal names before "and N more".
_NAMES_SHOWN: Final = 5


def _named_file(checkout: GitCheckout, mode: str) -> str:
    """The file the URL named, to be read (``""``: none, or the folder is
    read instead). Under ``PROJECT`` it is passed on unread. Else it is read
    only when it is a regular file of the folder, inside the clone and
    spelled as on disk (:func:`checkout_has_file`); nothing outside the
    clone is opened. Any other name (gone, a folder, a link, out of the
    clone) is refused under ``MODEL`` or for a name with a model suffix;
    under ``AUTO`` the folder is read instead, said in one ``INFO:``.

    Raises:
        RemoteSourceError: ``git.path-not-found`` (its ``pitloom_code``
            ``input-not-found``), its line saying whether the name is a
            link.
    """
    named = checkout.file
    if not named or mode == PROJECT:
        return named
    link = os.path.islink(os.path.join(checkout.folder, named))
    if not link and checkout_has_file(checkout.folder, named):
        return named
    shown = f"{checkout.subdir}/{named}".lstrip("/")
    if mode == MODEL or has_model_suffix(named):
        line = GIT_FILE_IS_LINK_LINE if link else GIT_FILE_NOT_FOUND_LINE
        raise RemoteSourceError(
            "git.path-not-found",
            line.render({"path": shown}),
            pitloom_code=INPUT_NOT_FOUND.code,
        )
    say_reading_folder(shown)
    return ""


def _model_like_names(folder: str) -> list[str]:
    """The names of *folder*'s regular files (links not followed) whose
    suffix could be a model's, sorted as plain ``str``; no file is read."""
    with os.scandir(folder) as entries:
        return sorted(
            entry.name
            for entry in entries
            if entry.is_file(follow_symlinks=False)
            and is_model_candidate_name(entry.name)
        )


def _refuse_model_only_folder(checkout: GitCheckout, subject: str) -> None:
    """For a project only: refuse a folder with no project config whose files
    may be AI models, with a hint to ask for a model SBOM. A folder with
    projects below it is left to the project read, whose failure names them
    (:meth:`~pitloom.extract.remote.git.GitCheckout.explaining_failures`).

    Raises:
        RemoteSourceError: ``git.no-project`` (its ``pitloom_code``
            ``project-not-found/model-files``).
    """
    if has_project_config(checkout.folder):
        return
    names = _model_like_names(checkout.folder)
    if not names or subproject_hint(checkout.folder, checkout.whole_repository):
        return
    shown = ", ".join(loggable(name) for name in names[:_NAMES_SHOWN])
    more = len(names) - _NAMES_SHOWN
    if more > 0:
        shown += f" and {more} more"
    raise RemoteSourceError(
        "git.no-project",
        MODEL_FILES_LINE.render({"path": subject, "files": shown}),
        pitloom_code=PROJECT_NOT_FOUND_MODEL_FILES.code,
    )


def _folder_subject(subject: str, file: str) -> str:
    """The URL *subject* of a project read without the file the URL named: a
    project read takes the folder, so a refusal names the folder, not the
    file. *subject* is kept when it does not end with the file's name (a
    query-style page)."""
    if not file:
        return subject
    tail = "/" + file
    return subject[: -len(tail)] if subject.endswith(tail) else subject


def resolve_git_target(checkout: GitCheckout, mode: str, url: str) -> SbomTarget:
    """What the SBOM of the fetched *checkout* of *url* describes under
    *mode* (:data:`~pitloom.extract.model_target.AUTO`, ``PROJECT`` or
    ``MODEL``), as :func:`~pitloom.extract.model_target.resolve_sbom_target`
    decides for its folder and the file the URL named, each file named by
    its path in the repository and the folder by *url* without credentials.

    Called within :meth:`~pitloom.extract.remote.git.GitCheckout.reading`, so
    a link is not followed, a Git LFS pointer is said as in a clone and a
    reader a hostile file could crash or hang (fastText, GGUF, HDF5, ONNX,
    PyTorch) is not run, on a model target and on the model files of a
    project target alike.

    The named file is read only when it is a regular file of the folder
    inside the clone (:func:`_named_file`): a name leading out of it is
    never opened, whatever its suffix.

    Raises:
        RemoteSourceError: ``git.path-not-found`` (the named file is no
            file of the folder, under ``MODEL`` or, under ``AUTO``, for a
            name with a model suffix: any other name reads the folder;
            ``input-not-found``) or ``git.no-project``: a project only, of a
            folder whose files may be models
            (``project-not-found/model-files``); or neither a project nor a
            model, with projects in folders below (its ``pitloom_code``
            ``project-or-model-not-found``).
        pitloom.messages.CodedValueError: as
            :func:`~pitloom.extract.model_target.resolve_sbom_target`.
        FileNotFoundError: The project read finds no project config.
        OSError: The folder cannot be listed.
    """
    subject = sanitize_url(url.strip())
    if mode == PROJECT:
        subject = _folder_subject(subject, checkout.file)
    named = _named_file(checkout, mode)
    if mode == PROJECT:
        _refuse_model_only_folder(checkout, subject)
    try:
        return resolve_sbom_target(
            checkout.folder,
            subject=subject,
            file=named,
            mode=mode,
            shown_prefix=checkout.subdir,
        )
    except CodedValueError as exc:
        if code_of(exc) != NO_SBOM_TARGET.code:
            raise
        hint = subproject_hint(checkout.folder, checkout.whole_repository)
        if not hint:
            raise
        raise RemoteSourceError(
            "git.no-project", f"{exc}{hint}", pitloom_code=NO_SBOM_TARGET.code
        ) from exc
