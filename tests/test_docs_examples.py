# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift-guard: the examples in the user manual still fit the current code.

Docs and skills have no test suite of their own (see CLAUDE.md's "Usage
surfaces"), so a renamed flag, a moved import or a retired config key would
leave a copy-paste example broken with every other test green. Each example is
checked, not run:

* ``loom`` commands (README, docs, skills, the example project's README) must
  parse with the real argument parser;
* Python blocks (README, docs) must parse, import what they import from
  ``pitloom``, and call it with keyword arguments it accepts;
* TOML blocks (README, docs) must use only keys ``[tool.pitloom]`` reads;
* YAML blocks (README, docs) that use the action must pass only inputs
  ``action.yml`` declares.

If a case fails, fix the example, unless the code is wrong, then fix both.

See also: :mod:`tests.test_docs_links` for links, and
:mod:`tests.test_build_timeout_examples` for ``--build-timeout`` values.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import inspect
import io
import json
import re
import shlex
from collections.abc import Iterator
from functools import cache
from types import ModuleType
from typing import Any

import pytest
import yaml

from pitloom._toml_io import TOMLDecodeError, load_toml_bytes
from pitloom.cli.parser import _build_parser
from pitloom.core._config_keys import KNOWN_KEYS
from tests._docs_scan import (
    CLI_DOC_FILES,
    DOC_FILES,
    REPO_ROOT,
    Snippet,
    fenced_blocks,
    inline_spans,
)

_SHELL_LANGS = frozenset({"", "bash", "console", "sh", "shell", "text"})
_PROGRAMS = ("loom", "pitloom", "python -m pitloom")
#: Commands the docs name as planned, not yet in the parser.
_PLANNED = frozenset({"loom fragment sign"})
_ACTION = "bact/pitloom"


def _end_at_pipe(command: str) -> str:
    return re.split(r"\s(?:\||&&|>)\s", command)[0]


def _cli_commands(text: str) -> Iterator[str]:
    """Each ``loom ...`` command of a shell block: a trailing backslash joins
    the next line, a pipe or redirect ends the command."""
    for raw in re.sub(r"\\\n\s*", " ", text).splitlines():
        line = re.sub(r"^\s*(?:\$ |- run: |run: )", "", raw).strip()
        if any(line == p or line.startswith(p + " ") for p in _PROGRAMS):
            yield _end_at_pipe(line)


def _collect_cli() -> list[Snippet]:
    cases: list[Snippet] = []
    for path in CLI_DOC_FILES:
        for block in fenced_blocks(path):
            if block.lang in _SHELL_LANGS | {"yaml", "yml"}:
                cases.extend(
                    Snippet(block.path, block.line, "block", cmd)
                    for cmd in _cli_commands(block.body)
                )
        cases.extend(
            Snippet(span.path, span.line, "inline", _end_at_pipe(span.body))
            for span in inline_spans(path)
            if any(span.body.startswith(p + " ") for p in _PROGRAMS)
        )
    return cases


def _collect(langs: frozenset[str]) -> list[Snippet]:
    return [
        block
        for path in DOC_FILES
        for block in fenced_blocks(path)
        if block.lang in langs
    ]


_CLI = _collect_cli()
_PYTHON = _collect(frozenset({"python"}))
_TOML = _collect(frozenset({"toml"}))
_YAML = _collect(frozenset({"yaml", "yml"}))


def _ids(cases: list[Snippet]) -> list[str]:
    return [f"{c.ident}:{c.body[:30]!r}" if c.lang else c.ident for c in cases]


def _parse_error(argv: list[str]) -> str | None:
    """What the real parser says about *argv*, ``None`` if it accepts it."""
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            _build_parser().parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (0, None):
            return err.getvalue().strip().splitlines()[-1]
    return None


@pytest.mark.parametrize("case", _CLI, ids=_ids(_CLI))
def test_documented_command_parses(case: Snippet) -> None:
    command = case.body
    if any(command.startswith(planned) for planned in _PLANNED):
        pytest.skip("named in the docs as planned")
    argv = shlex.split(command, comments=True)
    argv = argv[3:] if argv[:3] == ["python", "-m", "pitloom"] else argv[1:]
    argv = [re.sub(r"<[^>]+>", "X", arg) for arg in argv]
    if any(arg in {"-h", "--help", "--version"} for arg in argv):
        return
    error = _parse_error(argv)
    # An inline span often names a command without its operands.
    if error is not None and not (case.lang == "inline" and "required" in error):
        pytest.fail(f"{case.ident}: {command!r}: {error}")


def _imported_objects(tree: ast.AST) -> tuple[dict[str, Any], list[str]]:
    """The ``pitloom`` names a snippet imports, and what failed to import."""
    names: dict[str, Any] = {}
    errors: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "pitloom"
        ):
            continue
        for alias in node.names:
            try:
                names[alias.asname or alias.name] = _import_name(
                    node.module, alias.name
                )
            except ImportError:
                errors.append(f"cannot import {alias.name} from {node.module}")
    return names, errors


def _import_name(module: str, name: str) -> Any:
    parent: ModuleType = importlib.import_module(module)
    if hasattr(parent, name):
        return getattr(parent, name)
    return importlib.import_module(f"{module}.{name}")


def _resolve(node: ast.expr, names: dict[str, Any]) -> Any:
    """The object a dotted name stands for, ``None`` when it is not one of the
    imported ``pitloom`` names."""
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve(node.value, names)
        return None if base is None else getattr(base, node.attr, None)
    return None


def _snippet_errors(tree: ast.AST, names: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = _resolve(node.value, names)
            if base is not None and not hasattr(base, node.attr):
                errors.append(f"{ast.unparse(node.value)} has no {node.attr!r}")
        elif isinstance(node, ast.Call):
            problem = _call_error(node, names)
            if problem:
                errors.append(problem)
    return errors


def _call_error(node: ast.Call, names: dict[str, Any]) -> str | None:
    target = _resolve(node.func, names)
    if target is None or not callable(target):
        return None
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return None
    keywords = {kw.arg: None for kw in node.keywords if kw.arg}
    try:
        signature.bind_partial(*([None] * len(node.args)), **keywords)
    except TypeError as exc:
        return f"{ast.unparse(node.func)}(): {exc}"
    return None


@pytest.mark.parametrize("case", _PYTHON, ids=_ids(_PYTHON))
def test_documented_python_matches_api(case: Snippet) -> None:
    tree = ast.parse(case.body)
    names, errors = _imported_objects(tree)
    errors.extend(_snippet_errors(tree, names))
    assert not errors, f"{case.ident}: " + "; ".join(errors)


def _toml_key_errors(table: dict[str, Any], name: str) -> Iterator[str]:
    """Each key of *table* (``[tool.pitloom]`` or a table below it) that the
    config reader does not know."""
    known = KNOWN_KEYS.get(name)
    for key, value in table.items():
        if known is not None and key not in known:
            yield f"[tool.pitloom] {name or 'top level'}: unknown key {key!r}"
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, dict) and key in KNOWN_KEYS:
                yield from _toml_key_errors(child, key)


@pytest.mark.parametrize("case", _TOML, ids=_ids(_TOML))
def test_documented_toml_uses_known_keys(case: Snippet) -> None:
    try:
        data = load_toml_bytes(case.body.encode("utf-8"))
    except TOMLDecodeError as exc:
        pytest.fail(f"{case.ident}: not valid TOML: {exc}")
    tool = data.get("tool")
    table = tool.get("pitloom") if isinstance(tool, dict) else None
    if not isinstance(table, dict):
        pytest.skip("no [tool.pitloom] table")
    errors = list(_toml_key_errors(table, ""))
    assert not errors, f"{case.ident}: " + "; ".join(errors)


@cache
def _action_inputs() -> frozenset[str]:
    action = yaml.safe_load((REPO_ROOT / "action.yml").read_text(encoding="utf-8"))
    return frozenset(action["inputs"])


def _action_steps(node: Any) -> Iterator[dict[str, Any]]:
    """Every mapping of *node*, at any depth, that uses the action."""
    if isinstance(node, dict):
        if str(node.get("uses", "")).startswith(_ACTION):
            yield node
        for child in node.values():
            yield from _action_steps(child)
    elif isinstance(node, list):
        for child in node:
            yield from _action_steps(child)


@pytest.mark.parametrize("case", _YAML, ids=_ids(_YAML))
def test_documented_action_inputs_exist(case: Snippet) -> None:
    steps = list(_action_steps(yaml.safe_load(case.body)))
    if not steps:
        pytest.skip(f"does not use {_ACTION}")
    unknown = {
        key
        for step in steps
        for key in (step.get("with") or {})
        if key not in _action_inputs()
    }
    assert not unknown, f"{case.ident}: not inputs of action.yml: {sorted(unknown)}"


@pytest.mark.parametrize(
    ("name", "cases", "least"),
    [
        ("cli", _CLI, 100),
        ("python", _PYTHON, 5),
        ("toml", _TOML, 5),
        ("yaml", _YAML, 3),
    ],
)
def test_scan_found_examples(name: str, cases: list[Snippet], least: int) -> None:
    """Guard against a vacuous pass: a scan that stops finding examples (a
    changed fence style, a moved file) would leave its parametrized test with
    no cases to fail."""
    assert len(cases) >= least, f"only {len(cases)} {name} examples found"


def _unsorted_keys(node: Any) -> list[str]:
    """Object key lists under *node* that are not in sorted order."""
    if isinstance(node, list):
        return [bad for item in node for bad in _unsorted_keys(item)]
    if not isinstance(node, dict):
        return []
    bad = [] if list(node) == sorted(node) else [str(list(node))]
    return bad + [b for value in node.values() for b in _unsorted_keys(value)]


def test_provenance_envelope_examples_use_canonical_key_order() -> None:
    """A statement envelope (`schema` key) is RFC 8785 text, so its keys are
    sorted at every level; a hand-written example in another order misleads."""
    path = REPO_ROOT / "docs" / "metadata-provenance.md"
    envelopes = 0
    for block in fenced_blocks(path):
        if block.lang != "json" or '"schema"' not in block.body:
            continue
        envelopes += 1
        assert not _unsorted_keys(json.loads(block.body)), block.ident
    assert envelopes >= 5
