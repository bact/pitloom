# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``existing_model_path``: a resolve that says the path is missing (Python
3.10's Windows ``resolve()`` lets ``WinError 123`` escape) is ``None``;
another failure propagates.

See also: tests/cli/test_long_names.py.
"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from pitloom.cli.commands.utils import existing_model_path

pytestmark = pytest.mark.platform


class _InvalidName(OSError):
    """What Windows raises for an invalid name: ``EINVAL``, ``WinError 123``."""

    winerror = 123


@pytest.mark.parametrize(
    ("error", "missing"),
    [
        (_InvalidName(errno.EINVAL, "bad name"), True),
        (PermissionError(errno.EACCES, "denied"), False),
    ],
    ids=["winerror-123", "denied"],
)
def test_resolve_failure(
    error: OSError,
    missing: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given = tmp_path / "missing" / "m.gguf"

    def fail(_self: Path, strict: bool = False) -> Path:
        del strict
        raise error

    monkeypatch.setattr(type(given), "resolve", fail)
    if missing:
        assert existing_model_path(given) is None
    else:
        with pytest.raises(PermissionError):
            existing_model_path(given)
