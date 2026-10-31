# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Whether a path found in Python code names a model file.

A model is found by the file name its scan recorded. A path found in code
names it when its last component is that name and the directories before it,
if any, end the model's own path. ``"model.ftz"`` names every model called
``model.ftz``; ``"data/model.ftz"`` only one under a ``data`` directory. A
part that is not known (``%s``, ``{}``, a part of an f-string) hides the
directories before it.

See also: :mod:`pitloom.extract._usage_ast` (which finds the paths).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = ["UsageModel", "matches"]

#: A path that starts at a root: ``/x``, ``C:/x`` (separators are read as
#: ``/`` first).
_ROOTED: Final = re.compile(r"^(?:[A-Za-z]:)?/")
#: A drive (``C:``), the home directory, or a parent step: leading
#: components that say where the path starts, not what it holds.
_START: Final = re.compile(r"^(?:\.\.|~|[A-Za-z]:)$")
#: A component with a format placeholder: not known.
_UNKNOWN: Final = re.compile(r"[%{]")


@dataclass(frozen=True)
class UsageModel:
    """A model file as the usage scan looks for it.

    Attributes:
        name: The file name, with no directory.
        paths: The paths the model has in the SBOM (its distribution path and
            its project path), POSIX separators.
    """

    name: str
    paths: tuple[str, ...]


def _components(path: str) -> list[str]:
    """*path*'s components, ``.`` and empty ones dropped, ``..`` applied to
    the component before it (a leading ``..`` stays)."""
    found: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == ".." and found and found[-1] != "..":
            found.pop()
        else:
            found.append(part)
    return found


def matches(text: str, model: UsageModel) -> bool:
    """Whether *text*, a path (or the end of one) found in code, names
    *model*: see the module docstring."""
    norm = text.replace("\\", "/")
    rooted = bool(_ROOTED.match(norm)) or norm.startswith("~")
    parts = _components(norm)
    for index in range(len(parts) - 1, -1, -1):
        if _UNKNOWN.search(parts[index]):
            parts, rooted = parts[index + 1 :], False
            break
    while parts and _START.match(parts[0]):
        parts.pop(0)
    if not parts or parts[-1] != model.name:
        return False
    if len(parts) == 1:
        return True
    for path in model.paths:
        own = _components(path)
        if own[-len(parts) :] == parts:
            return True
        if rooted and len(own) <= len(parts) and parts[-len(own) :] == own:
            return True
    return False
