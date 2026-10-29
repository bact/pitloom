# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The catalogue's entries keep its rules (the code grammar, the closed
vocabularies, a line for each level and set of values), and the package
imports in either order with :mod:`pitloom.logging_config`.

See also: tests/messages/test_messages_fields.py (templates, fields and
frames), tests/messages/test_messages_emit.py (the code on a record and an
exception), tests/messages/test_messages_lines.py (reading a line back).
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess  # nosec B404
import sys
from collections.abc import Collection
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.evidence import REASON_CODES
from pitloom.messages import (
    CONDITIONS,
    LFS_CLONE_LINE,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    LFS_PULL_LINE,
    MESSAGES,
    Line,
    Message,
)
from pitloom.messages._catalogue import _by_code

_SRC = str(Path(__file__).resolve().parents[2] / "src")
_SHIPPED_LINE = LFS_POINTER_SHIPPED.lines[0]


def test_every_entry_is_keyed_by_its_own_code() -> None:
    assert all(code == entry.code for code, entry in MESSAGES.items())
    assert {LFS_POINTER, LFS_POINTER_SHIPPED, LFS_POINTER_MALFORMED} <= set(
        MESSAGES.values()
    )


def test_the_vocabulary_is_closed_at_23_cause_words() -> None:
    """Causes only: a response (``skipped``), a kind of message
    (``summary``), a domain (``licence``) or a merged synonym is not one."""
    assert len(CONDITIONS) == 23
    assert {m.condition for m in MESSAGES.values()} <= CONDITIONS
    assert {
        "ambiguous",
        "missing",
        "needs-build",
        "network-failed",
        "not-recordable",
        "timeout",
        "unsafe",
        "wrong-format",
    } <= CONDITIONS
    assert CONDITIONS.isdisjoint(
        {
            "decision",
            "fetch-failed",
            "id-collision",
            "ignored",
            "left-out",
            "licence",
            "mismatch",
            "missing-library",
            "new-id",
            "not-a-model",
            "not-this-format",
            "refused",
            "rejected",
            "skipped",
            "summary",
            "usage",
            "wrapper",
        }
    )


def test_the_lfs_pointer_code_is_the_evidence_reason() -> None:
    """One condition, one code: the warning's code and the provenance's
    ``Reason: lfs-pointer`` stay equal."""
    assert LFS_POINTER.code in REASON_CODES


def test_the_family_and_the_levels_come_from_the_code_and_the_lines() -> None:
    assert (LFS_POINTER_SHIPPED.family, LFS_POINTER_MALFORMED.family) == (
        "lfs-pointer",
        "lfs-pointer-malformed",
    )
    assert LFS_POINTER.levels == {"WARNING", "ERROR"}
    assert LFS_POINTER_SHIPPED.levels == {"WARNING"}
    assert hash(dataclasses.replace(LFS_POINTER)) == hash(LFS_POINTER)


@pytest.mark.parametrize(
    "code", ["lfs-pointer/" + "a" * 28, "lfs-pointer/x1-2", "lfs-pointer/shipped"]
)
def test_a_family_slash_variant_up_to_40_characters_is_a_code(code: str) -> None:
    assert dataclasses.replace(LFS_POINTER, code=code).code == code


def test_a_code_catalogued_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="catalogued twice"):
        _by_code([LFS_POINTER, LFS_POINTER])


