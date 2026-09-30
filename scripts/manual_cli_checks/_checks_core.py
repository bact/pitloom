# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Checks 1-11 and 14 of manual-cli-checks.md that can run unattended
(12-13 are in ``_checks_config.py``).

Check 6 (skills/plugin drift) needs judgement and stays manual.

See also: ``_harness.py``, ``_checks_build.py``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

from _fixtures import build_wheel, get, write_project
from _harness import (
    DATETIME,
    DEBUG_TAGS,
    NETGUARD,
    NETGUARD_MARK,
    REPO_ROOT,
    CheckFailed,
    CheckSkipped,
    Context,
    check,
    child_env,
    embedded_sboms,
    expect,
    expect_tagged,
    file_names,
    load_graph,
    package,
    run_loom,
    run_ok,
    without_creation_info,
)

_HF_MODEL = "mistralai/Mistral-7B-v0.1"


def _build_wheel(ctx: Context, project: Path, out: Path) -> Path:
    wheel = build_wheel(project, out)
    ctx.note(f"built {wheel.name}")
    return wheel


def _embedded_sbom(wheel: Path) -> bytes:
    sboms = embedded_sboms(wheel)
    expect(len(sboms) == 1, f"{wheel.name}: embedded SBOMs {sorted(sboms)}")
    return next(iter(sboms.values()))


@check("1", "determinism: two runs byte-identical, pretty and compact")
def check_determinism(ctx: Context) -> None:
    project = write_project(ctx.work / "proj")
    for style in ("--pretty", "--no-pretty"):
        outputs = []
        for run in ("a", "b"):
            out = ctx.work / f"{run}{style}.json"
            run_ok(
                "project",
                str(project),
                "-o",
                str(out),
                style,
                "--creation-datetime",
                DATETIME,
                "--offline",
            )
            outputs.append(out.read_bytes())
        expect(outputs[0] == outputs[1], f"{style}: outputs differ")


@check("2", "parity: CLI vs library API vs Hatchling hook")
def check_parity(ctx: Context) -> None:
    project = write_project(ctx.work / "proj", hook=True)
    cli = ctx.work / "cli.json"
    run_ok(
        "project",
        str(project),
        "-o",
        str(cli),
        "--creation-datetime",
        DATETIME,
        "--offline",
    )
    api = ctx.work / "api.json"
    code = (
        "import sys\nfrom pathlib import Path\n"
        "from pitloom.assemble import generate_project_sbom\n"
        "from pitloom.core.creation import CreationMetadata\n"
        "generate_project_sbom(Path(sys.argv[1]), output_path=Path(sys.argv[2]),"
        " creation_metadata=CreationMetadata(creation_datetime=sys.argv[3]),"
        " offline=True)\n"
    )
    proc = subprocess.run(  # nosec B603
        [sys.executable, "-c", code, str(project), str(api), DATETIME],
        env=child_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=300,
        check=False,
    )
    expect(proc.returncode == 0, f"library API failed:\n{proc.stderr[-2000:]!r}")
    cli_graph, api_graph = load_graph(cli), load_graph(api)
    expect(
        without_creation_info(cli_graph) == without_creation_info(api_graph),
        "CLI and library API graphs differ (CreationInfo ignored)",
    )
    hook_graph = load_graph(_embedded_sbom(_build_wheel(ctx, project, ctx.work / "w")))
    for key in ("name", "software_packageVersion", "software_packageUrl"):
        cli_value = package(cli_graph, "demo").get(key)
        hook_value = package(hook_graph, "demo").get(key)
        expect(cli_value == hook_value, f"hook {key}: {hook_value!r} != {cli_value!r}")


