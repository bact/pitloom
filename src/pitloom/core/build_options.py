# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``--allow-build``/``--no-build-isolation``/``--build-timeout``
options as one value, shared by every usage surface.

See also: :mod:`pitloom.core._models_wheel_types` (timeout validation and
parsing, :class:`~pitloom.core._models_wheel_types.BuildSettings`),
:mod:`pitloom.core._models_wheel_dispatch` (the build-and-read dispatch).

Every surface that accepts these flags -- the CLI ``project``/
``generate``/``embed-wheel`` commands, :func:`pitloom.assemble.generate`,
:func:`pitloom.assemble.generate_project_sbom`,
:class:`pitloom.embed.ConfigOverrides` and
:func:`pitloom.core.models.get_wheel_files` -- takes one
:class:`BuildOptions` and passes it down unchanged. Validation happens
once, at construction. The "has no effect" ``WARNING:`` comes only from
:meth:`BuildOptions.warn_no_effect` (a target that never reaches file
discovery), :meth:`BuildOptions.settle` (a ``no_isolation``/``timeout``
given without ``allow``, for a target that does), or
:meth:`BuildOptions.settle_not_applicable` (``warn_no_effect`` plus
resetting to defaults in one call, for a target a caller already knows
will never reach file discovery -- e.g. an sdist archive). Every surface
calls ``settle()``/``settle_not_applicable()`` on its build options as
early as it can determine the target's fate -- before reading any
project metadata or lock file -- so the "stray flag"/"has no effect"
warning surfaces at the very start of a run rather than after later
metadata warnings. Both reset what they warn about to defaults, so a
later call on the same (now settled) value -- e.g. ``get_wheel_files()``'s
own ``settle()`` call -- is a silent no-op; this is what keeps every
ignored flag reported exactly once, however many layers it passes
through.
"""

from __future__ import annotations

import dataclasses
import logging

from pitloom.core._models_wheel_types import (
    BUILD_LOG_PREFIX,
    BuildSettings,
    resolve_build_timeout,
    validate_build_timeout,
)

log = logging.getLogger(__name__)

_ALLOW_FLAG = "--allow-build"

#: Reasons passed to :meth:`BuildOptions.settle_not_applicable` for a
#: target that never reaches file discovery -- shared by the CLI handlers
#: (called before their own metadata read) and the library entry points,
#: so the wording can't drift between call sites.
SDIST_TARGET_REASON = (
    "for an sdist archive target (no build-and-read support for "
    "archives yet -- files come from the archive's own listing)"
)
NON_PROJECT_TARGET_REASON = (
    "for this target (no build-backend file discovery applies to "
    "env/wheel/model-file/Hugging-Face targets)"
)
EXTERNAL_SBOM_REASON = (
    "for an externally-supplied --sbom (embedded verbatim, never rescanned)"
)
NO_PROJECT_DIR_REASON = "with no project directory to rescan"


@dataclasses.dataclass(frozen=True)
class BuildOptions:
    """Explicit build-and-read options for one call.

    Attributes:
        allow: Opt into a real PEP 517 build of the scanned project to
            discover its wheel file list (``--allow-build``). SECURITY:
            executes third-party build-time code. Deliberately has no
            ``[tool.pitloom]`` equivalent: the scanned project's own
            config must never opt itself in, so a caller passes it
            explicitly on every call.
        no_isolation: Use the current environment's build backend instead
            of an isolated build environment (``--no-build-isolation``).
        timeout: Whole seconds the build may run before it is terminated
            (``--build-timeout``); ``None`` uses
            :data:`~pitloom.core._models_wheel_types.DEFAULT_BUILD_TIMEOUT_SECONDS`.

    ``no_isolation`` and ``timeout`` have no effect without ``allow``.
    The default instance means "no build flag given".

    Raises:
        TypeError: ``allow``/``no_isolation`` is not a ``bool`` (a truthy
            string such as ``"false"`` must never enable code execution),
            or ``timeout`` is not an ``int``.
        ValueError: ``timeout`` is outside
            ``1..MAX_BUILD_TIMEOUT_SECONDS``.
    """

    allow: bool = False
    no_isolation: bool = False
    timeout: int | None = None

    def __post_init__(self) -> None:
        for name in ("allow", "no_isolation"):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(
                    f"build option {name!r} must be bool, got {type(value).__name__}"
                )
        if self.timeout is not None:
            validate_build_timeout(self.timeout)

    @property
    def given(self) -> tuple[str, ...]:
        """CLI spellings of the explicitly given flags, in CLI order."""
        flags: list[str] = []
        if self.allow:
            flags.append(_ALLOW_FLAG)
        if self.no_isolation:
            flags.append("--no-build-isolation")
        if self.timeout is not None:
            flags.append("--build-timeout")
        return tuple(flags)

    def settings(self) -> BuildSettings | None:
        """The resolved settings for a real build, or ``None`` when
        ``allow`` is off."""
        if not self.allow:
            return None
        return BuildSettings(
            isolated=not self.no_isolation,
            timeout=resolve_build_timeout(self.timeout),
        )

    def warn_no_effect(self, subject: object, reason: str) -> None:
        """Log one ``WARNING:`` per given flag, for a target that never
        reaches file discovery. *reason* follows "has no effect" (no
        trailing punctuation), e.g. ``"for an sdist archive target"``."""
        _warn_each(subject, self.given, reason)

    def settle(self, subject: object) -> BuildOptions:
        """Resolve a ``no_isolation``/``timeout`` given without ``allow``:
        log one ``WARNING:`` per such flag and return
        ``BuildOptions()`` (defaults) so nothing is left to warn about
        later. Returns ``self`` unchanged when ``allow`` is set (nothing
        stray to resolve) or nothing was given (already settled).

        Call this as early as a caller can tell the target will reach
        file discovery -- before resolving project metadata or a lock
        file -- so the warning precedes those, not the other way round.
        Idempotent: settling an already-settled value warns nothing and
        returns it unchanged, so calling this again downstream (e.g.
        inside ``get_wheel_files()``) on a value a caller already
        settled is always a silent no-op.
        """
        if self.allow or not self.given:
            return self
        _warn_each(subject, self.given, f"without {_ALLOW_FLAG}")
        return BuildOptions()

    def settle_not_applicable(self, subject: object, reason: str) -> BuildOptions:
        """Resolve a target a caller already knows will never reach file
        discovery (e.g. an sdist archive, a non-project target, an
        externally-supplied ``--sbom``): log one ``WARNING:`` per given
        flag (via :meth:`warn_no_effect`) and return ``BuildOptions()``
        (defaults), so a downstream call on the same value -- one this
        caller forwards, or one a later layer resolves independently --
        has nothing left to warn about.

        Call this as early as the caller can tell the target's fate,
        before reading any project metadata or lock file, so the
        warning precedes those rather than following them. Idempotent
        the same way :meth:`settle` is: called again on the returned
        (defaulted) value, :meth:`warn_no_effect` iterates zero given
        flags and logs nothing.
        """
        self.warn_no_effect(subject, reason)
        return BuildOptions()


def _warn_each(subject: object, flags: tuple[str, ...], reason: str) -> None:
    for flag in flags:
        log.warning(
            "%s%s: %s has no effect %s", BUILD_LOG_PREFIX, subject, flag, reason
        )


__all__ = [
    "EXTERNAL_SBOM_REASON",
    "NO_PROJECT_DIR_REASON",
    "NON_PROJECT_TARGET_REASON",
    "BuildOptions",
    "SDIST_TARGET_REASON",
]
