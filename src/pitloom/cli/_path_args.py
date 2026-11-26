# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``type=`` of a path option that names where Pitloom writes or looks
(``-o``, ``--project-dir``, ``--id-registry``): an empty one is refused as
the option's own error (``option-invalid``), never read as ``.``.

An empty *input* path (a command's positional target) is ``input-not-found``
instead, said where the target is probed.
"""

from __future__ import annotations

import argparse

from pitloom.core.given_path import TypedPath
from pitloom.messages.config import must_be

__all__ = ["non_empty_path"]


def non_empty_path(text: str) -> TypedPath:
    """*text* as a :class:`~pitloom.core.given_path.TypedPath`, keeping its
    spelling.

    Raises:
        argparse.ArgumentTypeError: *text* is empty (``must be a non-empty
            string, got ''``).
    """
    if not text:
        raise argparse.ArgumentTypeError(must_be("non-empty", got=text))
    return TypedPath(text)
