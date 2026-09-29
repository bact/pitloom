# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for :mod:`tests.id_registry`."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from pitloom.id_registry import IdRegistry


@pytest.fixture(name="load_spy")
def _load_spy(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Spy on ``IdRegistry.load``, returning the list of paths it was
    called with (append-order, real loads still happen)."""
    calls: list[Path] = []
    real_load = IdRegistry.load.__func__  # type: ignore[attr-defined]

    def spy(cls: type[IdRegistry], path: Path) -> IdRegistry:
        calls.append(path)
        return cast(IdRegistry, real_load(cls, path))

    monkeypatch.setattr(IdRegistry, "load", classmethod(spy))
    return calls


@pytest.fixture(name="fixed_epoch")
def _fixed_epoch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``SOURCE_DATE_EPOCH``: a test comparing the bytes of two runs
    must not see ``created`` differ when the runs straddle a second."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
