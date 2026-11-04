# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``licenseid`` warning given as when Pitloom calls ``licenseid``.

``licenseid`` attributes its warning to the module of the code that called
it, skipping its own frames, and the relay's filter takes only a warning of
a ``pitloom`` module (:mod:`pitloom.extract._licenseid_relay`). A test
module is neither, so a function of the test runs here as the code of
another module: :func:`as_licenseid` for a stand-in of ``licenseid`` that
Pitloom's real code calls, :func:`warn_from_pitloom` for a warning given
straight in a relay block.
"""

from __future__ import annotations

import types
from collections.abc import Callable
from typing import TypeVar, cast

from licenseid import warning as licenseid_warning

_F = TypeVar("_F", bound=Callable[..., object])


def as_module(func: _F, module: str) -> _F:
    """*func* run as the code of *module* (its frames' ``__name__``)."""
    namespace = dict(func.__globals__, __name__=module)
    return cast(
        _F,
        types.FunctionType(
            func.__code__, namespace, func.__name__, func.__defaults__, func.__closure__
        ),
    )


def as_licenseid(func: _F) -> _F:
    """*func* as ``licenseid``'s own code: a warning it gives is attributed
    to the Pitloom code that called it."""
    return as_module(func, "licenseid._stand_in")


def _warn(
    subject: str, condition: str, detail: str | None = None, action: str | None = None
) -> None:
    licenseid_warning.warn(subject, condition, detail, action)


#: ``licenseid``'s one emitter, called from a ``pitloom`` module.
warn_from_pitloom = as_module(_warn, "pitloom.extract._license")
