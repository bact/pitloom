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
import zipfile
from pathlib import Path

from _fixtures import build_wheel, write_project
from _harness import (
    DATETIME,
    REPO_ROOT,
    Context,
    check,
    expect,
    expect_tagged,
    load_graph,
    run_loom,
    run_ok,
)

_TRUNCATED = "trunc.safetensors"
_LFS = "lfs.gguf"
_LFS_ONNX = "lfs.onnx"  # a suffix that admits any header, but not a pointer
_LFS_BIN = "lfs.bin"  # names no format: a warning with no FORMAT=
_LFS_MODEL = "x.model"  # a suffix shared with SentencePiece: magic required
_POINTERS = (_LFS, _LFS_BIN, _LFS_ONNX, _LFS_MODEL)
_CRF_TRUNCATED = "trunc.crfsuite"
_FILE = re.compile(r"FILE=(\S+): ")
_POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n"
_CRFSUITE = (
    REPO_ROOT / "tests" / "fixtures" / "aimodels" / "crfsuite" / "complete.crfsuite"
)
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
    """A truncated Safetensors file and a truncated CRFsuite file (models
    whose read fails) and Git LFS pointers named ``.gguf``, ``.onnx``, ``.bin``
    and ``.model`` (not models) in one project. ``project`` and ``wheel`` list
    each truncated file (an ``ai_AIPackage`` besides the good model's) and no
    pointer; each warns once per file, with the same text. ``loom model``
    writes a truncated file's SBOM with that same warning and exit 0, and
    refuses a pointer with one ``ERROR:`` and exit 1, nothing written."""
    project = write_project(ctx.work / "proj")
    models = project / "demo"
    header = b'{"a": 1}'
    truncated = struct.pack("<Q", 200) + header  # declares 200 bytes, has 8
    (models / _TRUNCATED).write_bytes(truncated)
    crf = _CRFSUITE.read_bytes()
    (models / _CRF_TRUNCATED).write_bytes(crf[:-5])  # header size past the end
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
            sorted(by_file) == sorted([*_POINTERS, _TRUNCATED, _CRF_TRUNCATED])
            and all(len(v) == 1 for v in by_file.values()),
            f"{surface}: want one WARNING per file, got {by_file}",
        )
        expect(by_file == expected, f"{surface}: warnings differ from project's")
        # The good model and the two truncated ones: not the pointers.
        expect(
            _ai_packages(outputs[surface]) == 3,
            f"{surface}: {_ai_packages(outputs[surface])} ai_AIPackage, want 3",
        )
    for pointer in _POINTERS:
        expect(
            "header is a Git LFS pointer" in expected[pointer][0],
            f"pointer: {expected[pointer]}",
        )

    single = ctx.work / "m.json"
    for truncated_name in (_TRUNCATED, _CRF_TRUNCATED):
        ok = run_ok("model", str(models / truncated_name), "-o", str(single), *_COMMON)
        by_file = _warnings_by_file(ok.stderr_lines)
        expect(
            by_file == {truncated_name: expected[truncated_name]},
            f"loom model {truncated_name}: warnings {by_file} differ from the scan's",
        )
        expect(
            _ai_packages(single) == 1,
            f"loom model {truncated_name}: want one ai_AIPackage",
        )

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


def _gguf(*pairs: tuple[str, str]) -> bytes:
    """A GGUF v3 file of string key/value pairs and no tensors."""
    body = b"".join(
        struct.pack("<Q", len(key.encode()))
        + key.encode()
        + struct.pack("<I", 8)
        + struct.pack("<Q", len(value.encode()))
        + value.encode()
        for key, value in pairs
    )
    return b"GGUF" + struct.pack("<IQQ", 3, 0, len(pairs)) + body


def _package_ids(path: Path) -> dict[str, str]:
    return {
        e["name"]: e["spdxId"] for e in load_graph(path) if e["type"] == "ai_AIPackage"
    }


def _hostile_project(root: Path) -> Path:
    """The demo project with the models of :func:`check_hostile_model_text`."""
    project = write_project(root)
    models = project / "demo"
    (models / "bidi.gguf").write_bytes(_gguf(("general.name", "evil\u202etxt.exe")))
    for tail in ("a", "b"):
        name = "n" * 1100 + tail
        (models / f"long{tail}.gguf").write_bytes(_gguf(("general.name", name)))
    with zipfile.ZipFile(models / "s.keras", "w") as zf:
        zf.writestr("metadata.json", '{"keras_version": "3.0.0"}')
        zf.writestr("config.json", '{"config": {"name": "k\\ud800"}}')
    return project


@check("19", "hostile model text: escaped, cut apart, ids kept across id import")
def check_hostile_model_text(ctx: Context) -> None:
    """A project with a model named with U+202E, two models whose names
    share their first 1100 characters, and a Keras file whose config holds
    a lone surrogate. ``project`` exits 0 with tagged stderr; the bidi name
    is escaped, the long names cut to two different names; after ``id
    import`` and a version bump (a new document), every model keeps its id."""
    project = _hostile_project(ctx.work / "proj")
    first, registry = ctx.work / "first.json", ctx.work / "registry.json"
    result = run_ok("project", str(project), "-o", str(first), *_COMMON)
    expect_tagged(result)
    ids = _package_ids(first)
    expect("evil\\u202etxt.exe" in ids, f"bidi name not escaped: {sorted(ids)}")
    expect("k\\ud800" in ids, f"lone surrogate not written as text: {sorted(ids)}")
    long_names = [name for name in ids if name.startswith("nnn")]
    expect(
        len(long_names) == 2 and {len(n) for n in long_names} == {1024},
        f"long names: {[len(n) for n in long_names]}",
    )
    run_ok("id", "import", str(first), "-o", str(registry))
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(text.replace('version = "0.1"', 'version = "0.2"'))
    second = ctx.work / "second.json"
    run_ok(
        "project",
        str(project),
        "-o",
        str(second),
        "--id-registry",
        str(registry),
        *_COMMON,
    )
    documents = [
        [e["spdxId"] for e in load_graph(path) if e["type"] == "SpdxDocument"]
        for path in (first, second)
    ]
    expect(documents[0] != documents[1], "the version bump kept the document")
    expect(_package_ids(second) == ids, "ids changed across id import")
    ctx.note("bidi, long and surrogate names: escaped, apart, ids kept")
