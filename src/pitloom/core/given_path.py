# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A path that keeps the spelling the user gave, for a message to name.

:class:`pathlib.Path` normalises what it is given (``https://h/x.whl``
becomes ``https:/h/x.whl``, a ``//`` collapsed), so a message naming the
``Path`` names something the user never typed. :class:`TypedPath` (a
command-line argument, the ``type=`` of every path-typed argument) and
:class:`GivenPath` (a path resolved for the read) keep the typed spelling;
:func:`given_spelling` reads it, and the catalogue writes every path field
through it (:func:`pitloom.messages._field_writers.file_text`).

No Pitloom import: the message writers import this module.

See also: :mod:`pitloom.core.given_file` (reading a file the user named).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

__all__ = ["GivenPath", "TypedPath", "given_spelling", "keep_spelling"]

if TYPE_CHECKING:
    _ConcretePath = Path
else:
    # Python 3.10 and 3.11 cannot subclass Path itself (it has no flavour of
    # its own): the concrete class of this platform is subclassed instead.
    _ConcretePath = type(Path())


class TypedPath(_ConcretePath):
    """A :class:`pathlib.Path` built from one string, as ``Path(text)``,
    that keeps *text* as :attr:`given` (built from a :class:`GivenPath` or a
    :class:`TypedPath`, the spelling that one keeps). A path derived from it
    (``/``,
    :meth:`~pathlib.Path.absolute`, :attr:`~pathlib.PurePath.parent`) is a
    new path: its :attr:`given` is its own text."""

    __slots__ = ("_typed",)
    _typed: str

    def __new__(cls, *args: str | os.PathLike[str]) -> TypedPath:
        self = super().__new__(cls, *args)
        if len(args) == 1 and isinstance(args[0], (str, TypedPath)):
            self._typed = os.fspath(given_spelling(args[0]))
        return self

    def __reduce__(self) -> tuple[type[TypedPath], tuple[str], str]:
        """Rebuilt from the path itself, with :attr:`given` as its state
        (:meth:`__setstate__`), so :mod:`copy` and :mod:`pickle` keep both:
        a path resolved from what was typed (``/abs/dir/x.whl`` typed
        ``x.whl``) stays that file."""
        return (type(self), (str(self),), self.given)

    def __setstate__(self, state: str) -> None:
        """Keep the typed spelling *state* (:meth:`__reduce__`)."""
        self._typed = state

    @property
    def given(self) -> str:
        """The text the path was built from, else its own text."""
        typed: str | None = getattr(self, "_typed", None)
        return str(self) if typed is None else typed


class GivenPath(str):
    """A path resolved for the read (made absolute against the current
    directory, or a configuration file's directory) that keeps the spelling
    the user gave, for a message to name (:func:`given_spelling`), as
    :func:`~pitloom.messages.targets.input_not_found` asks."""

    given: str

    def __new__(
        cls, resolved: str | os.PathLike[str], given: str | os.PathLike[str]
    ) -> GivenPath:
        self = super().__new__(cls, os.fspath(resolved))
        self.given = os.fspath(given_spelling(given))
        return self

    def __getnewargs__(self) -> tuple[str, str]:  # type: ignore[override]
        """The arguments :meth:`__new__` needs, so :mod:`copy` and
        :mod:`pickle` (``dataclasses.asdict`` of a configuration holding
        one) rebuild it with its spelling."""
        return (str(self), self.given)


def given_spelling(path: str | os.PathLike[str]) -> str | os.PathLike[str]:
    """The spelling of *path* the user gave: its :class:`GivenPath` or
    :class:`TypedPath` one, else *path* itself."""
    return path.given if isinstance(path, (GivenPath, TypedPath)) else path


def keep_spelling(path: Path, source: str | os.PathLike[str]) -> Path:
    """*path*, derived from *source* (resolved, or spelt as the file system
    lists it), keeping the spelling *source* was given in when it keeps one:
    a message about *path* names what the user typed."""
    if isinstance(source, (GivenPath, TypedPath)):
        return TypedPath(GivenPath(path, source.given))
    return path
