# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Python-version-gated ``tomllib``/``tomli`` import in
``pitloom.extract._toml_io``.

``pitloom.extract._setuptools``, ``pitloom.extract._poetry_lock``,
``pitloom.extract.hatchling``, ``pitloom.extract._pyproject``,
``pitloom.core._config_parse``, and ``pitloom.cli.options`` all build on
:func:`~pitloom.extract._toml_io.load_toml_file` instead of each carrying
their own version-gated import; ``pitloom.extract._sdist`` parses TOML
from in-memory bytes rather than a file path, so it can't use
``load_toml_file`` directly, but it still imports the resolved
:data:`~pitloom.extract._toml_io.tomllib` module from here rather than
carrying its own copy of the shim. Either way, the branch this file
exercises lives in ``_toml_io`` alone.

See also: :mod:`tests.extract.test_setuptools_integration` for the rest of
``read_setuptools()`` parsing, and :mod:`tests.tomllib_fixtures` for the
shared version-forcing helpers used here.
"""

from __future__ import annotations

import pytest

import pitloom.extract._toml_io as toml_io_module
from tests.tomllib_fixtures import force_tomli_branch, force_tomllib_branch


def test_toml_io_uses_stdlib_tomllib_on_py311_plus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python >= 3.11 interpreter, ``pitloom.extract._toml_io``
    imports the stdlib ``tomllib`` at module load time instead of the
    ``tomli`` backport."""
    with force_tomllib_branch(monkeypatch, toml_io_module):
        tomllib_mod: object = toml_io_module.tomllib
        assert tomllib_mod.__name__ == "tomllib"  # type: ignore[attr-defined]


def test_toml_io_uses_tomli_backport_below_py311(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python < 3.11 interpreter, ``pitloom.extract._toml_io``
    imports the ``tomli`` backport instead of stdlib ``tomllib`` -- the
    mirror-image branch of the test above, needed so this stays covered
    regardless of which Python version CI happens to collect coverage on
    (this repo's CI matrix runs both 3.10 and 3.14)."""
    with force_tomli_branch(monkeypatch, toml_io_module):
        tomllib_mod: object = toml_io_module.tomllib
        assert tomllib_mod.__name__ == "tomli"  # type: ignore[attr-defined]
