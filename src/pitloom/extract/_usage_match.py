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
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "UsageModel",
    "after_first_separator",
    "format_template",
    "join_path",
    "join_paths",
    "matches",
    "percent_template",
]

#: A path that starts at a root: ``/x``, ``C:/x`` (separators are read as
#: ``/`` first).
_ROOTED: Final = re.compile(r"^(?:[A-Za-z]:)?/")
_ROOT_START: Final = re.compile(r"^(?:[A-Za-z]:)?[/\\]")
#: A drive (``C:``) or the home directory: a leading component that says where
#: the path starts, not what directory it holds.
_START: Final = re.compile(r"^(?:~|[A-Za-z]:)$")
#: A component with a format placeholder: not known.
_UNKNOWN: Final = re.compile(r"[%{]")
#: A part of a template that is not known, until the template is cut after it.
_HOLE: Final = "\x00"
_FORMATTER: Final = string.Formatter()
#: The name of a ``str.format`` field ends where its attribute or index starts.
_FIELD_HEAD: Final = re.compile(r"[.\[]")
_PERCENT_SPEC: Final = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?(?P<flags>[#0\- +]*)(?P<width>\d+|\*)?"
    r"(?:\.(?P<prec>\d+|\*))?[hlL]?(?P<conv>[a-zA-Z%])"
)


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


def after_first_separator(text: str) -> str | None:
    """What follows the first separator of *text*, ``None`` when there is
    none or nothing follows: the first component may be only the end of one
    (the text came after something not known), so it is left out."""
    for index, char in enumerate(text):
        if char in "/\\":
            return text[index + 1 :].lstrip("/\\") or None
    return None


def join_path(left: str | None, right: str) -> str:
    """*right* appended to *left* as a path component; a rooted *right*
    replaces it, as in ``os.path.join``."""
    if left is None or _ROOT_START.match(right):
        return right
    head = left.rstrip("/\\")
    return f"{head}/{right}"


def join_paths(parts: Sequence[str | None]) -> str | None:
    """*parts* joined; what comes after the last part that is not known.
    ``None`` when the last part is not known."""
    joined: str | None = None
    for part in parts:
        joined = None if part is None else join_path(joined, part)
    return joined


def _filled(rendered: str) -> str | None:
    """A rendered template as a path: after the last unknown part
    (:data:`_HOLE`) only what follows its first separator is known."""
    if _HOLE in rendered:
        return after_first_separator(rendered.rsplit(_HOLE, 1)[-1])
    return rendered or None


def _named_arg(
    head: str, args: Sequence[str | None], kwargs: Mapping[str, str | None]
) -> str | None:
    """The argument a ``str.format`` field names: by position (ASCII digits
    only: ``int("\u00b2")`` raises) or by keyword."""
    if head.isascii() and head.isdigit():
        return args[int(head)] if int(head) < len(args) else None
    return kwargs.get(head)


def format_template(
    template: str,
    args: Sequence[str | None],
    kwargs: Mapping[str, str | None],
) -> str | None:
    """``template.format(*args, **kwargs)`` with known arguments filled in.
    A positional argument past the end of *args* (what follows a ``*args``
    that is not known) is not known; neither is a field with an attribute,
    an index, a conversion other than ``!s`` or a format spec."""
    try:
        fields = list(_FORMATTER.parse(template))
    except ValueError:
        return None
    out: list[str] = []
    index = 0
    for literal, name, spec, conversion in fields:
        out.append(literal)
        if name is None:
            continue
        head = _FIELD_HEAD.split(name, 1)[0]
        if head == "":
            value = args[index] if index < len(args) else None
            index += 1
        else:
            value = _named_arg(head, args, kwargs)
        if "{" in (spec or ""):
            index = len(args)
        plain = head == name and conversion in (None, "s") and spec in (None, "", "s")
        out.append(value if plain and value is not None else _HOLE)
    return _filled("".join(out))


def percent_template(
    template: str, values: Sequence[str | None] | Mapping[str, str | None]
) -> str | None:
    """``template % values`` with known values filled in: positional ones
    for a sequence, ``%(name)s`` ones for a mapping. Only a bare ``%s`` takes
    a value; ``%%`` is a percent sign; a ``*`` width takes an argument and
    leaves the later ones not known."""
    index = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal index
        conv, key = match.group("conv"), match.group("key")
        if conv == "%":
            return "%"
        value: str | None = None
        if isinstance(values, Mapping):
            value = values.get(key) if key is not None else None
        elif key is None:
            value = values[index] if index < len(values) else None
            index += 1
        if "*" in match.group(0):
            index = len(values)
            return _HOLE
        bare = conv == "s" and not any(
            match.group(group) for group in ("flags", "width", "prec")
        )
        return value if bare and value is not None else _HOLE

    return _filled(_PERCENT_SPEC.sub(_replace, template))


def _components(path: str) -> list[str]:
    """*path*'s components, ``.`` and empty ones dropped, ``..`` applied to
    the known component before it, and anything before an unknown placeholder
    cleared."""
    found: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if _UNKNOWN.search(part):
            found = [part]
        elif part == "..":
            if found and not _UNKNOWN.search(found[-1]):
                found.pop()
        elif not found and _START.match(part):
            continue
        else:
            found.append(part)
    return found


def matches(text: str, model: UsageModel) -> bool:
    """Whether *text*, a path (or the end of one) found in code, names
    *model*: see the module docstring."""
    if model.name not in text:
        return False
    norm = text.replace("\\", "/")
    if norm.endswith("/"):
        return False
    rooted = bool(_ROOTED.match(norm)) or norm.startswith("~")
    parts = _components(norm)
    if parts and _UNKNOWN.search(parts[0]):
        parts, rooted = parts[1:], False
    if not parts or parts[-1] != model.name:
        return False
    if not rooted:
        return len(parts) == 1 or any(
            _components(path)[-len(parts) :] == parts for path in model.paths
        )
    for path in model.paths:
        own = _components(path)
        if own == parts or (len(own) > 1 and parts[-len(own) :] == own):
            return True
    return False
