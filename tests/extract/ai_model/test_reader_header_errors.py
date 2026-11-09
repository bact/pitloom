# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``read_ai_model_header`` on a path that cannot be opened: Windows raises
``PermissionError`` for a directory (absence, not denial); a real denial
is raised; a FIFO is not opened (the open would wait for a writer).

See also: test_ai_model_header.py (the header read itself).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest

from pitloom.extract.ai_model import reader

#: Whether a FIFO can be made here (not on Windows).
_HAS_FIFO = hasattr(os, "mkfifo")


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


@pytest.mark.skipif(not _HAS_FIFO, reason="no FIFO on this platform")
def test_a_fifo_is_not_opened(tmp_path: Path) -> None:
    """Called directly (no caller's own check before it): a FIFO with no
    writer reads as absent at once, never waits."""
    fifo = tmp_path / "m.gguf"
    os.mkfifo(fifo)
    found: list[bytes] = []
    worker = threading.Thread(
        target=lambda: found.append(reader.read_ai_model_header(fifo)), daemon=True
    )
    worker.start()
    worker.join(timeout=10)
    if worker.is_alive():  # opened: let it end, then fail
        os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        worker.join(timeout=30)
        pytest.fail("read_ai_model_header() opened a FIFO and waited for a writer")
    assert found == [b""]
