# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Checks 12-13 of manual-cli-checks.md: a target that is not a project
reads no config it was not given; an sdist reads its own, as its unpacked
directory does.

See also: ``_checks_core.py`` (checks 1-11), ``_harness.py``.
"""

from __future__ import annotations

import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path

from _fixtures import build_wheel, get, write_project
from _harness import (
    DATETIME,
    Context,
    check,
    embedded_sboms,
    expect,
    load_graph,
    run_loom,
    run_ok,
)

_DECOY_COMMENT = "decoy config comment"
_DECOY_CONFIG = f"""\
[project]
name = "decoy"
version = "0.0.0"

[tool.pitloom]
pretty = true
enrich = true
update-id-registry = true
id-registry = "loom-id-registry.json"
creation-comment = "{_DECOY_COMMENT}"
"""
_REGISTRY = "loom-id-registry.json"
_PINNED = ("--creation-datetime", DATETIME)

# Command -> argv for a target; each writes its SBOM to the given file.
_Argv = Callable[[Path, Path, Path], list[str]]
_COMMANDS: dict[str, _Argv] = {
    "wheel": lambda w, _m, o: ["wheel", str(w), "--offline", "-o", str(o)],
    "generate-wheel": lambda w, _m, o: ["generate", str(w), "--offline", "-o", str(o)],
    "env": lambda _w, _m, o: ["env", "--offline", "-o", str(o)],
    "model": lambda _w, m, o: ["model", str(m), "--offline", "-o", str(o)],
    "enrich": lambda _w, m, o: ["enrich", str(m), "-o", str(o)],
}


def _decoy(cwd: Path, registry_source: Path) -> None:
    """Make *cwd* a project Pitloom must not read: a ``[tool.pitloom]``
    changing several outputs, and a registry it would write back to."""
    cwd.mkdir(parents=True, exist_ok=True)
    (cwd / "pyproject.toml").write_text(_DECOY_CONFIG, encoding="utf-8")
    shutil.copy2(registry_source, cwd / _REGISTRY)


def _expect_registry_untouched(cwd: Path, seeded: bytes, name: str) -> None:
    expect(
        (cwd / _REGISTRY).read_bytes() == seeded,
        f"{name}: the registry in cwd was written to",
    )


def _sbom(argv: list[str], cwd: Path, out: Path) -> bytes:
    result = run_loom(*argv, *_PINNED, cwd=cwd)
    expect(result.returncode == 0, result.describe())
    return out.read_bytes()


def _embedded(wheel: Path, work: Path, cwd: Path, *extra: str) -> bytes:
    """Embed into a private copy of *wheel* (same file name) from *cwd*."""
    work.mkdir(parents=True)
    copy = work / wheel.name
    shutil.copy2(wheel, copy)
    result = run_loom("embed-wheel", str(copy), "--offline", *_PINNED, *extra, cwd=cwd)
    expect(result.returncode == 0, result.describe())
    sboms = embedded_sboms(copy)
    expect(len(sboms) == 1, f"{copy}: embedded SBOMs {sorted(sboms)}")
    return next(iter(sboms.values()))


@check("12", "no implicit config: wheel/env/model/enrich/embed ignore cwd")
def check_no_implicit_config(ctx: Context) -> None:
    """Each non-project target is run from an empty directory and from a
    decoy project directory (whose model directory also holds the decoy):
    the SBOMs are byte-identical and the decoy registry is untouched. The
    decoy named by ``--config`` does change the SBOM, so the decoy is
    effective and the comparison is not vacuous."""
    project = write_project(ctx.work / "proj")
    wheel = build_wheel(project, ctx.work / "dist")
    registry = ctx.work / "seed-ids.json"
    run_ok(
        "id",
        "generate",
        str(project),
        "--project-dir",
        str(project),
        "-o",
        str(registry),
    )
    model_dir = ctx.work / "models"
    model_dir.mkdir()
    model = model_dir / "tiny.safetensors"
    shutil.copy2(get().get("model"), model)

    empty, decoy = ctx.work / "empty", ctx.work / "decoy"
    empty.mkdir()
    _decoy(decoy, registry)
    seeded = (decoy / _REGISTRY).read_bytes()
    config = str(decoy / "pyproject.toml")

    for name, argv in _COMMANDS.items():
        out = ctx.work / "out" / name
        out.mkdir(parents=True)
        clean = _sbom(argv(wheel, model, out / "a.json"), empty, out / "a.json")
        (model_dir / "pyproject.toml").write_text(_DECOY_CONFIG, encoding="utf-8")
        try:
            dirty = _sbom(argv(wheel, model, out / "b.json"), decoy, out / "b.json")
        finally:
            (model_dir / "pyproject.toml").unlink()
        expect(clean == dirty, f"{name}: a config in cwd changed the SBOM")
        _expect_registry_untouched(decoy, seeded, name)
        named = _sbom(
            [*argv(wheel, model, out / "c.json"), "--config", config],
            empty,
            out / "c.json",
        )
        expect(_DECOY_COMMENT.encode() in named, f"{name}: --config not applied")
        # The named config's id-registry may be written back: reseed it.
        (decoy / _REGISTRY).write_bytes(seeded)

    clean = _embedded(wheel, ctx.work / "embed" / "a", empty)
    dirty = _embedded(wheel, ctx.work / "embed" / "b", decoy)
    expect(clean == dirty, "embed-wheel: a config in cwd changed the SBOM")
    _expect_registry_untouched(decoy, seeded, "embed-wheel")
    named = _embedded(wheel, ctx.work / "embed" / "c", empty, "--config", config)
    expect(_DECOY_COMMENT.encode() in named, "embed-wheel: --config not applied")
    ctx.note(f"{len(_COMMANDS) + 1} surfaces ignore cwd and honour --config")


_OWN_COMMENT = "sdist own config comment"
_OWN_CONFIG = f"""
[tool.pitloom]
pretty = true

