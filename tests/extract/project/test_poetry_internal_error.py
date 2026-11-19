# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An ``InternalError`` from the Poetry gap-fill is not swallowed.

An ``InternalError`` is a ``ValueError``; without a ``poetry.lock`` the
caller drops a failed gap-fill quietly, so a bug must not be mistaken for one.

See also: ``tests/extract/project/test_poetry_pyproject.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.extract.project.pyproject import _try_read_poetry

pytestmark = pytest.mark.platform


def test_an_internal_error_from_the_gap_fill_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise InternalError("a bug")

    monkeypatch.setattr(
        "pitloom.extract.project.pyproject.extract_poetry_metadata", boom
    )
    with pytest.raises(InternalError, match="^a bug$"):
        _try_read_poetry({"tool": {"poetry": {"name": "x"}}}, tmp_path)
