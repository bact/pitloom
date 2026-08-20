# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Python-version-gated ``tomllib``/``tomli`` import in
``pitloom.core._config_parse``.

See also: :mod:`tests.core.test_config` for the rest of
``[tool.pitloom]`` parsing.
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest
import tomli

import pitloom.core._config_parse as config_parse


def test_config_parse_uses_stdlib_tomllib_on_py311_plus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a Python >= 3.11 interpreter, ``pitloom.core._config_parse``
    imports the stdlib ``tomllib`` at module load time instead of the
    ``tomli`` backport. This repo's test environment runs on 3.10 (no
    stdlib ``tomllib``), so the true branch is exercised here by faking
    both ``sys.version_info`` and a ``tomllib`` entry in ``sys.modules``
    (reusing the real ``tomli`` parser under that name), then reloading
    the module -- no source changes, purely a test-side substitution of
    what ``import tomllib`` resolves to plus a controlled re-import.

    The module is reloaded again at the end (in ``finally``, with the
    patches already undone) to restore its normal ``tomli``-backed state
    for every other test in the suite.
    """
    fake_tomllib = types.ModuleType("tomllib")
    fake_tomllib.load = tomli.load  # type: ignore[attr-defined]
    fake_tomllib.loads = tomli.loads  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tomllib", fake_tomllib)
    monkeypatch.setattr(sys, "version_info", (3, 11, 0, "final", 0))

    try:
        importlib.reload(config_parse)
        assert config_parse.tomllib is fake_tomllib  # type: ignore[attr-defined]
    finally:
        monkeypatch.undo()
        importlib.reload(config_parse)
