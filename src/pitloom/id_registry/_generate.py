# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Index the files under a project into an :class:`IdRegistry`.

See also: :meth:`pitloom.id_registry._registry.IdRegistry.generate`, which
delegates here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from pitloom.core.path_confine import inside_ancestor
from pitloom.id_registry._types import (
    AI_PACKAGE_TYPE,
    FILE_TYPE,
    _iter_files,
    _unstorable_name_error,
    sha256_file,
    warn_unreadable_file,
)
from pitloom.logging_config import loggable

if TYPE_CHECKING:
    from pitloom.id_registry._registry import IdRegistry

log = logging.getLogger("pitloom.id_registry")

__all__ = ["index_files"]


def _project_relative(file_path: Path, project_root: Path) -> str:
    """*file_path* below *project_root* as POSIX text: lexically first, with
    ``..`` collapsed (an in-project symlink to a directory outside keeps its
    project path), else by realpath of both (a project root spelled through
    a symlink). A file outside the project is a ``ValueError`` naming both."""
    lexical = Path(os.path.normpath(file_path))
    try:
        return lexical.relative_to(os.path.normpath(project_root)).as_posix()
    except ValueError:
        pass
    parent = Path(os.path.realpath(lexical.parent))
    ancestor = inside_ancestor(parent, Path(os.path.realpath(project_root)))
    if ancestor is None:
        raise ValueError(
            f"ID registry: {loggable(os.fspath(file_path))} is outside the "
            f"project root {loggable(os.fspath(project_root))}"
        )
    return (parent.relative_to(ancestor) / lexical.name).as_posix()


def index_files(
    registry: IdRegistry,
    paths: list[Path],
    project_root: Path,
    exclude: Path | None,
    *,
    explicit: bool = True,
) -> None:
    """Register the files under *paths* (and their AI models) in *registry*,
    except the *exclude* file; see :meth:`IdRegistry.generate`. *explicit*
    is false for implicit default roots (see
    :func:`~pitloom.id_registry._types._iter_files`)."""
    # pylint: disable=import-outside-toplevel,cyclic-import
    from pitloom.extract.ai_model import AiModelFormat, detect_ai_model_format
    from pitloom.extract.scanner import is_model_candidate_name

    models: dict[str, list[str]] = {}
    for file_path in _iter_files(paths, project_root, exclude, explicit=explicit):
        try:
            sha256 = sha256_file(file_path)
        except OSError as exc:
            warn_unreadable_file(file_path, project_root, exc)
            continue
        rel_path = _project_relative(file_path, project_root)
        name_error = _unstorable_name_error(file_path, project_root)
        if name_error is not None:
            warn_unreadable_file(file_path, project_root, name_error)
            continue
        registry.register(FILE_TYPE, rel_path, sha256=sha256)

        # The scan's rule (suffix filter, then header), so a model is
        # registered for the files a scan lists as models, and only those.
        if (
            is_model_candidate_name(file_path.name)
            and detect_ai_model_format(file_path) != AiModelFormat.UNKNOWN
        ):
            models.setdefault(file_path.stem, []).append(sha256)
    for stem, hashes in models.items():
        if len(hashes) == 1:
            registry.register(AI_PACKAGE_TYPE, stem, sha256=hashes[0])
            continue
        log.info(
            "ID registry: %d model files share the name %s; %s",
            len(hashes),
            stem,
            "its new entry is not content-gated"
            if registry.get(AI_PACKAGE_TYPE, stem) is None
            else "its entry is left as is",
        )
        registry.register(AI_PACKAGE_TYPE, stem)
