# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``--allow-build``/``--no-build-isolation``/``--build-timeout``
options as one value, shared by every usage surface.

Every surface (CLI ``project``/``generate``/``embed-wheel``,
:func:`pitloom.assemble.generate`, :func:`pitloom.assemble.generate_project_sbom`,
:class:`pitloom.embed.ConfigOverrides`, :func:`pitloom.core.models.get_wheel_files`)
takes one :class:`BuildOptions`, validated at construction. Each calls
:meth:`BuildOptions.settle` or :meth:`BuildOptions.settle_not_applicable`
as soon as it knows whether the target reaches file discovery, before any
metadata read, so the "has no effect" ``WARNING:`` comes first. Both
reset what they warn about, so settling again downstream is a silent
no-op: every ignored flag is reported exactly once.

See also: :mod:`pitloom.core._models_wheel_types` (timeout parsing and
:class:`~pitloom.core._models_wheel_types.BuildSettings`),
:mod:`pitloom.core._models_wheel_dispatch`.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

from pitloom.core._models_wheel_types import (
    BUILD_LOG_PREFIX,
    BuildSettings,
    resolve_build_timeout,
    validate_build_timeout,
)
from pitloom.core.no_effect import warn_no_effect
from pitloom.core.project import is_sdist_archive

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


def target_settle_plan(target: Path) -> tuple[bool, str | None]:
    """How to settle build options for a project-or-sdist *target* path:
    ``(True, SDIST_TARGET_REASON)`` for an sdist archive, ``(True, None)``
    for a project directory, ``(False, None)`` for anything else -- a
    missing path, or a file that is no sdist -- whose read fails with an
    ``ERROR:`` alone, with no build-flag warning ahead of it.

    One authority for that order and those reasons, shared by
    :meth:`BuildOptions.settle_target` and :mod:`pitloom._embed_generate`,
    which settles each branch through its own ``EmbedFileCache`` instead
    and so cannot call the method.
    """
    if is_sdist_archive(target):
        return True, SDIST_TARGET_REASON
    # os.path.isdir, not Path.is_dir(): never raises (e.g. EACCES).
    if os.path.isdir(target):
        return True, None
    return False, None


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
        warn_no_effect(BUILD_LOG_PREFIX, subject, self.given, f"without {_ALLOW_FLAG}")
        return BuildOptions()

    def settle_target(self, target: Path) -> BuildOptions:
        """Settle for a project-or-sdist *target* path, following
        :func:`target_settle_plan`: an sdist archive gets
        :meth:`settle_not_applicable` with :data:`SDIST_TARGET_REASON`, a
        directory :meth:`settle`, anything else nothing."""
        settle, reason = target_settle_plan(target)
        if not settle:
            return self
        if reason is None:
            return self.settle(target)
        return self.settle_not_applicable(target, reason)

    def settle_not_applicable(self, subject: object, reason: str) -> BuildOptions:
        """Resolve a target a caller already knows will never reach file
        discovery (e.g. an sdist archive, a non-project target, an
        externally-supplied ``--sbom``): log one ``WARNING:`` per given
        flag and return ``BuildOptions()``
        (defaults), so a downstream call on the same value -- one this
        caller forwards, or one a later layer resolves independently --
        has nothing left to warn about.

        Call this as early as the caller can tell the target's fate,
        before reading any project metadata or lock file, so the
        warning precedes those rather than following them. *reason*
        follows "has no effect" (no trailing punctuation), e.g.
        :data:`SDIST_TARGET_REASON`. Idempotent the same way :meth:`settle`
        is: the returned (defaulted) value has no given flag to warn about.
        """
        warn_no_effect(BUILD_LOG_PREFIX, subject, self.given, reason)
        return BuildOptions()


__all__ = [
    "EXTERNAL_SBOM_REASON",
    "NO_PROJECT_DIR_REASON",
    "NON_PROJECT_TARGET_REASON",
    "BuildOptions",
    "SDIST_TARGET_REASON",
]
