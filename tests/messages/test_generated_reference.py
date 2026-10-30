# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The message reference in ``docs/message-codes.md`` and in each skill's
``references/messages.md`` is generated from the catalogue by
``scripts/generate_message_reference.py``: the files hold exactly what the
script renders (bytes, LF), the script rewrites only its block, and the block
has a section per code that says every line of it, in Markdown that lints
clean (no line over 80 characters outside a table or a code block, none that
starts with ``<``).

See also: tests/messages/test_drift_quotes.py (quotes elsewhere).
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess  # nosec B404
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.messages import FRAMES, MESSAGES

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
_TARGETS = [
    pytest.param(path, id=path.relative_to(_ROOT).parent.as_posix())
    for path in gen.TARGETS
]


@pytest.mark.parametrize("path", _TARGETS)
def test_a_target_holds_what_the_script_renders(path: Path) -> None:
    current = path.read_bytes()
    wanted = gen.replace_block(current.decode("utf-8"), gen.render()).encode("utf-8")
    assert current == wanted, (
        f"{path.relative_to(_ROOT).as_posix()} is stale: run "
        "'python scripts/generate_message_reference.py' and commit it"
    )
    assert b"\r" not in current


def test_git_checks_every_target_out_with_lf() -> None:
    """A Windows checkout (``core.autocrlf``) writes CRLF, so the bytes
    differ from the render, unless ``.gitattributes`` pins the file to LF."""
    rules = (_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    for path in gen.TARGETS:
        assert f"{path.relative_to(_ROOT).as_posix()} text eol=lf" in rules


def test_the_docs_catalogue_has_its_own_page() -> None:
    """The guide links the page that holds the codes, and holds none itself."""
    guide = (_ROOT / "docs" / "messages.md").read_text(encoding="utf-8")
    assert gen.BEGIN not in guide and "(message-codes.md)" in guide
    assert _ROOT / "docs" / "message-codes.md" in gen.TARGETS


def _sections() -> dict[str, list[str]]:
    """The lines of each code's section, by code."""
    found: dict[str, list[str]] = {}
    for line in gen.render().splitlines():
        if line.startswith("### `"):
            found[line.split("`")[1]] = []
        elif found:
            found[next(reversed(found))].append(line)
    return found


def test_the_index_and_the_sections_list_every_code_in_order() -> None:
    rows = [r for r in gen.render().splitlines() if r.startswith("| [`")]
    assert [r.split("`")[1] for r in rows] == sorted(MESSAGES)
    assert {r.count(" | ") for r in rows} == {3}
    assert list(_sections()) == sorted(MESSAGES)
    for code in MESSAGES:
        assert f"](#{gen.slug(code)})" in gen.render()
    assert gen.slug("lfs-pointer/shipped") == "lfs-pointershipped"


@pytest.mark.parametrize("code", sorted(MESSAGES), ids=str)
def test_a_section_says_what_its_code_means_and_every_line(code: str) -> None:
    message = MESSAGES[code]
    text = "\n".join(_sections()[code])
    for bullet in ("Level", "Means", "SBOM effect", "Pitloom did", "Lines"):
        assert f"- **{bullet}**: " in text or f"- **{bullet}**:\n" in text
    assert "- **Tell the user**: " in text  # every entry's actor is the user
    assert (gen.ERROR_RULE.split()[0] in text) is ("ERROR" in message.levels)
    for line in message.lines:
        assert f"  {line.level}: {line.shown} [{code}]" in text.splitlines()


def test_the_prefixes_are_the_catalogues_frames() -> None:
    rows = [r for r in gen.render().splitlines() if "<text>` |" in r]
    assert len(rows) == len(FRAMES)
    for frame in FRAMES:
        head = f"| `{frame.shown}<text>` |"
        assert any(r.startswith(head) and frame.surface in r for r in rows), head


def test_the_block_lints_clean() -> None:
    """Outside code blocks: no code span with a space at an edge; outside
    tables too, no line over 80 characters and none starting with ``<``
    (an HTML block)."""
    fenced = False
    for line in gen.render().splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
        if fenced:
            continue
        assert all(span == span.strip() for span in re.findall(r"`([^`]+)`", line))
        if line.startswith(("|", "<!--")):
            continue
        assert len(line) <= gen.WIDTH, line
        assert not line.lstrip().startswith(("<", "`<")), line


@pytest.mark.parametrize(
    ("text", "first", "rest"),
    [
        ("word " * 40, "- **Means**: ", "  "),
        ("a " + "x" * 72 + " <file> and " + "y" * 70 + " `<file>` and more", "", ""),
    ],
    ids=["fill", "angle"],
)
def test_wrap_fills_to_80_and_never_starts_a_line_with_an_angle(
    text: str, first: str, rest: str
) -> None:
    lines = gen.wrap(text, first, rest)
    assert len(lines) > 1 and lines[0].startswith(first)
    assert all(ln.startswith(rest) for ln in lines[1:])
    assert " ".join(" ".join(lines).split()) == " ".join(f"{first}{text}".split())
    for line in lines[1:]:
        assert not line[len(rest) :].startswith(("<", "`<")), line
    assert all(len(ln) <= gen.WIDTH for ln in lines)


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
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src"), "PYTHONUTF8": "1"},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
