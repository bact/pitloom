# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The Hatchling base class of the build hook, for the installed Hatchling.

See also: :mod:`pitloom.plugins.hatch` (the build hook that subclasses it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

#: Start of the error :func:`resolve_build_hook_base` raises when Hatchling's
#: ``BuildHookInterface`` has an unexpected shape. The hook's frame
#: (``Pitloom build hook: ``) goes before it on the ERROR line; the traceback
#: names the module, so the raised text does not repeat it. The version gate
#: of :mod:`pitloom.plugins.hatch` is the catalogued ``library-unusable``.
HATCHLING_ERROR_PREFIX: Final = "Hatchling"

if TYPE_CHECKING:
    # Static shape for type checkers only: the one-parameter interface every
    # supported Hatchling except 1.32.3 declares. The ignore covers 1.32.3's
    # two-parameter shape; "unused-ignore" keeps it silent elsewhere. See
    # resolve_build_hook_base() below for the base used at runtime.
    class PitloomBuildHookBase(
        BuildHookInterface[BuilderConfig]  # type: ignore[type-arg, unused-ignore]
    ):
        """Static shape for type checkers -- see :func:`resolve_build_hook_base`."""

else:
    from hatchling.plugin.manager import PluginManager

    def resolve_build_hook_base() -> type:
        """Pick the Hatchling ``BuildHookInterface`` base matching the
        installed Hatchling's actual generic arity (see
        working-docs/implementation/hatchling-build-hook.md for why this
        varies by version). ``__parameters__`` is a side-effect-free
        tuple read, so detecting the arity this way can't itself trigger
        the subscription ``TypeError`` it works around.

        Raises:
            RuntimeError: If the arity is neither 1 nor 2.
        """
        param_count = len(BuildHookInterface.__parameters__)
        if param_count == 1:
            return BuildHookInterface[BuilderConfig]
        if param_count == 2:
            return BuildHookInterface[BuilderConfig, PluginManager]
        raise RuntimeError(
            f"{HATCHLING_ERROR_PREFIX} BuildHookInterface has an "
            f"unexpected number of type parameters ({param_count}); "
            "Pitloom's Hatchling build hook may need updating for this "
            "Hatchling version."
        )

    PitloomBuildHookBase = resolve_build_hook_base()
