# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Commands run in order, where an earlier one's side effect (a written
file, an embedded SBOM, an updated registry) is input to a later one.
Each ``S*`` check runs its sequence on private fixture copies.

See also: ``_matrix.py`` (single commands), ``_fixtures.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import _fixtures
from _harness import (
    DATETIME,
    Context,
    Result,
    check,
    embedded_sboms,
    expect,
    run_loom,
)

_DATED = ("--creation-datetime", DATETIME)


def _ok(cell: Path, *args: str) -> Result:
    result = run_loom(*args, cwd=cell)
    expect(result.returncode == 0, result.describe())
    expect("Traceback (most recent call last)" not in result.stderr, result.describe())
    return result


def _sbom_type(raw: bytes) -> list[str]:
    graph = json.loads(raw)["@graph"]
    return sorted(
        t
        for e in graph
        if e.get("type") == "software_Sbom"
        for t in e.get("software_sbomType", [])
    )


@check("S1", "project with its default output twice: the first output is not rescanned")
def seq_default_output(ctx: Context) -> None:
    project = _fixtures.get().stage("project", ctx.work)
    outputs = []
    for _ in range(2):
        result = _ok(project, "project", ".", "--offline", *_DATED)
        line = result.stdout.strip()
        expect(line.startswith("PITLOOM_SBOM_OUTPUT_PATH="), f"stdout: {line!r}")
        path = line.split("=", 1)[1]
        outputs.append((project / path).read_bytes())
    expect(
        outputs[0] == outputs[1], "the second run's SBOM includes the first's output"
    )


@check("S2", "embed-wheel twice on one wheel: one SBOM, same bytes, verifies")
def seq_embed_twice(ctx: Context) -> None:
    fx = _fixtures.get()
    wheel, project = fx.stage("wheel", ctx.work), fx.stage("project", ctx.work)
    seen = []
    for _ in range(2):
        _ok(
            ctx.work,
            "embed-wheel",
            str(wheel),
            "--project-dir",
            str(project),
            "--offline",
            *_DATED,
        )
        sboms = embedded_sboms(wheel)
        expect(len(sboms) == 1, f"embedded SBOMs: {sorted(sboms)}")
        seen.append(sboms)
        _ok(ctx.work, "verify-wheel", str(wheel), "--fail-on-mismatch")
    expect(seen[0] == seen[1], "re-embedding changed the SBOM")


@check("S3", "embed-wheel and wheel --embed in either order: the later one wins")
def seq_embed_orders(ctx: Context) -> None:
    fx = _fixtures.get()
    project = fx.stage("project", ctx.work)
    embed = ("embed-wheel", "--project-dir", str(project))
    orders = {
        "embed-wheel then wheel --embed": (embed, ("wheel", "--embed")),
        "wheel --embed then embed-wheel": (("wheel", "--embed"), embed),
    }
    for label, (first, second) in orders.items():
        cell = ctx.work / label.replace(" ", "_")
        cell.mkdir()
        wheel = fx.stage("wheel", cell)
        types = []
        for step in (first, second):
            _ok(cell, step[0], str(wheel), *step[1:], "--offline", *_DATED)
            sboms = embedded_sboms(wheel)
            expect(len(sboms) == 1, f"{label}: embedded SBOMs {sorted(sboms)}")
            types.append(_sbom_type(next(iter(sboms.values()))))
        _ok(cell, "verify-wheel", str(wheel), "--fail-on-mismatch")
        expect(types[0] != types[1], f"{label}: SBOM type did not change: {types}")
        ctx.note(f"{label}: {types[0]} -> {types[1]}")


