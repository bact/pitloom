# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_ai_model_header`` on a path that cannot be opened: Windows raises
``PermissionError`` for a directory (absence, not denial); a real denial
is raised.

See also: test_ai_model_header.py (the header read itself).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest

from pitloom.extract.ai_model import reader


def _denied(tmp_path: Path) -> Path:
    """A regular file whose ``open`` raises ``PermissionError``."""
    (tmp_path / "m.gguf").write_bytes(b"GGUF")

    # pylint: disable-next=too-few-public-methods
    class Denied(type(tmp_path)):  # type: ignore[misc]
        """A path that is a file but cannot be opened."""

        def open(self, *args: Any, **kwargs: Any) -> NoReturn:
            raise PermissionError("denied")

    return Denied(tmp_path / "m.gguf")


@pytest.mark.parametrize(
    ("is_dir", "expected"), [(True, b""), (False, None)], ids=["directory", "denied"]
)
def test_a_permission_error_is_absence_only_for_a_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    is_dir: bool,
    expected: bytes | None,
) -> None:
    path = _denied(tmp_path)
    monkeypatch.setattr(
        reader,
        "os",
        SimpleNamespace(stat=os.stat, path=SimpleNamespace(isdir=lambda _p: is_dir)),
    )
    if expected is None:
        with pytest.raises(PermissionError):
            reader.read_ai_model_header(path)
    else:
        assert reader.read_ai_model_header(path) == expected
