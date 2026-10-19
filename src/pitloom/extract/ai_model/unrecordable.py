# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The G7 honesty notice: one line per model naming the G7 elements whose
value was read but that SPDX 3.0.1 has no property for.

A value the source does not carry is never named: absent data stays silent.
The notice is on stderr only and never changes the SBOM.

See also: :func:`pitloom.extract.ai_model.limits.settle_read_text` (its one
call site, reached once per model by every surface).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.logging_config import loggable

_log = logging.getLogger(__name__)

#: The level of every notice line.
NOTICE_LEVEL = logging.INFO

#: The shared text after the ``FORMAT=``/``FILE=`` prefix.
NOTICE_TEXT = "no SPDX 3.0.1 property"


@dataclass(frozen=True)
class Unrecordable:
    """A G7 element with no SPDX 3.0.1 property that a reader can read.

    Attributes:
        element: The element's id in the G7-to-SPDX 3.0.1 SSSOM mapping
            (``model-architecture``).
        written_in: The broader SPDX property the value is written in, or
            ``None`` when it is not written at all.
        read: Whether a model as read holds a value for the element.
    """

    element: str
    written_in: str | None
    read: Callable[[AiModelMetadata], bool]

    def label(self) -> str:
        """The element as the notice names it."""
        if self.written_in is None:
            return f"{self.element} (not recorded)"
        return f"{self.element} (written in {self.written_in})"


#: Every G7 element a reader reads that SPDX 3.0.1 has no property for. The
#: assembler appends ``architecture`` to ``ai_typeOfModel`` after the type.
UNRECORDABLE: tuple[Unrecordable, ...] = (
    Unrecordable(
        "model-architecture", "ai_typeOfModel", lambda meta: bool(meta.architecture)
    ),
)


def log_unrecordable(fmt: str, where: str, read: Iterable[Unrecordable]) -> None:
    """The one notice line for *read*, sorted by element, naming the model
    (``FORMAT=<fmt> FILE=<where>``); nothing when *read* is empty."""
    labels = [entry.label() for entry in sorted(read, key=lambda e: e.element)]
    if labels:
        _log.log(
            NOTICE_LEVEL,
            "FORMAT=%s FILE=%s: %s: %s",
            fmt,
            loggable(where),
            NOTICE_TEXT,
            ", ".join(labels),
        )


def notice_unrecordable(meta: AiModelMetadata, fmt: str, where: str) -> None:
    """:func:`log_unrecordable` for the elements *meta* holds a value for."""
    log_unrecordable(fmt, where, (e for e in UNRECORDABLE if e.read(meta)))