def test_a_variant_never_changes_its_familys_condition() -> None:
    odd = dataclasses.replace(LFS_POINTER_SHIPPED, condition="malformed")
    with pytest.raises(ValueError, match="its family's is 'lfs-pointer'"):
        _by_code([LFS_POINTER, odd])
    assert len(_by_code([LFS_POINTER, LFS_POINTER_MALFORMED])) == 2


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"code": "LFS"}, "is not a code"),
        ({"code": "lfs-pointer x"}, "is not a code"),
        ({"code": "lfs-pointer.shipped"}, "is not a code"),
        ({"code": "lfs-pointer/a/b"}, "is not a code"),
        ({"code": "lfs--pointer"}, "is not a code"),
        ({"code": "lfs-pointer-"}, "is not a code"),
        ({"code": "lfs-pointer/"}, "is not a code"),
        ({"code": "lfs-pointer/-a"}, "is not a code"),
        ({"code": "1fs-pointer"}, "is not a code"),
        ({"code": "lfs-pointer/" + "a" * 29}, "is not a code"),
        ({"code": "sbom"}, "reserved"),
        ({"code": "pitloom/x"}, "reserved"),
        ({"condition": "broken"}, "unknown condition"),
        ({"effect": "fatter"}, "unknown effect"),
        ({"actor": "agent"}, "unknown actor"),
        ({"lines": ()}, "no lines"),
        ({"lines": (_SHIPPED_LINE, _SHIPPED_LINE)}, "one line twice"),
        ({"advice": " "}, "empty field"),
        ({"summary": ""}, "empty field"),
        ({"did": "\n"}, "empty field"),
        ({"subject_key": "file"}, "subject key"),
        ({"subject_key": "PATH"}, "subject key"),
        ({"since": "0.22"}, "since"),
        ({"since": "v0.22.0"}, "since"),
        ({"since": "0.022.0"}, "since"),
    ],
    ids=lambda value: str(value)[:30],
)
def test_an_entry_breaking_a_rule_is_refused(
    change: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        dataclasses.replace(LFS_POINTER_SHIPPED, **change)


def test_line_for_picks_the_one_line_naming_the_values() -> None:
    malformed = LFS_POINTER_MALFORMED
    assert LFS_POINTER_SHIPPED.line_for("WARNING", {"file", "count"}) == (_SHIPPED_LINE)
    assert malformed.line_for("WARNING", {"file"}).template.startswith("FILE=")
    assert malformed.line_for("WARNING", ["format", "file"]).template.startswith(
        "FORMAT="
    )
    for line in (LFS_PULL_LINE, LFS_CLONE_LINE):
        assert LFS_POINTER.line_for("WARNING", {"file", "count"}, line) is line


@pytest.mark.parametrize(
    ("message", "level", "names", "line", "match"),
    [
        (LFS_POINTER, "WARNING", {"file", "count"}, None, "2 name"),
        (LFS_POINTER, "WARNING", {"file", "count"}, _SHIPPED_LINE, "not one"),
        (LFS_POINTER, "ERROR", {"path"}, None, "0 name"),
        (LFS_POINTER_SHIPPED, "ERROR", {"file", "count"}, None, "0 name"),
        (LFS_POINTER_SHIPPED, "WARNING", {"file"}, None, "0 name"),
    ],
    ids=["two-lines", "another-line", "too-few", "level", "names"],
)
def test_line_for_refuses_when_it_cannot_tell(
    message: Message,
    level: str,
    names: Collection[str],
    line: Line | None,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        message.line_for(level, names, line)


@pytest.mark.parametrize(
    "first", ["pitloom.messages", "pitloom.logging_config", "pitloom.core.lfs_pointer"]
)
def test_the_package_imports_first_in_a_fresh_interpreter(first: str) -> None:
    """Each order of the two modules (and the warning's own module first)
    loads both, with no cycle. ``pitloom`` is an empty package, so the
    module named first is reached through its own imports only."""
    code = "\n".join(
        [
            "import importlib, sys, types",
            "bare = types.ModuleType('pitloom')",
            f"bare.__path__ = [{str(Path(_SRC) / 'pitloom')!r}]",
            "sys.modules['pitloom'] = bare",
            f"importlib.import_module({first!r})",
            "import pitloom.messages, pitloom.logging_config",
            "print(pitloom.messages.LFS_POINTER.code)",
        ]
    )
    run = subprocess.run(  # nosec B603
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        check=False,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr.decode("utf-8", "replace")
    assert run.stdout.decode("ascii").strip() == "lfs-pointer"


def test_logging_config_never_imports_the_catalogue() -> None:
    source = (Path(_SRC) / "pitloom" / "logging_config.py").read_text("utf-8")
    imported = {
        alias.name if isinstance(node, ast.Import) else node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported and not {n for n in imported if n.startswith("pitloom.messages")}
