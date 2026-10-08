# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`tests._environ`, the per-test ``os.environ`` restore."""

import os

import pytest

from tests._environ import environ_restored

_NAME = "PITLOOM_TEST_ENVIRON_RESTORE"


@pytest.mark.parametrize(
    ("before", "during"),
    [
        pytest.param(None, "1", id="added"),
        pytest.param("0", "1", id="changed"),
        pytest.param("0", None, id="removed"),
    ],
)
def test_environ_restored_undoes_direct_writes(
    monkeypatch: pytest.MonkeyPatch, before: str | None, during: str | None
) -> None:
    """Direct ``os.environ`` writes, which monkeypatch never sees, are undone."""
    monkeypatch.delenv(_NAME, raising=False)
    if before is not None:
        monkeypatch.setenv(_NAME, before)

    with environ_restored():
        if during is None:
            del os.environ[_NAME]
        else:
            os.environ[_NAME] = during
        assert os.environ.get(_NAME) == during

    assert os.environ.get(_NAME) == before


def test_restore_environ_fixture_wraps_every_test(
    request: pytest.FixtureRequest,
) -> None:
    """``tests/conftest.py`` applies the restore to every test, autouse."""
    assert "_restore_environ" in request.fixturenames
