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
    """One line (or summary) worded for each surface. All three are named:
    a surface that cannot reach the line names another's wording on
    purpose (:meth:`no_hook`), never by an implicit fallback.

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
    def no_hook(cls, cli: _T, library: _T) -> Twins[_T]:
        """The twins of a line the hook cannot reach: the hook's wording is
        the library's, and resolving it there raises under
        :func:`strict_surfaces`."""
        return cls(cli=cli, library=library, hook=library, hook_reachable=False)

    @property
    def members(self) -> tuple[_T, ...]:
        """Each distinct wording once, in :data:`SURFACES` order: what the
        entry lists among its lines."""
        found: list[_T] = []
        for member in (self.cli, self.library, self.hook):
            if member not in found:
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
    "strict_surfaces",
    "unreachable_on_hook",
]
