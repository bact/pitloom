# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Python-version-gated ``tomllib``/``tomli`` import in
``pitloom.extract._poetry``.

See also: :mod:`tests.extract.test_poetry_parsing` and
:mod:`tests.extract.test_poetry_pyproject` for the rest of ``[tool.poetry]``
parsing, and :mod:`tests.tomllib_fixtures` for the shared version-forcing
helpers used here.
"""

from __future__ import annotations

import pytest

import pitloom.extract._poetry as poetry_module
from tests.tomllib_fixtures import force_tomli_branch, force_tomllib_branch


def test_poetry_uses_stdlib_tomllib_on_py311_plus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python >= 3.11 interpreter, ``pitloom.extract._poetry``
    imports the stdlib ``tomllib`` at module load time instead of the
    ``tomli`` backport."""
    with force_tomllib_branch(monkeypatch, poetry_module):
        tomllib_mod: object = poetry_module.tomllib  # type: ignore[attr-defined]
        assert tomllib_mod.__name__ == "tomllib"  # type: ignore[attr-defined]


def test_poetry_uses_tomli_backport_below_py311(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python < 3.11 interpreter, ``pitloom.extract._poetry``
    imports the ``tomli`` backport instead of stdlib ``tomllib`` -- the
    mirror-image branch of the test above, needed so this stays covered
    regardless of which Python version CI happens to collect coverage on
    (this repo's CI matrix runs both 3.10 and 3.14)."""
    with force_tomli_branch(monkeypatch, poetry_module):
        tomllib_mod: object = poetry_module.tomllib  # type: ignore[attr-defined]
        assert tomllib_mod.__name__ == "tomli"  # type: ignore[attr-defined]
