# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check 23 of manual-cli-checks.md: Git LFS pointers (a checkout made with
LFS off) are recorded by their ``oid``, reported once, and refused as models.

See also: ``_checks_model.py`` (check 17, pointers named like models),
``_fixtures.py``, ``_harness.py``.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from _fixtures import build_wheel
from _harness import (
    DATETIME,
    REPO_ROOT,
    Context,
    check,
    expect,
    load_graph,
    run_loom,
    run_ok,
)

_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "lfs-pointers"
_POINTERS = {
    "data/humaneval-test.parquet": "humaneval-test.parquet",
    "models/pytorch_model.bin": "bert-tiny-pytorch-model.bin",
    "data/aa-lcr-extracted-text.zip": "aa-lcr-extracted-text.zip",
    "main.js": "static-js-app-main.js",
}
_NORMAL = "README.md"
_LOOKALIKE = "data/looks.parquet"
_MODEL = "models/pytorch_model.bin"
_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1"

[tool.hatch.build.targets.wheel]
include = ["data", "models", "main.js", "README.md"]
"""
_COMMENT = "Git LFS pointer oid; content not read; size {size} bytes"
_OPTIONS = ["--offline", "--creation-datetime", DATETIME]


def _fields(pointer: bytes) -> dict[str, str]:
    """``oid`` (hex) and ``size`` of a pointer's text."""
    lines = [ln.partition(" ") for ln in pointer.decode("ascii").splitlines()]
    values = {key: value for key, _, value in lines}
    return {"oid": values["oid"].removeprefix("sha256:"), "size": values["size"]}


def _write_project(root: Path) -> dict[str, bytes]:
    """The project of the check; the pointer texts by project-relative path."""
    pointers = {}
    for rel, fixture in _POINTERS.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        pointers[rel] = (_FIXTURES / fixture).read_bytes()
        shutil.copyfile(_FIXTURES / fixture, target)
    (root / _NORMAL).write_text("Demo\n", encoding="utf-8")
    # Opens like a pointer but is 1 KiB or larger, so it is not one.
    pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"ab" * 32
    (root / _LOOKALIKE).write_bytes(pointer + b"\nsize 5\n" + b"x" * 1100)
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return pointers


def _files(path: Path) -> dict[str, dict[str, Any]]:
    """The ``software_File`` elements of an SBOM by name."""
    return {e["name"]: e for e in load_graph(path) if e.get("type") == "software_File"}


def _hashes(element: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {h["algorithm"]: h for h in element.get("verifiedUsing", [])}


def _lfs_warnings(stderr_lines: list[str], text: str) -> list[str]:
    return [ln for ln in stderr_lines if ln.startswith("WARNING:") and text in ln]


@check("23", "Git LFS pointers: oid recorded, one WARNING, refused as a model")
def check_lfs_pointers(ctx: Context) -> None:
    """A project holding real Hub pointers (a dataset ``.parquet``, a model
    ``.bin``, a ``.zip``, a ``.js``), a normal file and a file that opens like
    a pointer but is 1 KiB or larger. ``project`` exits 0 with exactly one
    ``WARNING:`` (``Git LFS pointer, content not read (4 files)``, naming
    ``git lfs pull``), no per-file model warning and no ``ai_AIPackage``; each
    pointer has one SHA-256 (its ``oid``, with the size in a comment) and no
    SHA-512, the other two files keep both and no comment; two runs are
    byte-identical. ``loom model`` of the ``.bin`` pointer exits 1 with one
    ``ERROR:`` (``oid``, ``git lfs pull``) and writes nothing. The built wheel
    warns ``Git LFS pointer shipped`` and records the hashes of the pointer
    texts."""
    project = ctx.work / "proj"
    pointers = _write_project(project)
    out = ctx.work / "a.json"
    result = run_ok(
        "project",
        "--offline",
        "-o",
        str(out),
        "--creation-datetime",
        DATETIME,
        str(project),
    )
    warnings = [ln for ln in result.stderr_lines if ln.startswith("WARNING:")]
    expect(len(warnings) == 1, f"project: want one WARNING:, got {warnings}")
    expect(
        "Git LFS pointer, content not read (4 files)" in warnings[0]
        and "git lfs pull" in warnings[0],
        f"project: unexpected warning {warnings[0]!r}",
    )
    files = _files(out)
    for rel, text in pointers.items():
        fields = _fields(text)
        hashes = _hashes(files[rel])
        expect(
            list(hashes) == ["sha256"]
            and hashes["sha256"]["hashValue"] == fields["oid"],
            f"{rel}: want only the oid as SHA-256, got {hashes}",
        )
        expect(
            hashes["sha256"].get("comment") == _COMMENT.format(size=fields["size"]),
            f"{rel}: comment {hashes['sha256'].get('comment')!r}",
        )
    for rel in (_NORMAL, _LOOKALIKE):
        hashes = _hashes(files[rel])
        expect(
            sorted(hashes) == ["sha256", "sha512"]
            and not any("comment" in h for h in hashes.values()),
            f"{rel}: want SHA-256 and SHA-512, no comment, got {hashes}",
        )
    ai = [e for e in load_graph(out) if e.get("type") == "ai_AIPackage"]
    expect(not ai, f"project: want no ai_AIPackage, got {len(ai)}")

    again = ctx.work / "b.json"
    run_ok("project", *_OPTIONS, "-o", str(again), str(project))
    expect(out.read_bytes() == again.read_bytes(), "project: two runs differ")

    refused = ctx.work / "m.json"
    model = run_loom("model", str(project / _MODEL), "-o", str(refused), *_OPTIONS)
    errors = [ln for ln in model.stderr_lines if ln.startswith("ERROR:")]
    oid = _fields(pointers[_MODEL])["oid"]
    expect(model.returncode == 1, f"loom model: exit {model.returncode}, want 1")
    expect(len(errors) == 1, f"loom model: want one ERROR:, got {errors}")
    expect(
        oid in errors[0] and "git lfs pull" in errors[0],
        f"loom model: {errors[0]!r} lacks the oid or 'git lfs pull'",
    )
    expect(not refused.exists(), "loom model: output written despite refusal")

    wheel = build_wheel(project, ctx.work / "dist")
    built = ctx.work / "w.json"
    run = run_ok("wheel", str(wheel), "-o", str(built), *_OPTIONS)
    shipped = _lfs_warnings(run.stderr_lines, "Git LFS pointer shipped")
    expect(len(shipped) == 1, f"wheel: want one 'shipped' WARNING:, got {shipped}")
    wheel_files = _files(built)
    for rel, text in pointers.items():
        digest = hashlib.sha256(text).hexdigest()
        hashes = _hashes(wheel_files[rel])
        expect(
            hashes["sha256"]["hashValue"] == digest and "sha512" in hashes,
            f"wheel {rel}: want the hashes of the pointer text, got {hashes}",
        )
    ctx.note("4 pointers by oid, 1 WARNING; model refused; wheel hashes the text")
