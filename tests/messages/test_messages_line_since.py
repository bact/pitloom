# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A line's ``since``: the first release that prints that text at that
level. A line the last release did not print (the released-lines snapshot,
``tests/fixtures/message-catalogue/released-lines.tsv``) says a later
release; the reference says the release of each line that differs from its
code's; ``--snapshot`` writes the snapshot back.

See also: tests/messages/test_messages_types.py (the entry's rules) and
tests/messages/test_generated_reference.py (the pages).
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pitloom.messages import MESSAGES, Line, Message
from pitloom.messages._types import release_key, warning_twins

pytestmark = pytest.mark.platform  # reads and writes a file in bytes, LF

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "generate_message_reference.py"
_SHIPPED = MESSAGES["lfs-pointer/shipped"]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_message_reference", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load()
# Importable once the generator has put the repository root on the path.
sections = importlib.import_module("scripts.message_reference.sections")
snapshot = importlib.import_module("scripts.message_reference.snapshot")


def _with_lines(since: str, *lines: Line) -> Message:
    return dataclasses.replace(_SHIPPED, since=since, lines=lines, subject_key=None)


def _line(template: str, since: str | None = None) -> Line:
    return Line(level="WARNING", template=template, since=since)


def test_a_line_new_since_the_last_release_says_so() -> None:
    """A line the snapshot's release printed (same code, level and text)
    prints since that release or earlier; any other line, since a later one
    (a reworded line is new)."""
    release, released = snapshot.load(_ROOT / snapshot.SNAPSHOT)
    assert len(released) > 100  # the snapshot was read
    wrong = [
        (code, line.level, line.template, line.effective_since(message))
        for code, message in MESSAGES.items()
        for line in message.lines
        if ((code, line.level, line.template) in released)
        is (release_key(line.effective_since(message)) > release_key(release))
    ]
    assert wrong == []


@pytest.mark.parametrize(
    ("entry", "line", "match"),
    [
        ("0.22.0", "0.21.0", "before 0.22.0"),
        ("0.10.0", "0.9.0", "before 0.10.0"),  # numbers, not strings
        ("0.22.0", "0.25", "since '0.25'"),
        ("0.22.0", "v0.25.0", "since 'v0.25.0'"),
        ("0.22.0", "0.025.0", "since '0.025.0'"),
        ("0.22.0", "", "since ''"),
    ],
)
def test_line_since_rules(entry: str, line: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _with_lines(entry, _line("a", line))


@pytest.mark.parametrize(
    ("entry", "line", "effective"),
    [
        ("0.22.0", None, "0.22.0"),
        ("0.22.0", "0.22.0", "0.22.0"),
        ("0.22.0", "0.25.0", "0.25.0"),
        ("0.9.0", "0.10.0", "0.10.0"),  # numbers, not strings
    ],
)
def test_a_valid_line_since_is_its_effective_since(
    entry: str, line: str | None, effective: str
) -> None:
    message = _with_lines(entry, _line("a", line))
    assert message.lines[0].effective_since(message) == effective


def test_one_text_at_one_level_is_one_line_whatever_its_since() -> None:
    with pytest.raises(ValueError, match="one line twice"):
        _with_lines("0.22.0", _line("a"), _line("a", "0.25.0"))


def test_a_warning_twin_keeps_its_lines_since() -> None:
    ours = (
        Line(level="ERROR", template="a", since="0.25.0"),
        Line(level="ERROR", template="b"),
    )
    assert [ln.since for ln in warning_twins(ours)] == ["0.25.0", None] * 2


def test_the_since_note_names_each_later_release_and_its_lines() -> None:
    message = _with_lines(
        "0.22.0",
        _line("a"),
        _line("b", "0.25.0"),
        _line("c", "0.25.0"),
        _line("d", "0.22.0"),
        _line("e", "0.25.0"),
        _line("f", "0.100.0"),
        _line("g", "0.24.0"),
    )
    assert sections.since_note(message) == (
        "0.22.0; line 7: 0.24.0; lines 2-3, 5: 0.25.0; line 6: 0.100.0"
    )
    assert sections.since_note(_with_lines("0.22.0", _line("a", "0.22.0"))) is None


@pytest.mark.parametrize("code", sorted(MESSAGES))
def test_a_section_says_since_only_where_a_line_differs(code: str) -> None:
    message = MESSAGES[code]
    bullets = [ln for ln in sections.section(message) if ln.startswith("- **Since**")]
    differs = any(ln.effective_since(message) != message.since for ln in message.lines)
    assert len(bullets) == int(differs)
    if code == "input-not-found":
        assert bullets[0].startswith(f"- **Since**: {message.since}; lines ")
        assert bullets[0].endswith(": 0.25.0")


def test_the_snapshot_round_trips(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.main(["--snapshot", "99.0.0"]) == 0
    assert "INFO: " in capsys.readouterr().err
    path = tmp_path / snapshot.SNAPSHOT
    data = path.read_bytes()
    assert b"\r" not in data and data.endswith(b"\n")
    release, found = snapshot.load(path)
    assert release == "99.0.0"
    assert found == {
        (code, ln.level, ln.template) for code, m in MESSAGES.items() for ln in m.lines
    }
    assert snapshot.dump(release, sorted(found)) == data  # sorted rows


@pytest.mark.parametrize(
    ("release", "status"), [("0.25", 2), ("v1.0.0", 2), ("0.22.0", 1)]
)
def test_a_snapshot_is_refused_for_a_bad_or_too_early_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    release: str,
    status: int,
) -> None:
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.main(["--snapshot", release]) == status
    assert capsys.readouterr().err.startswith("ERROR: ")
    assert not (tmp_path / snapshot.SNAPSHOT).exists()


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"code\tWARNING\ta\n", "first line"),
        (b"# released-lines 0.25\n", "first line"),
        (b"# released-lines 0.25.0\ncode\tWARNING\n", "row"),
        (b"# released-lines 0.25.0\r\ncode\tWARNING\ta\r\n", "first line"),
        (b"# released-lines 0.25.0\ncode\tWARNING\ta\r\n", "row"),
        (b"# released-lines 0.25.0\ncode\tWARNING\ta\n\nb\tINFO\tc\n", "row ''"),
        (b"# released-lines 0.25.0\ncode\tWARNING\ta\ncode\tWARNING\ta\n", "twice"),
        (b"# released-lines 0.25.0\ncode\tWARNING\ta", "no LF"),
        (b"# released-lines 0.25.0", "no LF"),
    ],
)
def test_a_malformed_snapshot_is_refused(
    tmp_path: Path, data: bytes, match: str
) -> None:
    path = tmp_path / "released-lines.tsv"
    path.write_bytes(data)
    with pytest.raises(ValueError, match=match):
        snapshot.load(path)


def test_a_template_with_a_tab_is_not_snapshotted() -> None:
    message = _with_lines("0.22.0", _line("a\tb"))
    with pytest.raises(ValueError, match="tab"):
        snapshot.rows({"x": message})