@check("3", "embed-wheel vs wheel --embed describe the same package")
def check_embed_parity(ctx: Context) -> None:
    project = write_project(ctx.work / "proj")
    wheel = _build_wheel(ctx, project, ctx.work / "w")
    copy = ctx.work / "copy" / wheel.name
    copy.parent.mkdir()
    shutil.copy2(wheel, copy)
    run_ok("embed-wheel", str(wheel), "--project-dir", str(project), "--offline")
    run_ok("wheel", str(copy), "--embed", "--offline")
    embedded, standalone = (
        load_graph(_embedded_sbom(wheel)),
        load_graph(_embedded_sbom(copy)),
    )
    for key in ("name", "software_packageVersion", "software_packageUrl"):
        a, b = package(embedded, "demo").get(key), package(standalone, "demo").get(key)
        expect(a == b, f"{key}: embed-wheel {a!r} != wheel --embed {b!r}")
    expect(
        file_names(embedded) == file_names(standalone),
        f"file lists differ: {file_names(embedded)} vs {file_names(standalone)}",
    )


@check("4a", "round trip: embed-wheel --verify, then verify-wheel")
def check_round_trip(ctx: Context) -> None:
    project = write_project(ctx.work / "proj")
    wheel = _build_wheel(ctx, project, ctx.work / "w")
    run_ok(
        "embed-wheel",
        str(wheel),
        "--project-dir",
        str(project),
        "--verify",
        "--offline",
    )
    run_ok("verify-wheel", str(wheel), "--fail-on-mismatch")


@check("4b", "round trip: embed-wheel --validate, validate-wheel", network=True)
def check_round_trip_validate(ctx: Context) -> None:
    if importlib.util.find_spec("spdx3_validate") is None:
        raise CheckSkipped("needs pitloom[validate]")
    project = write_project(ctx.work / "proj")
    wheel = _build_wheel(ctx, project, ctx.work / "w")
    run_ok(
        "embed-wheel",
        str(wheel),
        "--project-dir",
        str(project),
        "--validate",
        "--offline",
        network=True,
    )
    run_ok("validate-wheel", str(wheel), network=True)


@check("5", "--debug parses on every subcommand; PITLOOM_DEBUG output tagged")
def check_debug(ctx: Context) -> None:
    usage = run_ok("--help").stdout
    match = re.search(r"\{([a-z,-]+)\}", usage)
    if match is None:
        raise CheckFailed("no subcommand list in `loom --help`")
    subcommands = match.group(1).split(",")
    for sub in subcommands:
        run_ok("--debug", sub, "--help")
    # A failing --allow-build build logs its output at DEBUG, so this run
    # is guaranteed to print DEBUG lines (a clean project may print none).
    project = ctx.work / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "failing_backend.py").write_text(
        "def build_wheel(wheel_directory, config_settings=None, "
        "metadata_directory=None):\n"
        "    print('failing backend output')\n    raise SystemExit(1)\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1"\n\n[build-system]\n'
        'requires = []\nbuild-backend = "failing_backend"\nbackend-path = ["."]\n',
        encoding="utf-8",
    )
    result = run_ok(
        "project",
        str(project),
        "-o",
        str(ctx.work / "dbg.json"),
        "--allow-build",
        "--no-build-isolation",
        env=child_env(PITLOOM_DEBUG="1"),
    )
    expect_tagged(result, DEBUG_TAGS)
    debug = [line for line in result.stderr_lines if line.startswith("DEBUG: ")]
    expect(bool(debug), "PITLOOM_DEBUG=1 printed no DEBUG: line")
    ctx.note(f"{len(subcommands)} subcommands, {len(debug)} DEBUG: lines")


