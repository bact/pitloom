# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``bool`` argument of the library takes ``True`` or ``False`` (``None``
where it means "not given"): ``"false"`` or ``1`` is refused before anything
runs, as a :class:`~pitloom.messages.CodedTypeError` (``option-invalid``)
naming the parameter, never read as either value.

The documented API (``docs/api.md``) is walked, so a new entry point or
field with a ``bool`` parameter is covered without a new case here.

See also: tests/core/test_library_argument_types.py (the other wrong
types).
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.bool_arguments import check_bool_fields, checked_bools
from pitloom.core.internal_error import InternalError
from pitloom.messages import CodedTypeError, code_of

_API_PAGE = Path(__file__).parents[2] / "docs" / "api.md"
#: Documented elsewhere than the reference page: the config a caller builds.
_ALSO_PUBLIC = ("pitloom.core.config.PitloomConfig",)
#: The loom SDK checks its own arguments (its rule table), inside a run.
_OWN_CHECK = {"pitloom.loom.Run", "pitloom.loom.set_model"}
#: A value no bool parameter takes.
_TRUTHY = "false"


def _documented() -> Iterator[tuple[str, Any]]:
    """Each object ``docs/api.md`` documents, and :data:`_ALSO_PUBLIC`."""
    names = re.findall(r"^::: (\S+)$", _API_PAGE.read_text("utf-8"), re.M)
    for full in [*names, *_ALSO_PUBLIC]:
        module, _, attr = full.rpartition(".")
        yield full, getattr(importlib.import_module(module), attr)


def _is_bool_annotation(annotation: object) -> bool:
    """Whether *annotation* names ``bool`` alone or in a union, in any
    spelling (``Optional[bool]`` too): one the decorator would refuse to
    take is still walked here, so an undecorated one fails."""
    if annotation is bool:
        return True
    text = str(annotation).removeprefix("typing.")
    members = {member.strip() for member in text.split("|")}
    return "bool" in members or text == "Optional[bool]"


def _bool_names(function: Callable[..., object]) -> list[str]:
    """The ``bool`` (or ``bool | None``) parameters of *function*."""
    return [
        name
        for name, parameter in inspect.signature(function).parameters.items()
        if _is_bool_annotation(parameter.annotation)
    ]


def _callables(full: str, obj: Any) -> Iterator[tuple[str, Callable[..., object]]]:
    """*obj*, and for a class each public method, with its label."""
    yield full, obj
    if inspect.isclass(obj):
        for name, member in vars(obj).items():
            function = getattr(member, "__func__", member)
            if not name.startswith("_") and inspect.isfunction(function):
                yield f"{full}.{name}", getattr(obj, name)


def _cases() -> list[Any]:
    """Each documented callable (a class's public methods and its
    constructor included) with each of its ``bool`` parameters."""
    return [
        pytest.param(function, name, id=".".join([*label.rsplit(".", 2)[-2:], name]))
        for full, obj in _documented()
        if full not in _OWN_CHECK
        for label, function in _callables(full, obj)
        if callable(function)
        for name in _bool_names(function)
    ]


def _expected_name(function: Callable[..., object], name: str) -> str:
    """A dataclass field is named ``<class>.<field>``, a parameter bare."""
    if inspect.isclass(function) and dataclasses.is_dataclass(function):
        return f"{function.__name__}.{name}"
    return name


@pytest.mark.parametrize(("function", "name"), _cases())
def test_every_documented_bool_parameter_refuses_another_type(
    function: Callable[..., object], name: str
) -> None:
    """Refused before the call needs any other argument: the check runs
    first, so nothing is read, fetched or built."""
    with pytest.raises(CodedTypeError) as caught:
        function(**{name: _TRUTHY})
    assert code_of(caught.value) == "option-invalid"
    said = f"{_expected_name(function, name)}: must be True or False, got a string"
    assert str(caught.value) == f"{said} 'false'"


def test_the_walk_reaches_the_entry_points() -> None:
    """A guard against a walk that finds nothing and passes vacuously."""
    ids = {case.id for case in _cases()}
    assert {
        "assemble.generate.pretty",
        "assemble.generate_project_sbom.use_lockfile",
        "embed.embed_wheel_sbom.allow_signed_wheel",
        "embed.ConfigOverrides.trust_model_files",
        "build_options.BuildOptions.allow",
        "id_registry.IdRegistry.refuse_credentials",
        "IdRegistry.load.refuse_credentials",
        "config.PitloomConfig.pretty",
        "assemble.merge_fragments.adopt_fragment_roots",
        "remote.fetch_git_project.trust_model_files",
    } <= ids
    assert len(ids) >= 80


