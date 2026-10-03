# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check 17 of manual-cli-checks.md: one outcome per kind of AI model file,
whichever command reads it.

See also: ``_checks_wheel.py`` (the other single-purpose check module),
``_harness.py``.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from _fixtures import build_wheel, write_project
from _harness import (
    DATETIME,
    Context,
    check,
    expect,
    load_graph,
    run_loom,
    run_ok,
)

_TRUNCATED = "trunc.safetensors"
_LFS = "lfs.gguf"
_LFS_ONNX = "lfs.onnx"  # a suffix that admits any header, but not a pointer
_LFS_BIN = "lfs.bin"  # names no format: a warning with no FORMAT=
_POINTERS = (_LFS, _LFS_BIN, _LFS_ONNX)
_FILE = re.compile(r"FILE=(\S+): ")
_POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n"
_COMMON = ["--creation-datetime", DATETIME, "--offline"]


def _warnings_by_file(stderr_lines: list[str]) -> dict[str, list[str]]:
    """``WARNING:`` lines of *stderr_lines*, text after the file path, keyed by
    the file's name (the path itself differs by surface)."""
    found: dict[str, list[str]] = {}
    for line in stderr_lines:
        match = _FILE.search(line) if line.startswith("WARNING:") else None
        if match:
            name = Path(match.group(1)).name
            found.setdefault(name, []).append(line.replace(match.group(1), "<file>"))
    return found


def _ai_packages(path: Path) -> int:
    return sum(e.get("type") == "ai_AIPackage" for e in load_graph(path))


@check("17", "model outcome parity: project, wheel, loom model list alike")
def check_model_outcome_parity(ctx: Context) -> None:
    """A truncated Safetensors file (a model whose read fails) and Git LFS
    pointers named ``.gguf``, ``.onnx`` and ``.bin`` (not models) in one
    project. ``project`` and ``wheel`` list the truncated file (an
    ``ai_AIPackage`` besides the good model's) and not the pointer; each warns
    once per file, with the same text. ``loom model`` writes the truncated
    file's SBOM with that same warning and exit 0, and refuses a pointer with
    one ``ERROR:`` and exit 1, nothing written."""
    project = write_project(ctx.work / "proj")
    models = project / "demo"
    header = b'{"a": 1}'
    truncated = struct.pack("<Q", 200) + header  # declares 200 bytes, has 8
    (models / _TRUNCATED).write_bytes(truncated)
    for pointer in _POINTERS:
        (models / pointer).write_bytes(_POINTER)
    wheel = build_wheel(project, ctx.work / "dist")

    outputs = {"project": ctx.work / "p.json", "wheel": ctx.work / "w.json"}
    warnings = {
        "project": run_ok(
            "project", str(project), "-o", str(outputs["project"]), *_COMMON
        ),
        "wheel": run_ok("wheel", str(wheel), "-o", str(outputs["wheel"]), *_COMMON),
    }
    expected = _warnings_by_file(warnings["project"].stderr_lines)
    for surface, result in warnings.items():
        by_file = _warnings_by_file(result.stderr_lines)
        expect(
            sorted(by_file) == sorted([*_POINTERS, _TRUNCATED])
            and all(len(v) == 1 for v in by_file.values()),
            f"{surface}: want one WARNING per file, got {by_file}",
        )
        expect(by_file == expected, f"{surface}: warnings differ from project's")
        # The good model and the truncated one: not the pointer.
        expect(
            _ai_packages(outputs[surface]) == 2,
            f"{surface}: {_ai_packages(outputs[surface])} ai_AIPackage, want 2",
        )
    for pointer in _POINTERS:
        expect(
            "header is a Git LFS pointer" in expected[pointer][0],
            f"pointer: {expected[pointer]}",
        )

    single = ctx.work / "m.json"
    ok = run_ok("model", str(models / _TRUNCATED), "-o", str(single), *_COMMON)
    by_file = _warnings_by_file(ok.stderr_lines)
    expect(
        by_file == {_TRUNCATED: expected[_TRUNCATED]},
        f"loom model: warnings {by_file} differ from the scan's",
    )
    expect(_ai_packages(single) == 1, "loom model: want one ai_AIPackage")

    refused = ctx.work / "lfs.json"
    for pointer in _POINTERS:
        result = run_loom("model", str(models / pointer), "-o", str(refused), *_COMMON)
        errors = [ln for ln in result.stderr_lines if ln.startswith("ERROR:")]
        expect(
            result.returncode == 1, f"loom model {pointer}: exit {result.returncode}"
        )
        expect(len(errors) == 1, f"loom model {pointer}: want one ERROR:, got {errors}")
        expect("Git LFS pointer" in errors[0], f"loom model {pointer}: {errors}")
        expect(not refused.exists(), f"loom model {pointer}: output written")
    ctx.note("project, wheel and loom model: one entry per confirmed model")
