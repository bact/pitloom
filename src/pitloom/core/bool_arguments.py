# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The one check of every ``bool`` argument a library caller gives, read
from the parameter's annotation (``bool``, or ``bool | None`` where ``None``
means "not given"): :func:`checked_bools` for a function or method,
:func:`check_bool_fields` for a dataclass. A truthy string (``"false"``)
or ``1`` is refused (``option-invalid``, a
:class:`~pitloom.messages.CodedTypeError`), never read as either value.

No leading underscore: the entry points of :mod:`pitloom.assemble`,
:mod:`pitloom.embed`, :mod:`pitloom.id_registry` and the configuration
dataclasses of :mod:`pitloom.core` import it.

See also: :mod:`pitloom._loom_args` (the loom SDK's own rule table).
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
from collections.abc import Callable
from typing import Final, NamedTuple, ParamSpec, TypeVar

from pitloom.core.internal_error import InternalError
from pitloom.messages.config import Parameter, invalid_type

#: A ``bool`` parameter's annotation as text, and whether ``None`` is
#: taken (the default "not given").
_BOOL_ANNOTATIONS: Final = {"bool": False, "bool | None": True}

_P = ParamSpec("_P")
_R = TypeVar("_R")


def require_bool(value: object, name: str, *, optional: bool = False) -> None:
    """Refuse *value*, given as the library parameter *name*, unless it is
    a ``bool`` (or ``None`` when *optional*).

    Raises:
        pitloom.messages.CodedTypeError: *value* is of another type
            (``option-invalid``, ``must be True or False``).
    """
    if isinstance(value, bool) or (optional and value is None):
        return
    raise invalid_type(Parameter(name), "python-bool", value)


def _bool_optional(annotation: object, where: str) -> bool | None:
    """Whether *annotation* (of the parameter or field *where*) is a
    ``bool`` one, and takes ``None``: ``False`` for ``bool``, ``True`` for
    ``bool | None``, else ``None``. Read as source text: a string as
    written (a module with ``from __future__ import annotations``),
    ``bool`` itself as ``"bool"``, an evaluated union as Python prints it.

    Raises:
        pitloom.core.internal_error.InternalError: *annotation* names
            ``bool`` as a member of a union in another spelling
            (``Optional[bool]``, ``None | bool``), which would be skipped.
    """
    if annotation is bool:
        return False
    text = annotation if isinstance(annotation, str) else str(annotation)
    if text in _BOOL_ANNOTATIONS:
        return _BOOL_ANNOTATIONS[text]
    members = {member.strip() for member in text.split("|")}
    if "bool" in members or text.removeprefix("typing.") == "Optional[bool]":
        raise InternalError(f"{where}: spell its bool annotation 'bool | None'")
    return None


class _BoolParameter(NamedTuple):
    """A ``bool`` parameter: its name, its index when it may be passed by
    position (``None``: keyword-only), and whether it takes ``None``."""

    name: str
    position: int | None
    optional: bool


def _bool_parameters(function: Callable[..., object]) -> tuple[_BoolParameter, ...]:
    """The ``bool`` parameters of *function*, by its signature."""
    found: list[_BoolParameter] = []
    positional = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    signature = inspect.signature(function)
    for index, (name, parameter) in enumerate(signature.parameters.items()):
        optional = _bool_optional(
            parameter.annotation, f"{function.__qualname__}({name})"
        )
        if optional is not None:
            at = index if parameter.kind in positional else None
            found.append(_BoolParameter(name, at, optional))
    return tuple(found)


def checked_bools(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """*function*, refusing a non-``bool`` argument to each of its ``bool``
    parameters (:func:`require_bool`) before it runs: before any read,
    fetch or build. Read once, when decorated; a method's ``self`` or
    ``cls`` counts as a position.

    Raises:
        pitloom.core.internal_error.InternalError: *function* has no
            ``bool`` parameter (the decorator would check nothing), or one
            spelt otherwise (:func:`_bool_optional`).
    """
    parameters = _bool_parameters(function)
    if not parameters:
        raise InternalError(f"{function.__qualname__} has no bool parameter")

    @functools.wraps(function)
    def checked(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        for parameter in parameters:
            if parameter.name in kwargs:
                value = kwargs[parameter.name]
            elif parameter.position is not None and parameter.position < len(args):
                value = args[parameter.position]
            else:
                continue  # its default
            require_bool(value, parameter.name, optional=parameter.optional)
        return function(*args, **kwargs)

    return checked


def check_bool_fields(instance: object) -> None:
    """Refuse a non-``bool`` value of each ``bool`` field of *instance*, a
    dataclass, named ``<class>.<field>`` (``BuildOptions.allow``): its
    ``__post_init__`` calls this first.

    Raises:
        pitloom.messages.CodedTypeError: A field holds another type
            (``option-invalid``).
        pitloom.core.internal_error.InternalError: *instance* is not a
            dataclass, or a field's ``bool`` annotation is spelt otherwise
            (:func:`_bool_optional`).
    """
    if not dataclasses.is_dataclass(instance) or isinstance(instance, type):
        raise InternalError(f"not a dataclass instance: {type(instance).__name__}")
    owner = type(instance).__name__
    for field in dataclasses.fields(instance):
        optional = _bool_optional(field.type, f"{owner}.{field.name}")
        if optional is not None:
            require_bool(
                getattr(instance, field.name),
                f"{owner}.{field.name}",
                optional=optional,
            )


__all__ = ["check_bool_fields", "checked_bools", "require_bool"]
