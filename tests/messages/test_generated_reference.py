# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message reference in ``docs/messages.md`` and in the skills'
``known-limitations.md`` is generated from the catalogue by
``scripts/generate_message_reference.py``: the files hold exactly what the
script renders (bytes, LF), and the script rewrites only its block.

See also: tests/messages/test_drift_quotes.py (quotes elsewhere).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.messages import MESSAGES

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "generate_message_reference.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_message_reference", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load()
_TARGETS = [pytest.param(path, id=path.name) for path in gen.TARGETS]


@pytest.mark.parametrize("path", _TARGETS)
def test_a_target_holds_what_the_script_renders(path: Path) -> None:
    current = path.read_bytes()
    wanted = gen.replace_block(current.decode("utf-8"), gen.render()).encode("utf-8")
    assert current == wanted, (
        f"{path.relative_to(_ROOT).as_posix()} is stale: run "
        "'python scripts/generate_message_reference.py' and commit it"
    )
    assert b"\r" not in current


def test_the_table_has_a_row_per_code_in_order() -> None:
    rows = [r for r in gen.render().splitlines() if r.startswith("| `")]
    assert [r.split("`")[1] for r in rows] == sorted(MESSAGES)
    assert {r.count(" | ") for r in rows} == {5}


def test_a_pipe_in_a_cell_is_escaped() -> None:
    assert gen.cell("a | b\n c") == "a \\| b c"


@pytest.mark.parametrize(
    "text",
    [
        "no markers",
        f"{gen.BEGIN}\n{gen.BEGIN}\n{gen.END}",
        f"{gen.END}\n{gen.BEGIN}",
        f"{gen.BEGIN}",
    ],
    ids=["none", "twice", "reversed", "unclosed"],
)
def test_markers_that_are_not_one_pair_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="GENERATED|before"):
        gen.replace_block(text, "x")


def test_only_the_block_is_rewritten() -> None:
    before = f"head\n{gen.BEGIN}\nold\n{gen.END}\ntail\n"
    after = gen.replace_block(before, "new")
    assert after == f"head\n{gen.BEGIN}\nnew\n{gen.END}\ntail\n"
    assert gen.replace_block(after, "new") == after


def test_check_fails_with_a_diff_on_a_stale_target_and_write_fixes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.md"
    target.write_bytes(f"a\n{gen.BEGIN}\nold\n{gen.END}\nb\n".encode())
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.run([target], check=True) == 1
    err = capsys.readouterr().err
    assert "-old" in err and "+| Code |" in err and "stale" in err
    assert target.read_bytes().endswith(b"old\n" + gen.END.encode() + b"\nb\n")
    assert gen.run([target], check=False) == 0
    assert gen.run([target], check=True) == 0
    written = target.read_bytes()
    assert b"\r" not in written and b"\nold\n" not in written


def test_a_target_without_markers_is_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "t.md"
    target.write_bytes(b"nothing\n")
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.run([target], check=True) == 2
    assert capsys.readouterr().err.startswith("ERROR: t.md: ")


def test_the_command_line_checks_the_tree() -> None:
    run = subprocess.run(  # nosec B603
        [sys.executable, str(_SCRIPT), "--check"],
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src")},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
