# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The current directory gone or not readable: one coded
``file-unreadable`` line (:func:`pitloom.core.current_dir.current_dir`),
and a command line parser that builds without it, so a command that needs
no current directory still runs.

See also: tests/_loom_child.py (the child ``loom``).
"""

from __future__ import annotations

import ast
import errno
import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from pitloom.core.current_dir import current_dir
from pitloom.messages import CodedValueError, code_of
from tests._loom_child import coded_lines, run_loom
from tests._wheel_fixtures import make_wheel

pytestmark = pytest.mark.platform

#: Windows cannot remove a process's current directory.
_CANNOT_REMOVE_CWD = sys.platform == "win32"
_SAID = "DIR=.: could not read for resolving relative paths; "
_ROOT = Path(__file__).resolve().parents[2]
_CLI = _ROOT / "src" / "pitloom" / "cli"
#: The smallest model fixture, absolute.
_MODEL = str(
    _ROOT / "tests" / "fixtures" / "aimodels" / "numpy" / "example-model-v1.npy"
)
#: Run first in the child: its current directory is removed before ``loom``
#: builds its parser.
_REMOVE_CWD = "import os\nos.rmdir(os.getcwd())\n"


def test_current_dir_is_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert current_dir().samefile(tmp_path)


def test_current_dir_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused ``getcwd`` (any OS) is said with the system's reason."""

    def refused(_cls: type[Path]) -> Path:
        raise PermissionError(errno.EACCES, "Permission denied")

    # Not os.getcwd: Python 3.10's pathlib bound it at import.
    monkeypatch.setattr(Path, "cwd", classmethod(refused))
    with pytest.raises(CodedValueError) as caught:
        current_dir()
    assert code_of(caught.value) == "file-unreadable"
    assert str(caught.value) == _SAID + "Permission denied"


@pytest.mark.skipif(_CANNOT_REMOVE_CWD, reason="Windows cannot remove the cwd")
def test_current_dir_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    with pytest.raises(CodedValueError) as caught:
        current_dir()
    assert code_of(caught.value) == "file-unreadable"
    assert str(caught.value).startswith(_SAID)


def _run_with_cwd_gone(argv: list[str], tmp_path: Path) -> CompletedProcess[bytes]:
    """``loom`` *argv* (``{abs}`` an absolute directory) in a child whose
    current directory is removed before its parser is built."""
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(_REMOVE_CWD, encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    args = [a.replace("{abs}", str(tmp_path / "abs")) for a in argv]
    done = run_loom(args, cwd, path=[shim])
    assert not cwd.exists()  # the shim ran
    assert b"Traceback" not in done.stderr
    return done


@pytest.mark.skipif(_CANNOT_REMOVE_CWD, reason="Windows cannot remove the cwd")
@pytest.mark.parametrize(
    ("argv", "code"),
    [
        # Absolute and missing: needs no current directory, so it says so.
        (["wheel", "{abs}/x-1-py3-none-any.whl"], "input-not-found"),
        # The default target is the current directory.
        (["project"], "file-unreadable"),
        # The default output is in the current directory.
        (["env"], "file-unreadable"),
    ],
    ids=["wheel", "project", "env"],
)
def test_cli_with_cwd_gone(argv: list[str], code: str, tmp_path: Path) -> None:
    """The parser builds (no traceback); each line is coded."""
    done = _run_with_cwd_gone(argv, tmp_path)
    assert done.returncode == 1
    assert list(coded_lines(done.stderr).values()) == [code]


@pytest.mark.skipif(_CANNOT_REMOVE_CWD, reason="Windows cannot remove the cwd")
@pytest.mark.parametrize(
    "argv",
    [
        ["env", "-o", "{abs}/out.json"],
        ["model", _MODEL, "-o", "{abs}/out.json"],
        ["enrich", _MODEL, "-o", "{abs}/out.json"],
        ["generate", "-o", "{abs}/out.json", _MODEL],
        ["wheel", "{abs}/demo-1.0-py3-none-any.whl", "-o", "{abs}/out.json"],
        ["embed-wheel", "{abs}/demo-1.0-py3-none-any.whl", "-o", "{abs}/out.whl"],
    ],
    ids=["env", "model", "enrich", "generate", "wheel", "embed-wheel"],
)
def test_cli_absolute_paths_with_cwd_gone(argv: list[str], tmp_path: Path) -> None:
    """Every path absolute: no current directory is needed, so none is
    read (an ID registry is resolved against it only when one is given)."""
    make_wheel(tmp_path / "abs")
    done = _run_with_cwd_gone(argv, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "file-unreadable" not in coded_lines(done.stderr).values()
    assert (tmp_path / "abs" / Path(argv[argv.index("-o") + 1]).name).is_file()


def _cwd_calls(node: ast.AST) -> list[str]:
    """Each ``*.cwd()``/``*.getcwd()`` call under *node*."""
    return [
        ast.unparse(n)
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"cwd", "getcwd"}
    ]


def test_no_parser_default_reads_the_cwd() -> None:
    """An ``add_argument`` default is evaluated when the parser is built:
    one that reads the current directory fails every command while it is
    gone. Such a default is ``None``, resolved in the command."""
    found = [
        f"{path.relative_to(_CLI)}:{call.lineno}: {text}"
        for path in sorted(_CLI.rglob("*.py"))
        for call in ast.walk(ast.parse(path.read_bytes()))
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr in {"add_argument", "set_defaults"}
        for keyword in call.keywords
        for text in _cwd_calls(keyword.value)
    ]
    assert len(list(_CLI.rglob("*.py"))) > 10  # the walk found the package
    assert not found
