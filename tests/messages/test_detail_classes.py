# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The proof behind the ratchet's ``DETAIL_EXC``
(``scripts/message_inventory/_scope.py``): a raise of one of its classes is
left out of the count because a wrapper says it, so each (class, raise site)
is a :class:`Case` run through a surface Pitloom itself calls. The class's
``__init__`` is spied on to prove the raise came from that site; then the
outcome is checked by the case's kind:

- ``detail``: a coded line, record or exception holds the escaped first 40
  characters of the exception's text;
- ``carrier``: a coded line of the case's code is said from the payload (a
  cap's reason), the exception's text neither required nor forbidden;
- ``signal``: control flow: the surface goes on and says no uncoded
  ``WARNING:`` or ``ERROR:``.

This module holds the harness and the meta-tests: the table's names are
``DETAIL_EXC``; each class name has one definition in ``src/``; each raise
of a table name in ``src/`` (a model reader's aside, detail by where it is)
sits in a (file, function) the table lists, and each listed site raises.

The site meta-test reads a raise by the name it spells (dotted names too,
which is how ``argparse``'s are matched). It misses a dotted raise of a class
the table keys by its bare name, an aliased import, ``err = X(...); raise
err`` and a factory (``model_parameters._over_cap()``): the ratchet counts
an alias or a dotted name outside ``DETAIL_EXC``, and the factory's raises
have their own cases (``FACTORY_CASES`` in test_detail_classes_archives.py),
whose spy also checks the factory's caller against the site. A second
raise of one class in a listed function (``read_lock_bytes`` raises
``LockFileRefusedError`` three times, its type check twice and the cap once)
needs no case of its own when it says the same code in the same way: the
case proves the function's class, not each line.

See also: tests/messages/test_detail_classes_text.py (the command line,
requirements and markers), tests/messages/test_detail_classes_files.py
(files, fragments, registries, lock files) and
tests/messages/test_detail_classes_archives.py (wheels and models);
tests/scripts/message_inventory/test_scope_detail.py (the scope rule).
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, TypeAlias

import pytest

from pitloom import __main__
from pitloom.logging_config import CODE_ATTR, one_line
from pitloom.messages import code_of, trusted_message
from tests._message_inventory import REPO_ROOT, load

pytestmark = pytest.mark.platform  # source paths, the spy's frame file names

#: The topic modules holding the cases.
CASE_MODULES = (
    "tests.messages.test_detail_classes_text",
    "tests.messages.test_detail_classes_files",
    "tests.messages.test_detail_classes_archives",
)
#: The model readers' package: a raise there is detail by where it is.
_READERS = "src/pitloom/extract/ai_model/"
_READER_DISPATCH = "src/pitloom/extract/ai_model/reader.py"
#: Names that are no class of Pitloom's: ``argparse``'s, and a factory
#: parameter (``archive_members(on_duplicate=...)``).
NOT_CLASSES = frozenset(
    {"argparse.ArgumentError", "argparse.ArgumentTypeError", "on_duplicate"}
)
_SHOWN = 40


class Env(NamedTuple):
    """What a trigger may use."""

    tmp: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]
    caplog: pytest.LogCaptureFixture


@dataclass(frozen=True)
class Outcome:
    """What a surface left: its stderr lines, its records, the exception it
    raised and whether it went on (exit 0, no exception)."""

    lines: tuple[str, ...] = ()
    records: tuple[logging.LogRecord, ...] = ()
    error: BaseException | None = None
    ok: bool = True


#: Runs a surface.
Trigger: TypeAlias = Callable[[Env], Outcome]


def cap_reason(exc: Any) -> str:
    """The reason of the cap *exc* carries, as an ``over-cap`` line says it."""
    return str(exc.cap.reason)


@dataclass(frozen=True)
class Case:
    """One (name, raise site) of ``DETAIL_EXC`` and how to prove it."""

    #: The ``DETAIL_EXC`` name.
    name: str
    #: The class raised, as ``(module, attribute)``.
    exc: tuple[str, str]
    #: The raise: its file under the repository and its function's
    #: qualified name, as the inventory names them.
    site: tuple[str, str]
    #: ``detail``, ``carrier`` or ``signal``.
    kind: str
    #: Runs the surface.
    trigger: Trigger
    #: The code of the line that says it (``detail``, ``carrier``).
    code: str | None = None
    #: The payload a carrier's line says.
    payload: Callable[[Any], str] | None = None
    #: Where the instance is built when not at the raise (a factory), as
    #: ``(file, function name)``; the ``site`` must then be its caller.
    made_in: tuple[str, str] | None = None
    #: Tells two cases of one site apart in the test id.
    tag: str = ""
    #: The builder is reached through a callback, so the site is any frame
    #: above it, not its direct caller.
    relayed: bool = False


def case_id(case: Case) -> str:
    """A short test id: the class, the raise's function, the tag or kind."""
    name = case.name.rpartition(".")[2]
    return f"{name}-{case.site[1].rpartition('.')[2]}-{case.tag or case.kind}"


class _Made(NamedTuple):
    exc: BaseException
    file: str
    function: str
    #: The frames above the one that built it, nearest first, each as
    #: ``(file, function)``.
    above: tuple[tuple[str, str], ...]


def _spy(monkeypatch: pytest.MonkeyPatch, cls: type[BaseException]) -> list[_Made]:
    """Every instance of *cls* built from now on, with the file and function
    of the frame that built it and the frames above it."""
    made: list[_Made] = []
    original = cls.__init__

    def __init__(self: BaseException, *args: Any, **kwargs: Any) -> None:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        if caller is not None:
            code = caller.f_code
            above = []
            outer = caller.f_back
            while outer is not None:
                above.append(
                    (Path(outer.f_code.co_filename).as_posix(), outer.f_code.co_name)
                )
                outer = outer.f_back
            made.append(
                _Made(
                    self,
                    Path(code.co_filename).as_posix(),
                    code.co_name,
                    tuple(above),
                )
            )
        original(self, *args, **kwargs)

    monkeypatch.setattr(cls, "__init__", __init__)
    return made


def resolve(exc: tuple[str, str]) -> type[BaseException]:
    """The class *exc* names."""
    found = getattr(importlib.import_module(exc[0]), exc[1])
    if not (isinstance(found, type) and issubclass(found, BaseException)):
        raise TypeError(f"{exc} is no exception class")
    return found


def cli(env: Env, *argv: object) -> Outcome:
    """``loom *argv`` through ``__main__.main()``, as the entry point runs it."""
    env.monkeypatch.setattr(sys, "argv", ["loom", *map(str, argv)])
    try:
        status = __main__.main()
    except SystemExit as exc:  # argparse's refusal
        status = exc.code if isinstance(exc.code, int) else 1
    err = env.capsys.readouterr().err
    return Outcome(
        tuple(line.removesuffix("\r") for line in err.split("\n") if line),
        tuple(env.caplog.records),
        ok=status == 0,
    )


def call(env: Env, function: Callable[[], object]) -> Outcome:
    """*function*, a library entry, run with its records captured."""
    try:
        function()
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:
        return Outcome(records=tuple(env.caplog.records), error=exc, ok=False)
    return Outcome(records=tuple(env.caplog.records))


def _chain(exc: BaseException | None) -> Iterator[BaseException]:
    while exc is not None:
        yield exc
        exc = exc.__cause__ or exc.__context__


def coded(outcome: Outcome) -> list[tuple[str, str]]:
    """Each ``(code, text)`` the outcome says with a code: a trusted stderr
    line, a coded record, a coded exception."""
    said = []
    for line in outcome.lines:
        message = trusted_message(line)
        if message is not None:
            said.append((message.code, line))
    for record in outcome.records:
        code = getattr(record, CODE_ATTR, None)
        if isinstance(code, str):
            said.append((code, record.getMessage()))
    for exc in _chain(outcome.error):
        code = code_of(exc)
        if code is not None:
            said.append((code, str(exc)))
    return said


def uncoded(outcome: Outcome) -> list[str]:
    """Each ``WARNING:`` or ``ERROR:`` the outcome says without a code."""
    lines = [
        line
        for line in outcome.lines
        if line.startswith(("WARNING: ", "ERROR: ")) and trusted_message(line) is None
    ]
    records = [
        record.getMessage()
        for record in outcome.records
        if record.levelno >= logging.WARNING
        and (record.name == "pitloom" or record.name.startswith("pitloom."))
        and not isinstance(getattr(record, CODE_ATTR, None), str)
    ]
    return lines + records


def _at(made: _Made, file: str, function: str) -> bool:
    return made.file.endswith(file.removeprefix("src/")) and made.function == function


def _called_from(made: _Made, case: Case) -> bool:
    """Whether the instance was built under the case's site: for a factory,
    by the site itself (the factory's direct caller), or, *relayed*, with the
    site anywhere above."""
    file, function = case.site[0].removeprefix("src/"), case.site[1].rpartition(".")[2]
    frames = made.above if case.relayed else made.above[:1]
    return any(f.endswith(file) and name == function for f, name in frames)


def prove(case: Case, env: Env) -> None:
    """Run *case*: the class is raised at its site, then said by its kind."""
    env.caplog.set_level(logging.INFO)
    made = _spy(env.monkeypatch, resolve(case.exc))
    outcome = case.trigger(env)
    site_file, site_function = case.site[0], case.site[1].rpartition(".")[2]
    file, function = case.made_in or (site_file, site_function)
    mine = [
        m.exc
        for m in made
        if _at(m, file, function) and (case.made_in is None or _called_from(m, case))
    ]
    assert mine, (
        case.name,
        case.site,
        [(m.file, m.function, m.above[:1]) for m in made],
    )
    said = coded(outcome)
    if case.kind == "signal":
        assert outcome.ok, outcome
        assert not uncoded(outcome), uncoded(outcome)
        return
    if case.kind == "detail":
        needle = one_line(mine[0], _SHOWN)
    else:
        assert case.kind == "carrier" and case.payload is not None
        needle = case.payload(mine[0])
    assert needle, case
    assert any(code == case.code and needle in text for code, text in said), (
        needle,
        said,
        outcome.lines,
    )


def make_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> Env:
    """The :class:`Env` of a test, its SBOM time pinned."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    return Env(tmp_path, monkeypatch, capsys, caplog)


# -- meta-tests ----------------------------------------------------------------


def _all_cases() -> list[Case]:
    cases: list[Case] = []
    for name in CASE_MODULES:
        cases.extend(importlib.import_module(name).CASES)
    return cases


def _detail_exc() -> frozenset[str]:
    load()
    scope = importlib.import_module("message_inventory._scope")
    return frozenset(scope.DETAIL_EXC)


def _sources() -> Iterator[tuple[str, ast.Module]]:
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        yield (
            path.relative_to(REPO_ROOT).as_posix(),
            ast.parse(path.read_bytes(), filename=str(path)),
        )


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def _raises(tree: ast.AST, scope: str = "") -> Iterator[tuple[str, str]]:
    """``(raised name, qualified function)`` of each raise in *tree*."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _raises(node, f"{scope}{node.name}.")
        elif isinstance(node, ast.Raise) and node.exc is not None:
            name = _dotted(node.exc)
            if name is not None:
                yield name, scope.removesuffix(".")
        else:
            yield from _raises(node, scope)


def test_the_table_names_are_detail_exc() -> None:
    """A name added to ``DETAIL_EXC`` needs a proof; a proved name dropped
    from it would be counted again."""
    assert {case.name for case in _all_cases()} == _detail_exc()


def test_each_class_name_has_one_definition_in_src() -> None:
    """``DETAIL_EXC`` is keyed on the bare name: a second class of that name
    would be left out of the count unproved. A Pitloom class has one
    definition; ``packaging``'s (``InvalidMarker``) none, so no class of
    Pitloom's takes its name."""
    owners = {
        case.name: case.exc[0].partition(".")[0]
        for case in _all_cases()
        if case.name not in NOT_CLASSES
    }
    found: dict[str, list[str]] = {name: [] for name in owners}
    for file, tree in _sources():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in found:
                found[node.name].append(file)
    expected = {name: int(owner == "pitloom") for name, owner in owners.items()}
    assert {name: len(files) for name, files in found.items()} == expected, found
    assert set(owners.values()) == {"pitloom", "packaging"}


def test_each_case_names_the_class_defined_under_its_name() -> None:
    for case in _all_cases():
        if case.name not in NOT_CLASSES:
            assert resolve(case.exc).__name__ == case.name, case


def test_each_raise_of_a_table_name_is_a_listed_site() -> None:
    """A new raise of a listed class at an unproved site fails here, and so
    does a listed site that raises it no more."""
    names = _detail_exc()
    raised = {
        (name, (file, function))
        for file, tree in _sources()
        if not file.startswith(_READERS) or file == _READER_DISPATCH
        for name, function in _raises(tree)
        if name in names
    }
    assert raised == {(case.name, case.site) for case in _all_cases()}


def test_each_kind_is_known_and_coded_kinds_name_a_code() -> None:
    for case in _all_cases():
        assert case.kind in {"detail", "carrier", "signal"}, case
        assert (case.code is None) is (case.kind == "signal"), case
        assert (case.payload is None) is (case.kind != "carrier"), case
