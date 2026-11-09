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
    PROJECT,
    SbomTarget,
    resolve_sbom_target,
)
from pitloom.extract.remote._git_folder import checkout_has_file, subproject_hint
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import GitCheckout
from pitloom.extract.scanner import is_model_candidate_name
from pitloom.logging_config import loggable
from pitloom.messages import (
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


def _named_file(checkout: GitCheckout) -> None:
    """Refuse the file the URL named when it is no regular file of the
    folder read (gone, a folder, or a link: a link is not followed).

    Raises:
        RemoteSourceError: ``git.path-not-found`` (its ``pitloom_code``
            ``input-not-found``).
    """
    path = os.path.join(checkout.folder, checkout.file)
    if not os.path.islink(path) and checkout_has_file(checkout.folder, checkout.file):
        return
    shown = f"{checkout.subdir}/{checkout.file}".lstrip("/")
    raise RemoteSourceError(
        "git.path-not-found",
        GIT_FILE_NOT_FOUND_LINE.render({"path": shown}),
        pitloom_code=INPUT_NOT_FOUND.code,
    )


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


def resolve_git_target(checkout: GitCheckout, mode: str, url: str) -> SbomTarget:
    """What the SBOM of the fetched *checkout* of *url* describes under
    *mode* (:data:`~pitloom.extract.model_target.AUTO`, ``PROJECT`` or
    ``MODEL``), as :func:`~pitloom.extract.model_target.resolve_sbom_target`
    decides for its folder and the file the URL named, each file named by
    its path in the repository and the folder by *url* without credentials.

    Called within :meth:`~pitloom.extract.remote.git.GitCheckout.reading`, so
    a link is not followed, a Git LFS pointer is said as in a clone and a
    native-library reader is not run.

    Raises:
        RemoteSourceError: ``git.path-not-found`` (the named file is no
            file of the folder, unless *mode* is ``PROJECT``;
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
    if checkout.file and mode != PROJECT:
        _named_file(checkout)
    if mode == PROJECT:
        _refuse_model_only_folder(checkout, subject)
    try:
        return resolve_sbom_target(
            checkout.folder,
            subject=subject,
            file=checkout.file,
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
