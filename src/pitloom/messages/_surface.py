# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The surface that runs, and the wording of a line on each surface: a
line's action names what the user can change where they ran Pitloom (a
command-line flag, a library parameter, a ``[tool.pitloom]`` key).

The entry points open :func:`advice_surface`: ``__main__.main()`` and
``cli_error_handler`` (:data:`SURFACE_CLI`; the GitHub Action runs the
command line) and the Hatchling build hook (:data:`SURFACE_HOOK`); a
library call, ``loom.run()`` included, keeps the default,
:data:`SURFACE_LIBRARY`. A line said on
several surfaces is a :class:`Twins`, resolved where it is said
(:func:`pitloom.messages.emit`, :class:`pitloom.messages.CodedValueError`,
:func:`pitloom.messages.say_summary`), never picked by a call site.

Within the library one route takes its settings otherwise:
``embed_wheel_sbom()`` takes them as
:class:`~pitloom.core.config_cascade.ConfigOverrides` fields, not keywords,
so a line whose action names a keyword has an :attr:`Twins.overrides`
wording, said within :func:`overrides_route`.

The surface is a :class:`contextvars.ContextVar`: a thread started with
:class:`threading.Thread` does not see it (unless the interpreter's
``thread_inherit_context`` flag is set), so a twinned line is said on the
thread that entered the surface.

See also: :mod:`pitloom.core.option_names` (an option as each surface
spells it).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, Generic, TypeVar

from pitloom.core.internal_error import InternalError
from pitloom.messages._templates import template_names

#: The command line (each ``loom`` command, the GitHub Action).
SURFACE_CLI: Final = "cli"
#: The Hatchling build hook: ``pyproject.toml`` is all a user can change.
SURFACE_HOOK: Final = "hook"
#: The library (``pitloom.assemble``, ``pitloom.embed``, ``loom.run()``).
SURFACE_LIBRARY: Final = "library"
#: Every surface, in the order a :class:`Twins` lists them.
SURFACES: Final = (SURFACE_CLI, SURFACE_LIBRARY, SURFACE_HOOK)

_SURFACE: ContextVar[str] = ContextVar("pitloom_surface", default=SURFACE_LIBRARY)
#: Whether the library call that runs takes its settings as
#: ``ConfigOverrides`` fields (:func:`overrides_route`).
_OVERRIDES_ROUTE: ContextVar[bool] = ContextVar(
    "pitloom_overrides_route", default=False
)
#: Whether a line the hook cannot reach raises when it is resolved there
#: (:func:`strict_surfaces`, the test suite only).
_STRICT: ContextVar[bool] = ContextVar("pitloom_strict_surfaces", default=False)


@contextmanager
def advice_surface(surface: str) -> Iterator[None]:
    """Within the block, a line names what *surface* (one of
    :data:`SURFACES`) lets the user change. An entry point opens it; the
    previous surface returns on exit, also on an exception.

    Raises:
        pitloom.core.internal_error.InternalError: *surface* is none of
            :data:`SURFACES`.
    """
    if surface not in SURFACES:
        raise InternalError(f"no advice for surface {surface!r}")
    token = _SURFACE.set(surface)
    try:
        yield
    finally:
        _SURFACE.reset(token)


def current_surface() -> str:
    """The surface that runs (:func:`advice_surface`), else
    :data:`SURFACE_LIBRARY`."""
    return _SURFACE.get()


def on_overrides_route() -> bool:
    """Whether the library call that runs takes its settings as
    ``ConfigOverrides`` fields (:func:`overrides_route`): for a line picked
    by its own branch per surface rather than a :class:`Twins`."""
    return _OVERRIDES_ROUTE.get()


@contextmanager
def overrides_route() -> Iterator[None]:
    """Within the block (or the function it decorates), the library's
    settings are
    :class:`~pitloom.core.config_cascade.ConfigOverrides` fields, not keywords
    (``embed_wheel_sbom()``): on :data:`SURFACE_LIBRARY` a :class:`Twins`
    says its :attr:`~Twins.overrides` wording where it has one. The command
    line and the hook are not affected. The previous route returns on exit,
    also on an exception."""
    token = _OVERRIDES_ROUTE.set(True)
    try:
        yield
    finally:
        _OVERRIDES_ROUTE.reset(token)


