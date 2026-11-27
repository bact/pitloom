# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``DETAIL_EXC`` cases said from text: ``argparse``'s refusals of a typed
value (the parser's ``option-invalid`` line carries their text), a
requirement, marker or specifier ``packaging`` is not let parse (Pitloom's
own refusal: nesting, an overlong number), the self-reference expansion's
caps, a marker whose extra gate cannot be isolated, a Poetry table and a
count the Hub states.

See also: tests/messages/test_detail_classes.py (the harness and the
meta-tests).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import pytest
from packaging.markers import Marker
from packaging.requirements import Requirement

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import _dep_scope
from pitloom.core import extra_gate, pep508, requirements
from pitloom.core.pep440 import MAX_VERSION_NUMBER_DIGITS
from pitloom.core.project import ProjectMetadata
from pitloom.extract.lock import apply_locked_dependencies
from pitloom.extract.project import read_project
from pitloom.extract.remote.huggingface_field import hub_producer_and_count
from tests._deep_marker import nested_marker
from tests.messages.test_detail_classes import (
    Case,
    Env,
    Outcome,
    Trigger,
    call,
    cap_reason,
    case_id,
    cli,
    make_env,
    prove,
)

pytestmark = pytest.mark.platform  # projects, lock files, the entry point

_OVERLONG = "1" * (MAX_VERSION_NUMBER_DIGITS + 1)
_PARSER = "src/pitloom/cli/parser.py"
_OPTIONS = "src/pitloom/cli/options.py"
_ID_ARGS = "src/pitloom/cli/_id_args.py"
_GATE = "src/pitloom/core/extra_gate.py"
_PEP508 = "src/pitloom/core/pep508.py"
_REQS = "src/pitloom/core/requirements.py"
_HATCHLING = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n'
    '[project]\nname = "demo"\nversion = "1.0"'
)
_POETRY = (
    '[build-system]\nrequires = ["poetry-core"]\n'
    'build-backend = "poetry.core.masonry.api"\n\n'
    '[tool.poetry]\nname = "demo"\nversion = "1.0"\ndescription = ""\n'
    'authors = []\n\n[tool.poetry.dependencies]\npython = "^3.10"'
)


def _option(
    function: str, file: str, *argv: str, name: str = "TypeError", tag: str = ""
) -> Case:
    """``loom *argv``, refused by ``argparse.Argument<name>`` raised in
    *function*."""
    return Case(
        f"argparse.Argument{name}",
        ("argparse", f"Argument{name}"),
        (file, function),
        "detail",
        lambda env: cli(env, *argv),
        code="option-invalid",
        tag=tag,
    )


def _project(root: Path, body: str, backend: str = _HATCHLING) -> Path:
    """A project ``demo`` whose ``pyproject.toml`` is *backend*, then *body*."""
    (root / "demo").mkdir(exist_ok=True)
    (root / "demo" / "__init__.py").write_bytes(b"")
    (root / "pyproject.toml").write_bytes(f"{backend}\n{body}".encode())
    return root


def _read(env: Env, body: str) -> Outcome:
    project = _project(env.tmp, body)
    return call(env, lambda: read_project(project))


def _sbom(env: Env, body: str) -> Outcome:
    project = _project(env.tmp, body)
    return call(env, lambda: generate_project_sbom(project))


def _locked(env: Env, name: str, content: str) -> Outcome:
    (env.tmp / name).write_bytes(content.encode())
    return call(
        env, lambda: apply_locked_dependencies(ProjectMetadata(name="pkg"), env.tmp)
    )


# -- requirements, markers, specifiers ----------------------------------------


def _nested_extra(env: Env) -> Outcome:
    """An extra's requirement nesting at the cap: tagged with its extra, one
    level more."""
    marker = nested_marker(pep508.MAX_MARKER_NESTING).replace('"', "'")
    return _read(env, f'[project.optional-dependencies]\ndev = ["x; {marker}"]\n')


def _self_reference(env: Env) -> Outcome:
    """A self-reference whose marker, joined to the nested one, is over."""
    marker = nested_marker(pep508.MAX_MARKER_NESTING).replace('"', "'")
    return _read(
        env,
        "[project.optional-dependencies]\n"
        "all = [\"demo[dev]; os_name == 'a'\"]\n"
        f'dev = ["x; {marker}"]\n',
    )


def _expansion_markers(env: Env) -> Outcome:
    env.monkeypatch.setattr(requirements, "MAX_EXPANSION_MARKERS", 1)
    return _read(
        env,
        "[project.optional-dependencies]\n"
        "all = [\"demo[mid]; os_name == 'a'\"]\n"
        "mid = [\"demo[dev]; os_name == 'b'\"]\n"
        'dev = ["x"]\n',
    )


