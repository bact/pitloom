# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Reading a code back from a printed line: :data:`LINE_RE` finds it,
:func:`trusted_message` trusts it only when it is catalogued and the text
matches the entry, and no uncatalogued template ends in a token that reads
as a code.

See also: tests/messages/test_messages_emit.py (printing the code).
"""

from __future__ import annotations

import ast
import logging
import os
import re
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

from pitloom.core.lfs_pointer import warn_pointers_not_read
from pitloom.logging_config import CODE_PATTERN, configure_logging
from pitloom.messages import (
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LINE_RE,
    trusted_message,
)
from tests._lfs import lfs_pointer_bytes

_SRC = Path(__file__).resolve().parents[2] / "src"
_LOG = logging.getLogger("pitloom.test_messages_lines")
_HOSTILE = "x [lfs-pointer]"

#: Uncatalogued string constants ending in a token :data:`LINE_RE` reads as a
#: code, as (module, token). Shrink only.
_KNOWN_CODE_LIKE_ENDINGS = {
    # Not a line end: "<table> has moved to <this>. Update your config."
    ("core/_config_legacy.py", "[tool.pitloom.content-type]"),
}


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "WARNING: FILE=a: Git LFS pointer, content not read; "
            "run 'git lfs pull' for the content [lfs-pointer]",
            LFS_POINTER,
        ),
        (
            f"WARNING: FILE={_HOSTILE}: Git LFS pointer shipped (2 files); "
            "the build did not pull LFS content [lfs-pointer.shipped]",
            LFS_POINTER_SHIPPED,
        ),
        (
            "ERROR: model command failed: 'm.gguf': header is a Git LFS pointer "
            "[lfs-pointer.malformed]",
            LFS_POINTER_MALFORMED,
        ),
        # a catalogued code after an uncatalogued text: a value, not a code
        (f"WARNING: skipped {_HOSTILE}", None),
        # a level the entry is not said at, an uncatalogued code, no code
        (
            "INFO: FILE=a: Git LFS pointer shipped; the build did not pull LFS "
            "content [lfs-pointer.shipped]",
            None,
        ),
        ("ERROR: too large [git.too-large]", None),
        ("WARNING: FILE=a: Git LFS pointer, content not read; x", None),
        ("WARNING: FILE=a: header is a Git LFS pointer [lfs-pointer]\n", None),
    ],
    ids=lambda v: str(v)[:24],
)
def test_a_code_is_trusted_only_for_its_own_text(line: str, expected: object) -> None:
    assert trusted_message(line) is expected


def test_a_printed_value_ending_in_a_code_is_not_trusted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file named ``x [lfs-pointer]`` at the end of an uncatalogued line
    reads as a code, and is not trusted; at the end of a catalogued line's
    value it is the value, the real code still last."""
    configure_logging()
    _LOG.warning("not listed: %s", _HOSTILE)
    warn_pointers_not_read([_HOSTILE])
    forged, real = capsys.readouterr().err.splitlines()
    found = LINE_RE.fullmatch(forged)
    assert found is not None and found.group(3) == "lfs-pointer"
    assert trusted_message(forged) is None
    assert trusted_message(real) is LFS_POINTER


def test_the_loom_entry_point_prints_the_code(tmp_path: Path) -> None:
    """``loom model`` on a pointer, through the real entry point: one
    ``ERROR:`` line, its code last, trusted."""
    model = tmp_path / "m.gguf"
    model.write_bytes(lfs_pointer_bytes(b"abc"))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(_SRC), env.get("PYTHONPATH")])
    )
    run = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pitloom", "model", str(model), "-o", "o.json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
        timeout=300,
    )
    assert run.returncode == 1
    (line,) = run.stderr.decode("utf-8").splitlines()
    assert re.search(r" \[lfs-pointer\]\r?$", line), line
    assert trusted_message(line.rstrip("\r")) is LFS_POINTER


def _string_ends(tree: ast.AST) -> list[str]:
    """Every string constant of *tree* but a docstring, and the last literal
    part of every f-string."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
    }
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and node.values:
            node = node.values[-1]
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            found.append(node.value)
    return found


def test_no_uncatalogued_template_ends_in_a_code() -> None:
    """A line ending in `` [word.word]`` reads as a code: every such ending
    in the source is a known one."""
    ending = re.compile(rf" (\[{CODE_PATTERN}\])$")
    root = _SRC / "pitloom"
    found = {
        (path.relative_to(root).as_posix(), token)
        for path in sorted(root.rglob("*.py"))
        for text in _string_ends(ast.parse(path.read_bytes()))
        for token in ending.findall(text.rstrip())
    }
    assert found == _KNOWN_CODE_LIKE_ENDINGS