@pytest.mark.parametrize(
    ("call", "said"),
    [
        pytest.param(
            lambda: _sdk().run("o.json", pretty="false"),
            "loom SDK: pretty: must be True or False, got a string 'false'",
            id="run",
        ),
    ],
)
def test_the_loom_sdk_says_a_python_bool(call: Callable[[], object], said: str) -> None:
    """The loom SDK's own rule table says Python's spelling, as the rest of
    the library does, not TOML's ``true or false``."""
    with pytest.raises(CodedTypeError) as caught:
        call()
    assert str(caught.value) == said


def _sdk() -> Any:
    """:mod:`pitloom.loom`, imported when a case runs."""
    return importlib.import_module("pitloom.loom")


@checked_bools
def _sample(
    first: bool, second: bool | None = None, *, third: bool = False, other: int = 0
) -> tuple[bool, bool | None, bool, int]:
    """A function with a positional, an optional and a keyword-only bool."""
    return first, second, third, other


@pytest.mark.parametrize(
    ("args", "kwargs", "name", "got"),
    [
        pytest.param((1,), {}, "first", "an integer 1", id="positional"),
        pytest.param((True, "no"), {}, "second", "a string 'no'", id="optional"),
        pytest.param((True,), {"third": None}, "third", "None", id="keyword-none"),
        pytest.param((), {"first": b""}, "first", "a value of type bytes", id="kw"),
    ],
)
def test_the_decorator_refuses_by_position_and_by_keyword(
    args: tuple[object, ...], kwargs: dict[str, object], name: str, got: str
) -> None:
    with pytest.raises(CodedTypeError) as caught:
        _sample(*args, **kwargs)  # type: ignore[arg-type]
    assert str(caught.value) == f"{name}: must be True or False, got {got}"


def test_the_decorator_takes_bools_and_none_where_optional() -> None:
    """Defaults stay unchecked; a non-bool parameter is not looked at."""
    assert _sample(True) == (True, None, False, 0)
    assert _sample(False, None, third=True, other=7) == (False, None, True, 7)


@pytest.mark.parametrize(
    "annotation",
    ["Optional[bool]", "typing.Optional[bool]", "None | bool", "bool | int"],
)
def test_another_spelling_of_a_bool_is_loud(annotation: str) -> None:
    """Never skipped silently: a parameter the check would miss."""

    def spelt(value: object = None) -> object:
        return value

    spelt.__annotations__ = {"value": annotation}
    with pytest.raises(InternalError, match="spell its bool annotation"):
        checked_bools(spelt)


def test_a_container_of_bools_is_no_bool_parameter() -> None:
    def holder(values: object = (), flag: bool = False) -> object:
        return values, flag

    holder.__annotations__ = {"values": "list[bool]", "flag": "bool"}
    assert checked_bools(holder)(values=[True])  # list[bool] not checked


def test_a_function_without_a_bool_is_refused() -> None:
    def plain(value: int = 0) -> int:
        return value

    with pytest.raises(InternalError, match="has no bool parameter"):
        checked_bools(plain)


def test_an_evaluated_bool_annotation_is_checked() -> None:
    """``bool`` itself, not its text (a module without postponed
    annotations), is read as a ``bool`` parameter."""

    def plain(flag=False):  # type: ignore[no-untyped-def]
        return flag

    plain.__annotations__ = {"flag": bool}
    with pytest.raises(CodedTypeError, match="^flag: must be True or False"):
        checked_bools(plain)(flag="false")


@dataclasses.dataclass
class _Fields:
    """A dataclass whose bool fields are checked."""

    flag: bool = False
    maybe: bool | None = None
    count: int = 0

    def __post_init__(self) -> None:
        check_bool_fields(self)


@pytest.mark.parametrize(
    ("kwargs", "said"),
    [
        ({"flag": 0}, "_Fields.flag: must be True or False, got an integer 0"),
        ({"maybe": "yes"}, "_Fields.maybe: must be True or False, got a string 'yes'"),
    ],
    ids=["bool", "optional"],
)
def test_a_dataclass_names_the_class_and_field(
    kwargs: dict[str, object], said: str
) -> None:
    with pytest.raises(CodedTypeError) as caught:
        _Fields(**kwargs)  # type: ignore[arg-type]
    assert str(caught.value) == said


def test_a_dataclass_takes_bools_none_and_other_fields() -> None:
    assert _Fields(True, None, 3) == _Fields(flag=True, maybe=None, count=3)
    assert _Fields(maybe=False).maybe is False


@pytest.mark.parametrize("value", [object(), _Fields], ids=["object", "class"])
def test_only_a_dataclass_instance_is_checked(value: object) -> None:
    with pytest.raises(InternalError, match="not a dataclass instance"):
        check_bool_fields(value)
