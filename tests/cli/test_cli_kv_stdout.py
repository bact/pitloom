# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every subcommand's stdout is ``KEY=VALUE`` data lines only; summaries,
hints and ``-v`` details are ``INFO:`` lines on stderr.

One case per leaf subcommand of the real parser -- the completeness test
fails when a new subcommand has no case here.

See also: :mod:`tests.kv_helpers` (the line parser),
:mod:`pitloom.cli.kv_output` (the writer).
"""

from __future__ import annotations

import argparse
import ast
import shutil
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.__about__ import __version__
from pitloom.cli.parser import _build_parser
from tests.assemble.conftest import (
    _embed_sbom_entry,
    _make_dummy_wheel,
    _spdx3_json_with_subject,
)
from tests.assemble.embed_surfaces_shared import demo_project
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.kv_helpers import info_kv, info_lines, kv_stdout

_FRAGMENT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "fragments"
    / "dataset-fragment.spdx3.json"
)
_SBOM_PATH = ("PITLOOM_SBOM_OUTPUT_PATH",)
_FRAGMENT_LIST_KEYS = (
    "PATH",
    "ROLE",
    "REQUIRED",
    "EXISTS",
    "ELEMENTS",
    "SHA256",
    "MODIFIED",
    "SAME_DOCUMENT",
)
_SRC = Path(__file__).resolve().parents[2] / "src" / "pitloom"

#: Argv builder for a case: (tmp_path, monkeypatch) -> argv after ``loom``.
_Argv = Callable[[Path, pytest.MonkeyPatch], list[str]]


def _wheel(tmp_path: Path) -> Path:
    return _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")


def _wheel_with_sbom(tmp_path: Path, basename: str, content: str) -> str:
    wheel = _wheel(tmp_path)
    _embed_sbom_entry(wheel, basename, content)
    return str(wheel)


def _fragments_dir(tmp_path: Path) -> str:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    shutil.copy(_FRAGMENT, fragments / "a.json")
    return str(fragments)


def _project_with_fragment(tmp_path: Path) -> str:
    project = demo_project(
        tmp_path, '\n[tool.pitloom.fragment]\nfiles = ["f.spdx3.json"]\n'
    )
    shutil.copy(_FRAGMENT, project / "f.spdx3.json")
    return str(project)


def _fragment_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # Schema/SHACL validation needs the network; its outcome is not the
    # subject here, its output shape is.
    fragment = "pitloom.cli.commands.fragment"
    monkeypatch.setattr(f"{fragment}._import_spdx3_validate", object)
    monkeypatch.setattr(f"{fragment}._validate_spdx3_documents", lambda *a, **k: 0)
    del tmp_path
    return ["fragment", "validate", str(_FRAGMENT)]


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # The installed environment's content is not the subject here.
    monkeypatch.setattr(
        "pitloom.cli.commands.env.generate_env_sbom", lambda *a, **k: "{}"
    )
    return ["env", "-v", "-o", str(tmp_path / "env.json")]


#: Leaf subcommand -> (argv builder, keys of each stdout record, ``-v`` given).
_CASES: dict[str, tuple[_Argv, tuple[str, ...], bool]] = {
    "generate": (
        lambda t, _: (
            ["generate", str(demo_project(t)), "-v", "--offline"]
            + ["-o", str(t / "o.json")]
        ),
        _SBOM_PATH,
        True,
    ),
    "project": (
        lambda t, _: (
            ["project", str(demo_project(t)), "-v", "--offline"]
            + ["-o", str(t / "o.json")]
        ),
        _SBOM_PATH,
        True,
    ),
    "wheel": (
        lambda t, _: (
            ["wheel", str(_wheel(t)), "-v", "--offline"] + ["-o", str(t / "o.json")]
        ),
        _SBOM_PATH,
        True,
    ),
    "embed-wheel": (
        lambda t, _: ["embed-wheel", str(_wheel(t)), "-v", "--offline"],
        ("WHEEL", "SBOM"),
        False,  # -v has no effect there: a WARNING, no details
    ),
    "verify-wheel": (
        lambda t, _: [
            "verify-wheel",
            _wheel_with_sbom(
                t, "demo-1.0.0.spdx3.json", _spdx3_json_with_subject("demo", "1.0.0")
            ),
        ],
        ("WHEEL", "STATUS"),
        False,
    ),
    "validate-wheel": (
        lambda t, _: [
            "validate-wheel",
            _wheel_with_sbom(t, "demo-1.0.0.cdx.json", '{"bomFormat": "CycloneDX"}'),
        ],
        ("WHEEL", "STATUS"),
        False,
    ),
    "model": (
        lambda t, _: (
            ["model", str(SAFETENSORS_FIXTURE), "-v"] + ["-o", str(t / "o.json")]
        ),
        _SBOM_PATH,
        True,
    ),
    "enrich": (
        lambda t, _: (
            ["enrich", str(SAFETENSORS_FIXTURE), "-v"] + ["-o", str(t / "o.json")]
        ),
        _SBOM_PATH,
        True,
    ),
    "env": (_env, _SBOM_PATH, True),
    "merge": (
        lambda t, _: ["merge", _fragments_dir(t), "-o", str(t / "o.json")],
        _SBOM_PATH,
        False,
    ),
    "fragment validate": (_fragment_validate, ("FILE", "STATUS"), False),
    "fragment list": (
        lambda t, _: ["fragment", "list", "--project-dir", _project_with_fragment(t)],
        _FRAGMENT_LIST_KEYS,
        False,
    ),
    "id generate": (
        lambda t, _: (
            ["id", "generate", "--project-dir", str(demo_project(t))]
            + [str(t / "proj" / "demo"), "-o", str(t / "reg.json")]
        ),
        ("PITLOOM_ID_REGISTRY_PATH",),
        False,
    ),
    "id import": (
        lambda t, _: ["id", "import", str(_FRAGMENT), "-o", str(t / "reg.json")],
        ("PITLOOM_ID_REGISTRY_PATH",),
        False,
    ),
}


def _leaf_commands() -> set[str]:
    """Every leaf subcommand of the real parser, e.g. ``fragment list``."""

    def walk(parser: argparse.ArgumentParser, prefix: str) -> Iterator[str]:
        subs = [
            action
            for action in parser._actions  # pylint: disable=protected-access
            # pylint: disable-next=protected-access
            if isinstance(action, argparse._SubParsersAction)
        ]
        if not subs:
            yield prefix
        for sub in subs:
            for name, child in sub.choices.items():
                yield from walk(child, f"{prefix} {name}".strip())

    return set(walk(_build_parser(), ""))


def test_every_subcommand_has_a_case() -> None:
    """A new subcommand needs a case here, so its stdout is checked."""
    assert set(_CASES) == _leaf_commands()


@pytest.mark.parametrize("command", sorted(_CASES))
def test_stdout_is_key_value_only(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_argv, keys, verbose = _CASES[command]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *build_argv(tmp_path, monkeypatch)])

    assert __main__.main() == 0

    captured = capsys.readouterr()
    stdout_records = kv_stdout(captured.out)
    assert stdout_records, "a successful run prints at least one data line"
    assert all(tuple(record) == keys for record in stdout_records), stdout_records
    untagged = [
        line
        for line in captured.err.splitlines()
        if line and not line.startswith(("ERROR: ", "WARNING: ", "INFO: "))
    ]
    assert not untagged
    assert (info_kv(captured.err).get("PITLOOM_VERSION") == __version__) is verbose


@pytest.mark.parametrize(
    ("command", "summary"),
    [
        ("verify-wheel", "verify-wheel: 1 wheel(s) OK"),
        ("merge", "merge: merged 1 fragment(s)"),
        ("fragment validate", "fragment validate: 1 document(s) valid"),
        ("id import", "ID registry: holds 0 file(s) and 2 entit(y/ies)"),
    ],
)
def test_summary_is_an_info_line(
    command: str,
    summary: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A count is prose for a human: ``INFO:`` on stderr, not stdout."""
    monkeypatch.chdir(tmp_path)
    argv = _CASES[command][0](tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])

    assert __main__.main() == 0

    assert summary in info_lines(capsys.readouterr().err)


