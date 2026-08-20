# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Python-version-gated ``tomllib``/``tomli`` import in
``pitloom.core._config_parse``.

See also: :mod:`tests.core.test_config` for the rest of
``[tool.pitloom]`` parsing, and :mod:`tests.tomllib_fixtures` for the
shared version-forcing helpers used here.
"""

from __future__ import annotations

import pytest

import pitloom.core._config_parse as config_parse
from tests.tomllib_fixtures import force_tomli_branch, force_tomllib_branch


def test_config_parse_uses_stdlib_tomllib_on_py311_plus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python >= 3.11 interpreter, ``pitloom.core._config_parse``
    imports the stdlib ``tomllib`` at module load time instead of the
    ``tomli`` backport."""
    with force_tomllib_branch(monkeypatch, config_parse):
        assert config_parse.tomllib.__name__ == "tomllib"  # type: ignore[attr-defined]


def test_config_parse_uses_tomli_backport_below_py311(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python < 3.11 interpreter, ``pitloom.core._config_parse``
    imports the ``tomli`` backport instead of stdlib ``tomllib`` -- the
    mirror-image branch of the test above, needed so this stays covered
    regardless of which Python version CI happens to collect coverage on
    (this repo's CI matrix runs both 3.10 and 3.14)."""
    with force_tomli_branch(monkeypatch, config_parse):
        assert config_parse.tomllib.__name__ == "tomli"  # type: ignore[attr-defined]
