# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The catalogue's entries keep its rules, and the package imports in either
order with :mod:`pitloom.logging_config`.

See also: tests/messages/test_messages_emit.py (the code on a record and an
exception), tests/messages/test_messages_lines.py (reading a line back).
"""

from __future__ import annotations

import ast
import dataclasses
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.core.evidence import REASON_CODES
from pitloom.messages import (
    CONDITIONS,
    LFS_POINTER,
    LFS_POINTER_MALFORMED,
    LFS_POINTER_SHIPPED,
    MESSAGES,
)
from pitloom.messages._catalogue import _by_code

_SRC = str(Path(__file__).resolve().parents[2] / "src")


def test_every_entry_is_keyed_by_its_own_code() -> None:
    assert all(code == entry.code for code, entry in MESSAGES.items())
    assert {LFS_POINTER, LFS_POINTER_SHIPPED, LFS_POINTER_MALFORMED} <= set(
        MESSAGES.values()
    )


def test_the_vocabulary_is_closed_at_36_condition_words() -> None:
    assert len(CONDITIONS) == 36
    assert {m.condition for m in MESSAGES.values()} <= CONDITIONS


def test_the_lfs_pointer_code_is_the_evidence_reason() -> None:
    """One condition, one code: the warning's code and the provenance's
    ``Reason: lfs-pointer`` stay equal."""
    assert LFS_POINTER.code in REASON_CODES


@pytest.mark.parametrize(
    "code", ["lfs-pointer/" + "a" * 28, "lfs-pointer/x1-2", "lfs-pointer/shipped"]
)
def test_a_family_slash_variant_up_to_40_characters_is_a_code(code: str) -> None:
    assert dataclasses.replace(LFS_POINTER, code=code).code == code


def test_a_code_catalogued_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="catalogued twice"):
        _by_code([LFS_POINTER, LFS_POINTER])


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
        ({"code": "lfs-pointer/" + "a" * 29}, "is not a code"),
        ({"code": "lfs-pointerx"}, "is not in"),
        ({"code": "other/shipped"}, "is not in"),
        ({"code": "sbom", "family": "sbom"}, "reserved"),
        ({"code": "pitloom/x", "family": "pitloom"}, "reserved"),
        ({"condition": "broken"}, "unknown condition"),
        ({"levels": frozenset()}, "levels"),
        ({"levels": frozenset({"DEBUG"})}, "levels"),
        ({"advice": " "}, "empty field"),
        ({"summary": ""}, "empty field"),
        ({"patterns": ()}, "empty field"),
        ({"patterns": ("",)}, "empty field"),
    ],
    ids=lambda value: str(value)[:30],
)
def test_an_entry_breaking_a_rule_is_refused(
    change: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        dataclasses.replace(LFS_POINTER, **change)


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
        [sys.executable, "-c", code], capture_output=True, check=False
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