@check(
    "S4",
    "registry: generate, then project --id-registry twice; --no-update-id-registry",
)
def seq_registry(ctx: Context) -> None:
    project = _fixtures.get().stage("project", ctx.work)
    registry = ctx.work / "reg.json"
    _ok(
        ctx.work,
        "id",
        "generate",
        str(project),
        "--project-dir",
        str(project),
        "-o",
        str(registry),
    )
    # While the fresh registry still lacks the project's entities, so a
    # plain run (the control below) does change it.
    fresh = registry.read_bytes()
    frozen = ctx.work / "frozen.json"
    frozen.write_bytes(fresh)
    _ok(
        ctx.work,
        *("project", str(project), "--id-registry", str(frozen), "--offline", *_DATED),
        *("-o", "c.json", "--no-update-id-registry"),
    )
    expect(frozen.read_bytes() == fresh, "--no-update-id-registry changed the registry")
    args = (
        "project",
        str(project),
        "--id-registry",
        str(registry),
        "--offline",
        *_DATED,
    )
    outputs, registries = [], []
    for name in ("a.json", "b.json"):
        _ok(ctx.work, *args, "-o", name)
        outputs.append((ctx.work / name).read_bytes())
        registries.append(registry.read_bytes())
    expect(registries[0] != fresh, "a plain run did not update the fresh registry")
    expect(outputs[0] == outputs[1], "same registry, different SBOMs")
    expect(registries[0] == registries[1], "the second run changed the registry again")
    expect((ctx.work / "c.json").read_bytes() == outputs[0], "SBOM differs")


@check("S5", "id import of an SBOM, then project --id-registry reuses its IDs")
def seq_import(ctx: Context) -> None:
    fx = _fixtures.get()
    sbom = fx.get("sbom")
    registry = ctx.work / "reg.json"
    _ok(ctx.work, "id", "import", str(sbom), "-o", str(registry))
    project = fx.stage("project", ctx.work)
    _ok(
        ctx.work,
        "project",
        str(project),
        "--id-registry",
        str(registry),
        "--offline",
        *_DATED,
        "-o",
        "out.json",
    )
    ids_before = {e.get("spdxId") for e in json.loads(sbom.read_bytes())["@graph"]}
    ids_after = {
        e.get("spdxId")
        for e in json.loads((ctx.work / "out.json").read_bytes())["@graph"]
    }
    shared = {i for i in ids_before & ids_after if i}
    expect(bool(shared), "no imported ID reused")
    ctx.note(f"{len(shared)} IDs reused")


@check("S6", "merge -o inside the fragments dir: a rerun merges its own output")
def seq_merge_into_input(ctx: Context) -> None:
    fragments = _fixtures.get().stage("fragments", ctx.work)
    count = len(list(fragments.glob("*.spdx3.json")))
    first = _ok(
        ctx.work, "merge", str(fragments), "-o", str(fragments / "m.spdx3.json")
    )
    second = _ok(
        ctx.work, "merge", str(fragments), "-o", str(fragments / "m.spdx3.json")
    )
    # Documented in manual-cli-checks.md check 7: write the output elsewhere.
    expect(f"merged {count} " in first.stdout, first.stdout)
    expect(f"merged {count + 1} " in second.stdout, second.stdout)
    ctx.note("documented hazard reproduced (write merge output outside the input dir)")


@check("S7", "verify-wheel before and after embedding")
def seq_verify_order(ctx: Context) -> None:
    fx = _fixtures.get()
    wheel = fx.stage("wheel", ctx.work)
    before = run_loom("verify-wheel", str(wheel), "--fail-on-mismatch", cwd=ctx.work)
    expect(before.returncode != 0, "verify-wheel passed a wheel with no SBOM")
    _ok(
        ctx.work,
        "embed-wheel",
        str(wheel),
        "--project-dir",
        str(fx.stage("project", ctx.work)),
        "--offline",
        *_DATED,
    )
    _ok(ctx.work, "verify-wheel", str(wheel), "--fail-on-mismatch")


@check("S8", "embed-wheel on a hook-built wheel (already has an SBOM): one SBOM")
def seq_hook_then_embed(ctx: Context) -> None:
    fx = _fixtures.get()
    wheel = fx.stage("hook-wheel", ctx.work)
    before = embedded_sboms(wheel)
    expect(len(before) == 1, f"hook-built wheel SBOMs: {sorted(before)}")
    _ok(
        ctx.work,
        "embed-wheel",
        str(wheel),
        "--project-dir",
        str(fx.stage("project", ctx.work)),
        "--offline",
        *_DATED,
    )
    after = embedded_sboms(wheel)
    expect(len(after) == 1, f"embedded SBOMs after embed-wheel: {sorted(after)}")
    _ok(ctx.work, "verify-wheel", str(wheel), "--fail-on-mismatch")
    ctx.note(f"hook SBOM {'kept' if after == before else 'replaced'}")