@contextmanager
def strict_surfaces() -> Iterator[None]:
    """Within the block, a :class:`Twins` made by :meth:`Twins.no_hook`
    raises when resolved under :data:`SURFACE_HOOK`: the test suite's check
    that the hook never reaches such a line. Outside it the library's
    wording is said, so a build never fails over a line's wording."""
    token = _STRICT.set(True)
    try:
        yield
    finally:
        _STRICT.reset(token)


def unreachable_on_hook(what: str) -> None:
    """Under :func:`strict_surfaces`, refuse *what*, which the hook was
    ruled unable to say (the caller checked the surface is the hook);
    otherwise return, and the caller says the library's wording.

    Raises:
        pitloom.core.internal_error.InternalError: :func:`strict_surfaces`
            is open.
    """
    if _STRICT.get():
        raise InternalError(f"the hook said a line it cannot reach: {what}")


_T = TypeVar("_T")


@dataclass(frozen=True)
class Twins(Generic[_T]):
    """One line (or summary) worded for each surface. All three surfaces
    are named: a surface that cannot reach the line names another's wording
    on purpose (:meth:`no_hook`), never by an implicit fallback.
    :attr:`overrides` is a variant of the library's wording, for the route
    that takes its settings as ``ConfigOverrides`` fields
    (:func:`overrides_route`); a drift test holds that every line whose
    library action names such a setting has one.

    Raises:
        ValueError: The members differ in level or in the fields their
            templates name: one call says any of them with one set of values.
    """

    #: The command line's wording.
    cli: _T
    #: The library's.
    library: _T
    #: The Hatchling build hook's.
    hook: _T
    #: Whether the hook can say it (:meth:`no_hook`).
    hook_reachable: bool = True
    #: The library's wording within :func:`overrides_route`; ``None``: the
    #: library's own wording names no setting that route spells otherwise.
    overrides: _T | None = None

    def __post_init__(self) -> None:
        """Check that one call can say any member."""
        shapes = {
            (
                getattr(member, "level", None),
                frozenset(template_names(getattr(member, "template", ""))),
            )
            for member in self.members
        }
        if len(shapes) != 1:
            raise ValueError(f"twins of different levels or fields: {self.members!r}")

    @classmethod
    def no_hook(cls, cli: _T, library: _T, overrides: _T | None = None) -> Twins[_T]:
        """The twins of a line the hook cannot reach: the hook's wording is
        the library's, and resolving it there raises under
        :func:`strict_surfaces`."""
        return cls(
            cli=cli,
            library=library,
            hook=library,
            hook_reachable=False,
            overrides=overrides,
        )

    @property
    def members(self) -> tuple[_T, ...]:
        """Each distinct wording once, in :data:`SURFACES` order: what the
        entry lists among its lines."""
        found: list[_T] = []
        for member in (self.cli, self.library, self.hook, self.overrides):
            if member is not None and member not in found:
                found.append(member)
        return tuple(found)

    def current(self) -> _T:
        """The wording of the surface that runs."""
        return self.for_surface(current_surface())

    def for_surface(self, surface: str) -> _T:
        """The wording of *surface*.

        Raises:
            pitloom.core.internal_error.InternalError: *surface* is none of
                :data:`SURFACES`.
        """
        if surface == SURFACE_CLI:
            return self.cli
        if surface == SURFACE_HOOK:
            if not self.hook_reachable:
                unreachable_on_hook(repr(self.hook))
            return self.hook
        if surface == SURFACE_LIBRARY:
            if self.overrides is not None and _OVERRIDES_ROUTE.get():
                return self.overrides
            return self.library
        raise InternalError(f"no wording for surface {surface!r}")


__all__ = [
    "SURFACES",
    "SURFACE_CLI",
    "SURFACE_HOOK",
    "SURFACE_LIBRARY",
    "Twins",
    "advice_surface",
    "current_surface",
    "on_overrides_route",
    "overrides_route",
    "strict_surfaces",
    "unreachable_on_hook",
]
