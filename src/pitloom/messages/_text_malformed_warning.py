# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one ``WARNING:`` for text holding lone surrogates
(:func:`warn_lone_surrogates`).

See also: :mod:`pitloom.messages._text_malformed` (the entry).
"""

from __future__ import annotations

import logging
import os

from pitloom.messages._emit import emit
from pitloom.messages._text_malformed import FILE_LINE, MODEL_LINE, TEXT_MALFORMED


def warn_lone_surrogates(
    log: logging.Logger,
    *,
    file: str | os.PathLike[str],
    model_format: str | None = None,
) -> None:
    """The one ``WARNING:`` on *log* that text read from *file* (as the
    line names it, raw: the line escapes it) held lone surrogates, now
    written as text, ``[text-malformed]``; *model_format* names the format
    of a model file first. Each caller says it once per file."""
    if model_format is None:
        emit(log, TEXT_MALFORMED, logging.WARNING, line=FILE_LINE, file=file)
    else:
        emit(
            log,
            TEXT_MALFORMED,
            logging.WARNING,
            line=MODEL_LINE,
            file=file,
            format=model_format,
        )