@check("7", "fragment merge: deterministic, output validates")
def check_fragment_merge(ctx: Context) -> None:
    fragments = ctx.work / "fragments"
    fragments.mkdir()
    for src in sorted(
        (REPO_ROOT / "tests" / "fixtures" / "fragments").glob("*.spdx3.json")
    ):
        shutil.copy2(src, fragments / src.name)
    # Outputs go outside the fragments dir: merge reads every *.spdx3.json.
    outputs = [ctx.work / "m1.json", ctx.work / "m2.json"]
    for out in outputs:
        run_ok("merge", str(fragments), "-o", str(out))
    expect(outputs[0].read_bytes() == outputs[1].read_bytes(), "merges differ")
    if ctx.network:  # validation fetches the SPDX context from spdx.org
        run_ok("fragment", "validate", str(outputs[0]), network=True)
    else:
        ctx.note("output not validated (needs --network)")


@check("8", "--offline makes zero network attempts (socket guard)")
def check_offline(ctx: Context) -> None:
    out = str(ctx.work / "model.json")
    offline = run_loom(
        "model", _HF_MODEL, "--offline", "-o", out, bootstrap=NETGUARD, timeout=120
    )
    attempts = offline.stderr.count(NETGUARD_MARK)
    expect(attempts == 0, f"--offline made {attempts} network attempts")
    expect(
        offline.returncode != 0 or "Offline" in offline.stderr,
        "--offline neither refused the remote model nor said why",
    )
    # Control: the guard really sees attempts when --offline is absent.
    try:
        online = run_loom("model", _HF_MODEL, "-o", out, bootstrap=NETGUARD, timeout=20)
        seen = online.stderr.count(NETGUARD_MARK)
    except subprocess.TimeoutExpired as exc:  # retries with backoff
        seen = (exc.stderr or b"").decode("utf-8", "replace").count(NETGUARD_MARK)
    expect(seen > 0, "control run without --offline made no network attempt")
    ctx.note(f"control run: {seen} blocked attempts")


@check("9", "registry round trip: IDs stable across repeated runs")
def check_registry(ctx: Context) -> None:
    project = write_project(ctx.work / "proj")
    registry = ctx.work / "registry.json"
    run_ok(
        "id",
        "generate",
        str(project),
        "--project-dir",
        str(project),
        "-o",
        str(registry),
    )
    outputs = []
    for run in ("a", "b"):
        out = ctx.work / f"{run}.json"
        run_ok(
            "project",
            str(project),
            "-o",
            str(out),
            "--id-registry",
            str(registry),
            "--creation-datetime",
            DATETIME,
            "--offline",
        )
        outputs.append(out.read_bytes())
    expect(outputs[0] == outputs[1], "SBOMs with the same registry differ")
    ids = sorted(e["spdxId"] for e in json.loads(outputs[0])["@graph"] if "spdxId" in e)
    expect(bool(ids), "no spdxId values in the SBOM")


@check(
    "10", "--allow-build vs static vs real wheel (compare_allow_build.py)", network=True
)
def check_allow_build_parity(ctx: Context) -> None:
    proc = subprocess.run(  # nosec B603
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "compare_allow_build.py"),
            "--fixture",
            "uv_build/django-model-import-0.9.0",
        ],
        env=child_env(TMPDIR=str(ctx.work)),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=1500,
        check=False,
        cwd=ctx.work,
    )
    output = proc.stdout.decode("utf-8", "replace")
    expect(
        proc.returncode == 0,
        f"compare_allow_build.py exited {proc.returncode}:\n" + output[-2000:],
    )
    ctx.note(output.strip().splitlines()[-1] if output.strip() else "no output")


