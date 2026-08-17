# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.core.creation."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pitloom.core.creation import resolve_source_date_epoch


def test_resolve_source_date_epoch_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert resolve_source_date_epoch() is None


def test_resolve_source_date_epoch_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert resolve_source_date_epoch() == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc
    )


def test_resolve_source_date_epoch_invalid_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-a-number")
    assert resolve_source_date_epoch() is None


def test_resolve_source_date_epoch_overflow_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "99999999999999999999999999999999999")
    assert resolve_source_date_epoch() is None


def test_resolve_source_date_epoch_empty_string_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "")
    assert resolve_source_date_epoch() is None
