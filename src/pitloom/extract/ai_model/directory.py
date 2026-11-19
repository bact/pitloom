# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Models stored as a folder, not a file, and how one is recognised.

A folder model has no suffix and no magic bytes, so its format is decided by
a marker file the writer leaves in it (an Orbax checkpoint step holds
``_CHECKPOINT_METADATA``). Detection only asks whether the marker is there:
a regular file, never a link (a link could lead out of a Git URL's clone).
Whether its content is well-formed is the reader's question, answered with
a refusal of that model alone.

See also: :mod:`pitloom.extract.ai_model.reader` (dispatch) and
:mod:`pitloom.extract.model_target` (which folder a user's path names).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from pitloom.core.ai_metadata import AiModelFormat

__all__ = [
    "DIRECTORY_MARKERS",
    "detect_directory_format",
    "directory_models_in",
    "is_directory_model",
]

#: The marker file each folder format holds directly in its folder.
DIRECTORY_MARKERS: dict[AiModelFormat, str] = {
    AiModelFormat.JAX: "_CHECKPOINT_METADATA",
}


def _is_regular_file(path: Path) -> bool:
    """Whether *path* is a regular file itself (a link is not followed)."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def detect_directory_format(folder: Path) -> AiModelFormat:
    """The folder format of *folder*, or :attr:`AiModelFormat.UNKNOWN`: it
    is not a folder, or holds no marker file of any folder format.

    Never raises: a folder that cannot be looked into holds no marker.
    """
    if not os.path.isdir(folder):
        return AiModelFormat.UNKNOWN
    for fmt, marker in DIRECTORY_MARKERS.items():
        if _is_regular_file(folder / marker):
            return fmt
    return AiModelFormat.UNKNOWN


def is_directory_model(folder: Path) -> bool:
    """Whether *folder* is a model of a folder format."""
    return detect_directory_format(folder) != AiModelFormat.UNKNOWN


def directory_models_in(
    folder: Path, *, follow_links: bool = True, limit: int | None = None
) -> list[tuple[str, AiModelFormat]] | None:
    """The folders directly in *folder* that are models of a folder format,
    each with its format, sorted by name as plain ``str``. A folder inside is
    not looked into: the marker is the folder's own.

    Args:
        folder: The folder to list.
        follow_links: Whether a link to a folder counts (``False`` in a Git
            URL's clone, where a link could lead out of it).
        limit: Most subfolders to look at; ``None``: all.

    Returns:
        The models, or ``None`` when *folder* holds more than *limit*
        subfolders (none is looked at).

    Raises:
        OSError: *folder* cannot be listed.
    """
    with os.scandir(folder) as entries:
        names = sorted(
            entry.name
            for entry in entries
            if entry.is_dir(follow_symlinks=follow_links)
        )
    if limit is not None and len(names) > limit:
        return None
    found = []
    for name in names:
        fmt = detect_directory_format(folder / name)
        if fmt != AiModelFormat.UNKNOWN:
            found.append((name, fmt))
    return found