@check("11", "--content-type-method extension skips the authors-file fetch")
def check_content_type_method_fetch(ctx: Context) -> None:
    """A dependency authored by "and others (see AUTHORS.txt)" has its authors
    file fetched from the repository host, except under ``extension``. The
    socket guard blocks that attempt, so ``auto`` shows one more blocked
    attempt than ``extension`` (the PyPI fallback's are the same in both).
    Run on ``project`` (the reference) and on ``embed-wheel``."""
    dist_info = ctx.work / "site" / "fakedep-1.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: fakedep\nVersion: 1.0\n"
        "Author: and others (see AUTHORS.txt)\n"
        "Project-URL: Repository, https://github.com/example/fakedep\n",
        encoding="utf-8",
    )
    # Prepend: replacing an inherited PYTHONPATH could select another Pitloom.
    env = child_env(
        PYTHONPATH=os.pathsep.join(
            p for p in (str(dist_info.parent), child_env().get("PYTHONPATH", "")) if p
        )
    )
    project = write_project(ctx.work / "proj")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace("packaging>=20", "fakedep==1.0"),
        encoding="utf-8",
    )
    wheel = _build_wheel(ctx, project, ctx.work / "w")

    def blocked(*args: str) -> int:
        result = run_loom(*args, env=env, bootstrap=NETGUARD)
        expect(result.returncode == 0, result.describe())
        return result.network_attempts

    def run_project(method: str) -> int:
        out = ctx.work / f"project-{method}.json"
        return blocked(
            "project", str(project), "-o", str(out), "--content-type-method", method
        )

    def run_embed(method: str) -> int:
        copy = ctx.work / f"embed-{method}" / wheel.name
        copy.parent.mkdir()
        shutil.copy2(wheel, copy)
        return blocked(
            "embed-wheel",
            str(copy),
            "--project-dir",
            str(project),
            "--content-type-method",
            method,
        )

    for surface, run in (("project", run_project), ("embed-wheel", run_embed)):
        auto, extension = run("auto"), run("extension")
        expect(
            auto > extension,
            f"{surface}: auto made {auto} blocked attempts, extension {extension} "
            "(extension must skip the authors-file fetch)",
        )
        ctx.note(f"{surface}: auto {auto} blocked attempts, extension {extension}")


@check(
    "14",
    "declared registry missing/invalid: one ERROR:, exit 1, no output, every surface",
)
def check_registry_missing_invalid(ctx: Context) -> None:
    """A declared ``--id-registry`` that is missing or unparseable is a
    hard failure on every surface that accepts the flag -- never silent
    auto-discovery, never a partial SBOM."""
    project = write_project(ctx.work / "proj")
    wheel = _build_wheel(ctx, project, ctx.work / "dist")
    model = ctx.work / "model.safetensors"
    shutil.copy2(get().get("model"), model)

    invalid = ctx.work / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    missing = ctx.work / "missing.json"  # never created

    commands: dict[str, list[str]] = {
        "project": ["project", str(project), "--offline"],
        "wheel": ["wheel", str(wheel), "--offline"],
        "env": ["env", "--offline"],
        "model": ["model", str(model), "--offline"],
        "embed-wheel": ["embed-wheel", "--project-dir", str(project), "--offline"],
    }
    for name, argv in commands.items():
        for label, registry in (("missing", missing), ("invalid", invalid)):
            case_dir = ctx.work / "cases" / f"{name}-{label}"
            case_dir.mkdir(parents=True)
            out = case_dir / "out.json"
            full_argv = list(argv)
            if name == "embed-wheel":
                copy = case_dir / wheel.name
                shutil.copy2(wheel, copy)
                full_argv.insert(1, str(copy))
            full_argv += ["-o", str(out), "--id-registry", str(registry)]
            result = run_loom(*full_argv, bootstrap=NETGUARD)
            expect(
                result.returncode == 1,
                f"{name}/{label}: exit {result.returncode}, want 1\n"
                f"{result.describe()}",
            )
            error_lines = [ln for ln in result.stderr_lines if ln.startswith("ERROR: ")]
            expect(
                len(error_lines) == 1,
                f"{name}/{label}: want one ERROR: line, got {error_lines}",
            )
            expect(
                bool(error_lines) and "ID registry file" in error_lines[0],
                f"{name}/{label}: {error_lines} does not name 'ID registry file'",
            )
            expect(not out.exists(), f"{name}/{label}: output written despite failure")
    ctx.note(f"{len(commands)} surfaces x missing/invalid registry: one ERROR:, exit 1")
