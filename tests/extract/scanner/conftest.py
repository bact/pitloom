# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Fixtures shared by the wheel scanner tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.extract import scanner_wheel


@pytest.fixture(name="copies")
def fixture_copies(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The path of every temporary copy the wheel producer opens for writing."""
    opened: list[Path] = []
    real_open = open

    # Mirrors the signature of builtins.open().
    # pylint: disable-next=keyword-arg-before-vararg
    def spy(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if "x" in mode:
            opened.append(Path(file))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(scanner_wheel, "open", spy, raising=False)
    return opened