[tool.pitloom.creation]
creation-comment = "{_OWN_COMMENT}"
"""


def _creation_comments(sbom: bytes) -> list[str]:
    return sorted(
        str(o["comment"])
        for o in load_graph(sbom)
        if o.get("type") == "CreationInfo" and "comment" in o
    )


def _sdist_of(project: Path, out: Path) -> Path:
    """``out/demo-0.1.tar.gz`` holding *project* under ``demo-0.1/``."""
    out.mkdir(parents=True)
    sdist = out / "demo-0.1.tar.gz"
    with tarfile.open(sdist, "w:gz") as tf:
        tf.add(project, arcname="demo-0.1")
    return sdist


@check("13", "sdist reads its own config as its directory; --config rescues")
def check_sdist_own_config(ctx: Context) -> None:
    """The same ``[tool.pitloom]`` gives the same config-driven output
    (pretty, creation comment) for a directory and its ``.tar.gz``, and
    ``-v`` labels it with the archive member. An invalid one is one
    ``ERROR:`` naming the member; ``--config`` replaces it without
    parsing it, so the run then succeeds."""
    project = write_project(ctx.work / "proj")
    with (project / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write(_OWN_CONFIG)
    sdist = _sdist_of(project, ctx.work / "dist")
    outs = {name: ctx.work / f"{name}.json" for name in ("dir", "sdist")}
    for name, target in (("dir", project), ("sdist", sdist)):
        run_ok("project", str(target), *_PINNED, "--offline", "-o", str(outs[name]))
    sboms = {name: path.read_bytes() for name, path in outs.items()}
    for name, sbom in sboms.items():
        expect(sbom.startswith(b"{\n  "), f"{name}: own pretty = true not applied")
        expect(
            _creation_comments(sbom) == [_OWN_COMMENT],
            f"{name}: own creation comment not applied",
        )
    verbose = run_ok("project", str(sdist), "-v", "--offline", "-o", str(outs["sdist"]))
    expect(
        f"{sdist.name}:pyproject.toml" in verbose.stdout,
        f"-v does not label the sdist member:\n{verbose.describe()}",
    )

    broken = write_project(ctx.work / "broken")
    with (broken / "pyproject.toml").open("a", encoding="utf-8") as f:
        f.write("\n[tool.pitloom]\npretty = 'yes'\n")
    bad = _sdist_of(broken, ctx.work / "bad-dist")
    out = ctx.work / "bad.json"
    failed = run_loom("project", str(bad), "--offline", "-o", str(out))
    errors = [line for line in failed.stderr.splitlines() if line.startswith("ERROR:")]
    expect(
        failed.returncode != 0
        and len(errors) == 1
        and f"{bad.name}:pyproject.toml" in errors[0],
        f"invalid sdist config: expected one ERROR: naming the member\n"
        f"{failed.describe()}",
    )
    good = ctx.work / "good.toml"
    good.write_text("[tool.pitloom]\npretty = true\n", encoding="utf-8")
    run_ok("project", str(bad), "--config", str(good), "--offline", "-o", str(out))
    ctx.note("sdist == directory for its own config; --config rescues a broken one")