def _expansion_entries(env: Env) -> Outcome:
    env.monkeypatch.setattr(requirements, "MAX_EXPANSION_ENTRIES", 1)
    return _read(
        env,
        '[project.optional-dependencies]\nall = ["demo[dev]"]\ndev = ["x", "y"]\n',
    )


def _too_deep_requirement(env: Env) -> Outcome:
    """``packaging`` out of stack: Pitloom's ``nested too deep`` refusal."""
    real = Requirement

    def requirement(text: str) -> Requirement:
        if text == "deep":
            raise RecursionError
        return real(text)

    env.monkeypatch.setattr(pep508, "Requirement", requirement)
    return _sbom(env, 'dependencies = ["deep", "x"]\n')


def _too_deep_marker(env: Env) -> Outcome:
    real = Marker

    def marker(text: str) -> Marker:
        if "deep" in text:
            raise RecursionError
        return real(text)

    env.monkeypatch.setattr(pep508, "Marker", marker)
    return _locked(
        env,
        "pylock.toml",
        'lock-version = "1.0"\ncreated-by = "t"\n[[packages]]\nname = "a"\n'
        'version = "1"\nmarker = "\'deep\' in dependency_groups"\n',
    )


def _overlong_marker(env: Env) -> Outcome:
    return _locked(
        env,
        "pylock.toml",
        'lock-version = "1.0"\ncreated-by = "t"\n[[packages]]\nname = "a"\n'
        f'version = "1"\nmarker = "\'dev\' in dependency_groups and '
        f"python_version > '{_OVERLONG}'\"\n",
    )


def _packaging(
    name: str, kind: str, trigger: Trigger, code: str | None = None, tag: str = ""
) -> Case:
    module, function = {
        "InvalidRequirement": ("packaging.requirements", "parse_requirement"),
        "InvalidMarker": ("packaging.markers", "parse_marker"),
    }[name]
    return Case(
        name, (module, name), (_PEP508, function), kind, trigger, code=code, tag=tag
    )


def _over_cap(function: str, trigger: Trigger, tag: str) -> Case:
    return Case(
        "_OverCap",
        ("pitloom.core.requirements", "_OverCap"),
        (_REQS, function),
        "carrier",
        trigger,
        code="over-cap",
        payload=cap_reason,
        tag=tag,
    )


def _pipfile(env: Env) -> Outcome:
    lock = {
        "_meta": {"pipfile-spec": 6},
        "default": {"a": {"version": f"=={_OVERLONG}"}},
    }
    return _locked(env, "Pipfile.lock", json.dumps(lock))


_REQUIREMENT_CASES = [
    _packaging(
        "InvalidRequirement",
        "detail",
        lambda env: _locked(env, "requirements.txt", f"a=={_OVERLONG}\n"),
        "over-cap",
        "pins",
    ),
    _packaging("InvalidRequirement", "signal", _too_deep_requirement, tag="deep"),
    _packaging(
        "InvalidMarker", "detail", _nested_extra, "requirement-invalid", "extra"
    ),
    _packaging("InvalidMarker", "detail", _overlong_marker, "over-cap", "pylock"),
    _packaging(
        "InvalidMarker", "detail", _too_deep_marker, "lock-entry-malformed", "deep"
    ),
    _packaging("InvalidMarker", "signal", _self_reference, tag="expansion"),
    Case(
        "InvalidSpecifier",
        ("packaging.specifiers", "InvalidSpecifier"),
        ("src/pitloom/core/pep440.py", "parse_specifier_set"),
        "signal",
        _pipfile,
    ),
    _over_cap("_Expansion._walk", _self_reference, "nesting"),
    _over_cap("_Expansion._walk", _expansion_markers, "markers"),
    _over_cap("_Expansion._count", _expansion_entries, "entries"),
]

# -- extra gates ---------------------------------------------------------------


def _gate(dependency: str, mangle: str = "") -> Trigger:
    """A project depending on *dependency*; its marker's text read with
    *mangle* after it, as no ``packaging`` spelling has it."""

    def trigger(env: Env) -> Outcome:
        if mangle:
            real = extra_gate.read_gate
            env.monkeypatch.setattr(
                _dep_scope, "read_gate", lambda marker: real(marker + mangle)
            )
        return _sbom(env, f"dependencies = [{dependency!r}]\n")

    return trigger


