# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check 16 of manual-cli-checks.md: a wheel Pitloom refuses is refused the
same way by every command that reads one.

See also: ``_checks_config.py``, ``_checks_core.py`` and ``_checks_build.py``
(the other checks), ``_harness.py``.
"""

from __future__ import annotations

import shutil
import warnings
import zipfile
from pathlib import Path

from _fixtures import build_wheel, write_project
from _harness import Context, check, embedded_sboms, expect, run_loom, run_ok

_BAD = "bad-1.0-py3-none-any.whl"
_REFUSED = " -- wheel refused"


def _duplicate_member_wheel(path: Path) -> Path:
    """A wheel holding one install location twice, the second naming another
    package: whichever reader takes it, the answer would differ."""
    with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as zf:
        warnings.simplefilter("ignore")  # zipfile's own duplicate-name warning
        zf.writestr("bad-1.0.dist-info/METADATA", "Name: bad\nVersion: 1.0\n")
        zf.writestr("bad-1.0.dist-info/METADATA", "Name: evil\nVersion: 9.9\n")
    return path


@check("16", "refused wheel: one ERROR, exit 1, nothing written, every command")
def check_refused_wheel_parity(ctx: Context) -> None:
    """A wheel with a duplicate member is refused by ``wheel``,
    ``generate``, ``wheel --embed -o``, ``embed-wheel`` (in a batch with a
    good wheel, which is still embedded), ``verify-wheel`` and
    ``validate-wheel``: exit 1, exactly one ``ERROR:`` line ending
    ``-- wheel refused``, the wheel unchanged, no ``-o`` file, and an
    ``--id-registry`` file (where the command takes one) unchanged."""
    project = write_project(ctx.work / "proj")
    good = build_wheel(project, ctx.work / "dist")
    registry = ctx.work / "ids.json"
    run_ok(
        "id",
        "generate",
        str(project),
        "--project-dir",
        str(project),
        "-o",
        str(registry),
    )
    seeded = registry.read_bytes()
    bad_dir = ctx.work / "bad"
    bad_dir.mkdir()
    bad = _duplicate_member_wheel(bad_dir / _BAD)
    before = bad.read_bytes()
    out = ctx.work / "out.json"
    ids = ["--id-registry", str(registry)]

    def batch_copy() -> Path:
        copy = ctx.work / "batch" / good.name
        copy.parent.mkdir(exist_ok=True)
        shutil.copy2(good, copy)
        return copy

    commands: dict[str, list[str]] = {
        "wheel": ["wheel", str(bad), "--offline", "-o", str(out), *ids],
        "generate": ["generate", str(bad), "--offline", "-o", str(out), *ids],
        "wheel-embed": [
            "wheel",
            str(bad),
            "--embed",
            "--offline",
            "-o",
            str(out),
            *ids,
        ],
        "embed-wheel": ["embed-wheel", str(bad), str(batch_copy()), "--offline", *ids],
        "verify-wheel": ["verify-wheel", str(bad)],
        "validate-wheel": ["validate-wheel", str(bad)],
    }
    for name, argv in commands.items():
        result = run_loom(*argv)
        errors = [ln for ln in result.stderr_lines if ln.startswith("ERROR:")]
        expect(result.returncode == 1, f"{name}: exit {result.returncode}, want 1")
        expect(len(errors) == 1, f"{name}: want one ERROR: line, got {errors}")
        expect(
            errors[0].endswith(_REFUSED) and repr(_BAD) in errors[0],
            f"{name}: {errors[0]!r} does not refuse {_BAD}",
        )
        expect(bad.read_bytes() == before, f"{name}: the refused wheel was changed")
        expect(not out.exists(), f"{name}: output written despite refusal")
        expect(registry.read_bytes() == seeded, f"{name}: the registry was written")
    embedded = embedded_sboms(ctx.work / "batch" / good.name)
    expect(len(embedded) == 1, "embed-wheel: the good wheel of the batch not embedded")
    ctx.note(f"{len(commands)} commands refuse the one wheel alike")
