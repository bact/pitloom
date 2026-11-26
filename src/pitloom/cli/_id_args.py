# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The argparse ``type=`` callables of ``loom id``'s options: each refuses
a value the argparse way (``argument <option>: ...``, exit code 2).

See also: :mod:`pitloom.cli.id` (the commands) and
:mod:`pitloom.cli._path_args` (an empty path option).
"""

from __future__ import annotations

import argparse
import re
import unicodedata

from packaging.utils import InvalidName, canonicalize_name

from pitloom.cli._path_args import non_empty_path
from pitloom.core.given_path import TypedPath
from pitloom.core.iri import (
    NAMESPACE_CREDENTIALS,
    namespace_problem,
    require_namespace_iri,
)
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
)

__all__ = ["entity_arg", "namespace_arg", "registry_file_arg"]

#: The TYPEs ``id generate -e NAME:TYPE`` accepts: the types a lookup reads.
_ENTITY_TYPES: tuple[str, ...] = (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
)
#: The shape of an SPDX 3 compact type name (``prefix_ClassName``).
_COMPACT_TYPE = re.compile(r"[a-z]+_[A-Z][A-Za-z0-9]*")


def namespace_arg(text: str) -> str:
    """``type=`` callable for ``--namespace``: validate through
    :func:`~pitloom.core.iri.require_namespace_iri`. A namespace holding
    credentials passes here: the command refuses it as the library does
    (:func:`~pitloom.id_registry.require_registry_namespace`,
    ``credentials-unsafe/registry``), a code argparse's frame cannot carry."""
    if namespace_problem(text) == NAMESPACE_CREDENTIALS:
        return text
    try:
        return require_namespace_iri(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def registry_file_arg(text: str) -> TypedPath:
    """``type=`` callable for ``-o``: a non-empty file path
    (:func:`~pitloom.cli._path_args.non_empty_path`), never ``-``: a
    registry is not written to stdout, and ``-`` would name a file called
    ``-``. The path keeps the spelling typed, for a message to name it."""
    if text == "-":
        raise argparse.ArgumentTypeError("'-' (stdout) is not supported")
    return non_empty_path(text)


def entity_arg(text: str) -> tuple[str, str]:
    """``type=`` callable for ``-e NAME[:TYPE]``: ``(TYPE, NAME)``.

    Split at the last ``:`` only when what follows is one of
    :data:`_ENTITY_TYPES`, so the ``:`` of a URL or a drive letter stays in
    NAME. A typo is refused, never silently made part of NAME: a trailing
    ``:``, a suffix shaped like a compact type, a known one in another case
    or with whitespace around it, a control character (a newline) anywhere,
    and an empty or blank NAME, or package name before a
    ``software_Package``'s ``@VERSION``, or one that is no PEP 508 name
    (:func:`_name_problem`).
    """
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise argparse.ArgumentTypeError(f"control character in {text!r}")
    name, _, suffix = text.rpartition(":")
    if suffix in _ENTITY_TYPES:
        type_name = suffix
    elif (
        text.endswith(":")
        or _COMPACT_TYPE.fullmatch(suffix.strip())
        or suffix.strip().lower() in {known.lower() for known in _ENTITY_TYPES}
    ):
        raise argparse.ArgumentTypeError(
            f"unknown TYPE {suffix!r} (one of: {', '.join(_ENTITY_TYPES)})"
        )
    else:
        name, type_name = text, AI_PACKAGE_TYPE
    problem = _name_problem(type_name, name)
    if problem is not None:
        raise argparse.ArgumentTypeError(f"{problem[0]} in {text!r}{problem[1]}")
    return type_name, name


def _name_problem(type_name: str, name: str) -> tuple[str, str] | None:
    """``(problem, hint)`` for a NAME that is empty or blank, or for a
    ``software_Package`` NAME (before its ``@VERSION``) that is blank or no
    PEP 508 name (a specifier, a space: no package a lookup reads has it),
    with the spelling a version takes when ``==`` was typed; else ``None``."""
    stated = name.partition("@")[0] if type_name == PACKAGE_TYPE else name
    if not stated.strip():
        return "no NAME", ""
    if type_name != PACKAGE_TYPE:
        return None
    try:
        canonicalize_name(stated, validate=True)
    except InvalidName:
        return "invalid package NAME", "; write NAME@VERSION" if "==" in name else ""
    return None