def test_fragment_validate_prints_one_line_per_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    second = tmp_path / "b.spdx3.json"
    shutil.copy(_FRAGMENT, second)
    argv = _fragment_validate(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["loom", *argv, str(second)])

    assert __main__.main() == 0

    out = capsys.readouterr().out
    assert [r["FILE"] for r in kv_stdout(out)] == [str(_FRAGMENT), str(second)]


def _writes_stdout(node: ast.AST) -> bool:
    """A ``print()`` not sent to ``sys.stderr``, or any ``sys.stdout`` use."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
        stream = next((k.value for k in node.keywords if k.arg == "file"), None)
        return stream is None or ast.unparse(stream) != "sys.stderr"
    return isinstance(node, ast.Attribute) and ast.unparse(node) == "sys.stdout"


def _stdout_writers() -> set[str]:
    """``<module>:<innermost function>`` of every stdout write in Pitloom."""
    writers: set[str] = set()
    for path in sorted(_SRC.rglob("*.py")):
        module = path.relative_to(_SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owner: dict[ast.AST, str] = {}
        for function in ast.walk(tree):  # outer functions come first
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner.update(dict.fromkeys(ast.walk(function), function.name))
        writers.update(
            f"{module}:{owner.get(node, '<module>')}"
            for node in ast.walk(tree)
            if _writes_stdout(node)
        )
    return writers


def test_only_kv_output_prints_to_stdout() -> None:
    """Only :func:`pitloom.cli.kv_output.print_kv` (data lines) and
    :func:`pitloom._sbom_io.write_stdout_lf` (an SBOM for ``-o -``) write
    stdout; every other ``print()`` goes to ``sys.stderr``."""
    assert _stdout_writers() == {
        "cli/kv_output.py:print_kv",
        "_sbom_io.py:write_stdout_lf",
    }
