# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for exercising the ``sys.version_info``-gated
``tomllib``/``tomli`` import branch present in each of Pitloom's TOML-reading
modules, regardless of which Python version pytest actually runs under.

Every module of the form::

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

needs BOTH branches covered for the coverage floor to hold on every CI leg:
this repo's CI test matrix runs coverage collection on Python 3.14 (stdlib
``tomllib`` naturally taken there) but also runs the full suite on 3.10
(``tomli`` backport naturally taken there) -- whichever branch the *real*
interpreter doesn't take has to be forced via ``sys.version_info`` faking
plus a module reload.

``tomli`` is always genuinely importable here regardless of interpreter
version: it's pulled in transitively via Pitloom's own ``pipdeptree``
dependency (which requires it unconditionally, not just for <3.11), so
forcing the ``tomli`` branch never needs a fake stand-in module -- only
forcing the ``tomllib`` branch does, since real stdlib ``tomllib`` doesn't
exist before 3.11.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType

import pytest
import tomli


@contextmanager
def force_tomllib_branch(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType
) -> Iterator[None]:
    """Force *module* to take its ``import tomllib`` (stdlib) branch: fake
    ``sys.version_info >= (3, 11)`` and a ``tomllib`` sys.modules entry
    (backed by the real ``tomli`` parser), then reload *module*. Restores
    *module* to its real, unpatched state on exit."""
    fake_tomllib = types.ModuleType("tomllib")
    fake_tomllib.load = tomli.load  # type: ignore[attr-defined]
    fake_tomllib.loads = tomli.loads  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tomllib", fake_tomllib)
    monkeypatch.setattr(sys, "version_info", (3, 11, 0, "final", 0))
    try:
        importlib.reload(module)
        yield
    finally:
        monkeypatch.undo()
        importlib.reload(module)


@contextmanager
def force_tomli_branch(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType
) -> Iterator[None]:
    """Force *module* to take its ``import tomli as tomllib`` (backport)
    branch: fake ``sys.version_info < (3, 11)``, then reload *module* (the
    real ``tomli`` package is always importable here -- see module
    docstring). Restores *module* to its real, unpatched state on exit."""
    monkeypatch.setattr(sys, "version_info", (3, 10, 0, "final", 0))
    try:
        importlib.reload(module)
        yield
    finally:
        monkeypatch.undo()
        importlib.reload(module)
