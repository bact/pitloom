# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The files that make a directory a Python project, and whether a folder
has one, by the rule :func:`pitloom.extract.project.read_project` applies.

A leaf module: it imports nothing of Pitloom, so the model-target resolver
and the Git checkout code can both use it.

See also: :mod:`pitloom.extract.model_target` (project or model) and
:mod:`pitloom.extract.remote._git_folder` (the monorepo hint).
"""

from __future__ import annotations

import os
from typing import Final

__all__ = ["PROJECT_MARKERS", "has_project_config"]

#: Files that make a directory a Python project.
PROJECT_MARKERS: Final = ("pyproject.toml", "setup.cfg", "setup.py")


def has_project_config(folder: str | os.PathLike[str]) -> bool:
    """Whether *folder* holds one of :data:`PROJECT_MARKERS`, present as
    ``read_project`` tests it (``exists()``): a directory or a link to one
    named ``pyproject.toml`` counts, since ``read_project`` then reads it
    (and fails on it) rather than saying there is no project. Never
    raises."""
    return any(os.path.exists(os.path.join(folder, name)) for name in PROJECT_MARKERS)
