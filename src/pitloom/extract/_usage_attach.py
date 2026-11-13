# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What one Python script does with the models it names: the part of the
usage scan that works on a script's text, after the scanner has read it.

See also: :mod:`pitloom.extract.scanner` (``attach_usage_references``: which
scripts are read, and the caps), :mod:`pitloom.extract._usage_ast` (the tree
walk), :mod:`pitloom.extract._usage_parse` (the parse) and
:mod:`pitloom.messages._usage_unparseable` (the two lines said for a script
that cannot be parsed).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.model_usage import ModelUsage, combine_access
from pitloom.core.project import project_relative_or_fallback
from pitloom.extract._usage_ast import find_usages
from pitloom.extract._usage_match import UsageModel
from pitloom.extract._usage_parse import PARSE_ERRORS, parse_python, python_version
from pitloom.logging_config import loggable
from pitloom.messages import emit
from pitloom.messages.models import (
    USAGE_UNPARSEABLE,
    USAGE_UNPARSEABLE_MENTION,
)

if TYPE_CHECKING:
    from pitloom.extract.scanner import UsageSource

log = logging.getLogger("pitloom.extract.scanner")

__all__ = ["attach_from_source", "usage_models"]


def usage_models(
    models: Sequence[AiModelMetadata],
) -> list[tuple[AiModelMetadata, UsageModel]]:
    """Each of *models* that has a file name, with how a script names it."""
    found: list[tuple[AiModelMetadata, UsageModel]] = []
    for meta in models:
        info = meta.format_info
        if info.file_name:
            rel = info.file_path_relative or ""
            phys = project_relative_or_fallback(info.physical_path or "", rel)
            paths = tuple(dict.fromkeys(p for p in (rel, phys) if p))
            found.append((meta, UsageModel(info.file_name, paths)))
    return found


def _parse_failure(exc: BaseException) -> ValueError:
    """What stopped the parse of a script, as the line says it: the
    interpreter's message and line for a syntax error, else its own words
    (a nesting error has none, and a syntax error's text names no file)."""
    if isinstance(exc, SyntaxError):
        msg = exc.msg or type(exc).__name__
        where = f" (line {exc.lineno})" if exc.lineno else ""
        return ValueError(f"{msg}{where}")
    if isinstance(exc, (MemoryError, RecursionError)):
        return ValueError("nested too deeply")
    return ValueError(str(exc))


def attach_from_source(
    source: UsageSource,
    content: str,
    candidates: Sequence[tuple[AiModelMetadata, UsageModel]],
) -> None:
    """Record what the script *content* does with each model it names.

    Only a script whose text holds a model's file name is parsed. One that
    cannot be parsed makes no claim: the name in its text may be a comment or
    a message. It is warned of once, and each model it names is said at
    ``INFO:``.
    """
    named = [(meta, usage) for meta, usage in candidates if usage.name in content]
    if not named:
        return
    try:
        tree = parse_python(content)
    except PARSE_ERRORS as exc:
        emit(
            log,
            USAGE_UNPARSEABLE,
            logging.WARNING,
            file=source.physical_path,
            python=python_version(),
            failure=_parse_failure(exc),
        )
        for name in dict.fromkeys(usage.name for _, usage in named):
            emit(
                log,
                USAGE_UNPARSEABLE_MENTION,
                logging.INFO,
                file=source.physical_path,
                name=name,
            )
        return
    accesses = find_usages(tree, [usage for _, usage in named])
    for (meta, usage), found in zip(named, accesses, strict=True):
        if found:
            meta.usage_files.append(
                ModelUsage(source.distribution_path, combine_access(found))
            )
            log.debug(
                "Found usage of %s inside %s",
                loggable(usage.name),
                loggable(source.distribution_path),
            )
