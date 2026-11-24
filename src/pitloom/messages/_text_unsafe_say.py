# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying ``text-unsafe``: :func:`warn_text_unsafe`.

See also: :mod:`pitloom.messages._text_unsafe` (the entry).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from pitloom.messages._emit import emit
from pitloom.messages._text_unsafe import TEXT_UNSAFE


def warn_text_unsafe(
    log: logging.Logger, properties: Sequence[str], **where: Any
) -> None:
    """The one ``WARNING:`` (``text-unsafe``) that *properties* (sorted, once
    each) had their display text escaped; *where* names the subject: a
    model by ``format`` and ``file``, or a loom dataset by ``dataset``.

    Raises:
        ValueError: *where* names neither, or a value does not have its
            field's shape.
    """
    emit(log, TEXT_UNSAFE, logging.WARNING, properties=list(properties), **where)
