# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.plugins.hatch's Hatchling-version-agnostic
``BuildHookInterface`` base-class resolution (``_resolve_build_hook_base``).

Regression coverage for Hatchling 1.32.3's undocumented change of
``BuildHookInterface`` from ``Generic[BuilderConfigBound]`` (one type
param) to ``Generic[BuilderConfigBound, PluginManagerBound]`` (two),
reverted in 1.32.4. A wrong-arity subscription crashes
``PitloomBuildHook``'s class definition at import time.

See also:
- :mod:`tests.extract.project.test_hatch_hook_hook_basic` for hook
  lifecycle tests.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

import pytest

import pitloom.plugins.hatch as hatch_module

# pylint: disable=too-few-public-methods
# (the fake *ParamFakeInterface classes below are intentionally-empty
# type-arity stand-ins, not real interfaces)

# BuildHookInterface/BuilderConfig/PluginManager/_resolve_build_hook_base
# exist as real module attributes at runtime, but the first three are
# merely-imported names mypy's no_implicit_reexport won't let an outside
# module read off ``hatch_module`` directly, and the last is defined only
# in hatch.py's non-TYPE_CHECKING branch -- deliberately invisible to
# static analysis (see hatch.py). getattr() sidesteps both, honestly.
_BuildHookInterface: Any = getattr(hatch_module, "BuildHookInterface")  # noqa: B009
_BuilderConfig: Any = getattr(hatch_module, "BuilderConfig")  # noqa: B009
_PluginManager: Any = getattr(hatch_module, "PluginManager")  # noqa: B009
_resolve_build_hook_base: Any = getattr(  # noqa: B009
    hatch_module, "_resolve_build_hook_base"
)
_HATCHLING_ERROR_PREFIX: str = getattr(  # noqa: B009
    hatch_module, "_HATCHLING_ERROR_PREFIX"
)

_T = TypeVar("_T")
_U = TypeVar("_U")
_V = TypeVar("_V")


class _OneParamFakeInterface(Generic[_T]):
    """Stands in for the single-type-param interface (all but 1.32.3)."""


class _TwoParamFakeInterface(Generic[_T, _U]):
    """Stands in for Hatchling 1.32.3's two-type-param interface."""


class _ThreeParamFakeInterface(Generic[_T, _U, _V]):
    """Stands in for a hypothetical arity Pitloom doesn't handle."""


class _ZeroParamFakeInterface:
    """Stands in for a hypothetical arity Pitloom doesn't handle."""

    __parameters__: tuple[type, ...] = ()


def test_resolve_build_hook_base_imported() -> None:
    """``_resolve_build_hook_base`` exists at runtime (only defined outside
    the TYPE_CHECKING branch) -- if the module failed to import (the
    reported crash: a TypeError at class-definition time), this fails
    before any assertion even runs."""
    assert issubclass(hatch_module.PitloomBuildHook, _BuildHookInterface)


def test_resolve_build_hook_base_one_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single-type-param BuildHookInterface (every Hatchling except
    1.32.3) resolves to a one-argument subscription."""
    monkeypatch.setattr(hatch_module, "BuildHookInterface", _OneParamFakeInterface)

    base = _resolve_build_hook_base()

    # pylint: disable-next=no-member
    assert base.__origin__ is _OneParamFakeInterface
    # pylint: disable-next=no-member
    assert base.__args__ == (_BuilderConfig,)


def test_resolve_build_hook_base_two_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """A two-type-param BuildHookInterface (Hatchling 1.32.3 only)
    resolves to a two-argument subscription, using the concrete
    PluginManager class as the 2nd arg."""
    monkeypatch.setattr(hatch_module, "BuildHookInterface", _TwoParamFakeInterface)

    base = _resolve_build_hook_base()

    # pylint: disable-next=no-member
    assert base.__origin__ is _TwoParamFakeInterface
    # pylint: disable-next=no-member
    assert base.__args__ == (_BuilderConfig, _PluginManager)


@pytest.mark.parametrize(
    "fake_interface", [_ZeroParamFakeInterface, _ThreeParamFakeInterface]
)
def test_resolve_build_hook_base_unexpected_arity_raises(
    monkeypatch: pytest.MonkeyPatch, fake_interface: type
) -> None:
    """An arity Pitloom doesn't know how to handle raises a clear,
    grep-able RuntimeError instead of guessing wrong."""
    monkeypatch.setattr(hatch_module, "BuildHookInterface", fake_interface)

    with pytest.raises(RuntimeError, match=_HATCHLING_ERROR_PREFIX):
        _resolve_build_hook_base()
