# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared ``tomllib``/``tomli`` compat import and raw TOML-file read.

See also: :mod:`pitloom.extract._setuptools` (``pyproject.toml`` reads),
:mod:`pitloom.extract._poetry_lock` (``poetry.lock`` reads) -- both build
on :func:`load_toml_file` instead of duplicating the version-gated import
and the ``open()``/``tomllib.load()`` pair. Exception handling (which
errors to log, at what level, and what to return) stays with each caller,
since that policy differs per file (e.g. a missing ``pyproject.toml`` vs.
a missing, purely-optional ``poetry.lock``).
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

__all__ = ["TOMLDecodeError", "load_toml_file"]

TOMLDecodeError = tomllib.TOMLDecodeError


def load_toml_file(path: Path) -> dict[str, object]:
    """Read and parse *path* as TOML.

    Propagates ``OSError`` (including ``FileNotFoundError``) and
    :data:`TOMLDecodeError` to the caller -- callers decide how to log
    and what fallback to return for each.
    """
    with open(path, "rb") as f:
        return tomllib.load(f)