def _gate_over_nesting(env: Env) -> Outcome:
    env.monkeypatch.setattr(extra_gate, "MAX_MARKER_NESTING", 0)
    return _gate("x; extra == 'a' and (os_name == 'b' or os_name == 'c')")(env)


def _gate_recursion(env: Env) -> Outcome:
    def parse(self: object) -> NoReturn:
        raise RecursionError

    # pylint: disable-next=protected-access
    env.monkeypatch.setattr(extra_gate._GateParser, "parse", parse)
    return _gate("x; extra == 'a'")(env)


def _gate_case(function: str, trigger: Trigger, tag: str = "") -> Case:
    return Case(
        "MarkerShapeError",
        ("pitloom.core.extra_gate", "MarkerShapeError"),
        (_GATE, function),
        "signal",
        trigger,
        tag=tag,
    )


_GATE_CASES = [
    _gate_case("_GateParser.__init__", _gate("x; extra == 'a'", " ~")),
    _gate_case("_GateParser.parse", _gate("x; extra == 'a'", " )")),
    _gate_case("_GateParser._next", _gate("x; extra == 'a'", " and")),
    _gate_case("_GateParser._or", _gate("x; extra == 'a' or os_name == 'b'")),
    _gate_case("_GateParser._atom", _gate("x; extra != 'a'"), "operator"),
    _gate_case("_GateParser._atom", _gate("x; extra == ''"), "empty"),
    _gate_case("read_gate", _gate_over_nesting, "nesting"),
    _gate_case("read_gate", _gate_recursion, "recursion"),
]

# -- the command line ----------------------------------------------------------

_ARGPARSE_CASES = [
    _option(
        "fingerprint_argument",
        "src/pitloom/cli/_parser_credentials.py",
        "project",
        "--accept-url-credential",
        "nope",
    ),
    _option("namespace_arg", _ID_ARGS, "id", "generate", "--namespace", "no iri"),
    _option("registry_file_arg", _ID_ARGS, "id", "generate", "-o", "-"),
    _option("entity_arg", _ID_ARGS, "id", "generate", "-e", "x:"),
    _option("_build_timeout_arg", _OPTIONS, "project", "--build-timeout", "soon"),
    _option("_flag_integer", _OPTIONS, "project", "--max-source-metadata-bytes", "a"),
    _option("byte_budget", _OPTIONS, "project", "--max-source-metadata-bytes", "3"),
    _option(
        "positive_byte_ceiling", _OPTIONS, "project", "--max-model-extract-bytes", "0"
    ),
    _option("creation_datetime", _OPTIONS, "project", "--creation-datetime", "now"),
    _option("non_empty_path", "src/pitloom/cli/_path_args.py", "wheel", "-o", ""),
    _option(
        "non_empty_name",
        "src/pitloom/cli/_path_args.py",
        "embed-wheel",
        "--sbom-basename",
        "",
    ),
    *(
        _option(
            f"{action}.__call__",
            _PARSER,
            "project",
            flag,
            value,
            name="Error",
            tag=action,
        )
        for action, flag, value in (
            ("_CreatorTypeAction", "--creator-type", "person"),
            ("_CreatorEmailAction", "--creator-email", "a@example.com"),
        )
    ),
]

# -- Poetry, the Hub -----------------------------------------------------------


def _poetry_markers(env: Env) -> Outcome:
    pytest.importorskip("poetry.core")
    project = _project(env.tmp, 'x = { version = "^1.0", markers = 5 }\n', _POETRY)
    return call(env, lambda: read_project(project))


_OTHER_CASES = [
    Case(
        "_MarkersTypeError",
        ("pitloom.extract.project._poetry_requirements", "_MarkersTypeError"),
        ("src/pitloom/extract/project/_poetry_requirements.py", "_markers"),
        "detail",
        _poetry_markers,
        code="requirement-invalid",
    ),
    Case(
        "ParameterCountRejected",
        ("pitloom.core.model_parameters", "ParameterCountRejected"),
        ("src/pitloom/core/model_parameters.py", "stated_parameter_count"),
        "detail",
        lambda env: call(
            env, lambda: hub_producer_and_count({"safetensors_total": "7B"}, {}, "o/m")
        ),
        code="parameter-count-invalid",
    ),
]


CASES = [*_ARGPARSE_CASES, *_REQUIREMENT_CASES, *_GATE_CASES, *_OTHER_CASES]


@pytest.mark.parametrize("case", CASES, ids=[case_id(c) for c in CASES])
def test_a_detail_class_is_said_by_its_kind(
    case: Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prove(case, make_env(tmp_path, monkeypatch, capsys, caplog))
