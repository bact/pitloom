# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Checks 20, 21 and 24 of manual-cli-checks.md: a ``loom.run`` script's
dataset ids, read from a registry ``loom id generate`` wrote, are the same
from the project root and from a subdirectory (20); separate training and
evaluation scripts share one model id that loom records itself, a retrain
re-mints it, and a crashing script writes nothing (21); ``id generate -e``
and ``loom.run`` hash or omit a dataset the same way under one cap (24).

See also: ``_checks_core.py`` (check 9, the CLI's registry round trip),
``_harness.py``.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

from _harness import (
    TAGS,
    Context,
    check,
    child_env,
    expect,
    load_graph,
    run_loom,
)

_SCRIPT = """\
import sys
from pitloom import loom

out, registry, single, directory = sys.argv[1:5]
with loom.run(out, id_registry=registry):
    loom.set_model("m")
    loom.add_dataset(single)
    loom.add_input_dataset(directory)
"""


def _write_project(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "data" / "t.txt").write_bytes(b"one line\n")
    (root / "corpus" / "b").mkdir(parents=True)
    (root / "corpus" / "a.txt").write_bytes(b"a\n")
    (root / "corpus" / "b" / "c.txt").write_bytes(b"c\n")
    (root / "sub").mkdir()
    (root / "train.py").write_text(_SCRIPT, encoding="utf-8")


def _python(script: Path, cwd: Path, *args: str) -> tuple[int, str]:
    """Run *script* with *args* from *cwd*: its exit code and stderr."""
    proc = subprocess.run(  # nosec B603
        [sys.executable, str(script), *args],
        env=child_env(),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=300,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def _run_script(root: Path, cwd: Path, out: Path, prefix: str) -> list[dict[str, Any]]:
    """Run the project's loom script from *cwd*, naming the datasets with
    *prefix* (the way back to the project root)."""
    code, stderr = _python(
        root / "train.py",
        cwd,
        str(out),
        str(root / "loom-id-registry.json"),
        f"{prefix}data/t.txt",
        f"{prefix}corpus",
    )
    expect(code == 0, f"loom script exited {code}\n{stderr}")
    expect("Traceback" not in stderr, f"loom script traceback:\n{stderr}")
    return load_graph(out)


def _summary(graph: list[dict[str, Any]]) -> dict[str, Any]:
    """The data file's id, the file dataset's id and its ``contains``
    edges, and the directory dataset's Merkle root."""
    (held,) = [
        e for e in graph if e["type"] == "software_File" and e["name"] != "train.py"
    ]
    packages = {e["name"]: e for e in graph if e["type"] == "dataset_DatasetPackage"}
    single = next(p for name, p in packages.items() if name.endswith("data/t.txt"))
    directory = next(p for name, p in packages.items() if name.endswith("corpus"))
    contains = [
        (r["from"], r["to"]) for r in graph if r.get("relationshipType") == "contains"
    ]
    (root_hash,) = directory["verifiedUsing"]
    return {
        "file": (held["name"], held["spdxId"]),
        "single": single["spdxId"],
        "contains": contains,
        "root": root_hash["hashValue"],
        "comment": root_hash.get("comment", ""),
    }


@check("20", "loom.run datasets: registry ids kept from a subdirectory, Merkle root")
def check_loom_dataset_ids(ctx: Context) -> None:
    root = ctx.work / "proj"
    _write_project(root)
    registry = root / "loom-id-registry.json"
    generated = run_loom(
        "id",
        "generate",
        str(root / "data" / "t.txt"),
        "--project-dir",
        str(root),
        "-o",
        str(registry),
        "-e",
        "data/t.txt:dataset_DatasetPackage",
    )
    expect(generated.returncode == 0, generated.describe())
    before = registry.read_bytes()

    first = _summary(_run_script(root, root, ctx.work / "a.json", ""))
    second = _summary(_run_script(root, root, ctx.work / "b.json", ""))
    expect(first == second, f"two runs from the root differ:\n{first}\n{second}")
    expect(first["file"][0] == "data/t.txt", f"file not keyed from the root: {first}")
    expect("#File-" in first["file"][1], f"file id not from the registry: {first}")
    expect(
        "#DatasetPackage-" in first["single"], f"dataset not from the registry: {first}"
    )
    expect(
        first["contains"] == [(first["single"], [first["file"][1]])],
        f"no contains edge from the dataset to its file: {first}",
    )
    expect("over 2 files" in first["comment"], f"Merkle root comment: {first}")

    nested = _summary(_run_script(root, root / "sub", ctx.work / "c.json", "../"))
    expect(nested["file"] == first["file"], f"file id from sub/ differs: {nested}")
    expect(nested["root"] == first["root"], f"Merkle root from sub/ differs: {nested}")

    (root / "corpus" / "a.txt").rename(root / "corpus" / "z.txt")
    renamed = _summary(_run_script(root, root, ctx.work / "d.json", ""))
    expect(renamed["root"] != first["root"], "renaming a file kept the Merkle root")
    expect(registry.read_bytes() == before, "a loom run wrote the registry")
    ctx.note(f"file {first['file'][1]}, root {first['root'][:12]}...")


_MODEL_SCRIPT = """\
import sys
from pitloom import loom

out, registry, mode = sys.argv[1:4]
with loom.run(out, id_registry=registry):
    if mode == "eval":
        loom.use_model("m", path="model.bin")
        loom.add_validation_dataset("data.txt")
    else:
        loom.set_model("m", path="model.bin")
        loom.add_dataset("data.txt")
    if mode == "crash":
        with open("model.bin", "wb") as f:
            f.write(b"weights, half-trained")
        raise RuntimeError("training failed")
"""


def _model_run(root: Path, out: Path, mode: str) -> tuple[str, list[str]]:
    """Run the model script in *mode* from *root*, ending cleanly: the
    model's id and the stderr lines, every one tagged."""
    code, stderr = _python(
        root / "run.py", root, str(out), str(root / "loom-id-registry.json"), mode
    )
    expect(code == 0, f"loom {mode} script exited {code}\n{stderr}")
    lines = stderr.splitlines()
    expect(all(line.startswith(TAGS) for line in lines), f"untagged:\n{stderr}")
    (model,) = [e for e in load_graph(out) if e["type"] == "ai_AIPackage"]
    return str(model["spdxId"]), lines


@check("21", "loom.run models: train/eval share an id loom records; crash writes none")
def check_loom_model_ids(ctx: Context) -> None:
    root = ctx.work / "models"
    root.mkdir()
    (root / "data.txt").write_bytes(b"rows\n")
    (root / "model.bin").write_bytes(b"weights")
    (root / "run.py").write_text(_MODEL_SCRIPT, encoding="utf-8")
    registry = root / "loom-id-registry.json"
    generated = run_loom(
        "id",
        "generate",
        str(root / "data.txt"),
        str(root / "run.py"),
        "--project-dir",
        str(root),
        "-o",
        str(registry),
        "-e",
        "data.txt:dataset_DatasetPackage",
    )
    expect(generated.returncode == 0, generated.describe())
    expect(b"ai_AIPackage" not in registry.read_bytes(), "id generate pinned a model")

    trained, lines = _model_run(root, ctx.work / "train.json", "train")
    expect(
        len(lines) == 1 and "ID registry: added 1 new id(s)" in lines[0],
        f"training did not record the model alone: {lines}",
    )
    recorded = registry.read_bytes()
    expect(b"ai_AIPackage" in recorded, "the model is not in the registry")

    evaluated, lines = _model_run(root, ctx.work / "eval.json", "eval")
    expect(evaluated == trained, f"eval id {evaluated} is not train id {trained}")
    expect(not lines, f"evaluation logged: {lines}")
    expect(registry.read_bytes() == recorded, "evaluation wrote the registry")

    code, stderr = _python(
        root / "run.py", root, str(ctx.work / "crash.json"), str(registry), "crash"
    )
    expect(code == 1 and "RuntimeError: training failed" in stderr, stderr)
    expect(not (ctx.work / "crash.json").exists(), "a crashed run wrote a fragment")
    expect(registry.read_bytes() == recorded, "a crashed run wrote the registry")

    retrained, lines = _model_run(root, ctx.work / "retrain.json", "train")
    changed = [line for line in lines if "content changed for model.bin;" in line]
    expect(retrained != trained, f"a retrained model kept id {trained}")
    expect(
        len(changed) == 1 and len(lines) == 2 and lines[0].startswith("INFO: "),
        f"retrain: not one content-changed INFO: {lines}",
    )
    ctx.note(f"model {trained} -> {retrained}")


_CAP_SCRIPT = """\
import sys
from pitloom import loom

out, mode, value = sys.argv[1:4]
extra = {"max_dataset_hash_bytes": int(value)} if mode == "keyword" else {
    "pitloom_config": value
}
with loom.run(out, **extra):
    loom.add_dataset("data/small.txt")
    loom.add_dataset("data/big.txt")
"""
#: Bytes of ``data/small.txt`` (at the cap) and ``data/big.txt`` (over it).
_CAP = 16


def _pinned_digests(registry: Path) -> dict[str, str | None]:
    """Dataset name -> SHA-256 (or none) in the registry at *registry*."""
    entries = json.loads(registry.read_bytes())["elements"]["dataset_DatasetPackage"]
    return {name: entry.get("sha256") for name, entry in entries.items()}


def _packaged_digests(graph: list[dict[str, Any]]) -> dict[str, str | None]:
    """Dataset name -> SHA-256 (or none) in a loom fragment's graph."""
    found: dict[str, str | None] = {}
    for element in graph:
        if element["type"] != "dataset_DatasetPackage":
            continue
        hashes = {
            h["algorithm"]: h["hashValue"] for h in element.get("verifiedUsing", [])
        }
        found[element["name"]] = hashes.get("sha256")
    return found


def _id_generate_with_cap(root: Path, registry: Path, *flags: str) -> None:
    """Pin both datasets with ``id generate -e``: one INFO names the cap."""
    result = run_loom(
        "id",
        "generate",
        "--project-dir",
        str(root),
        "-o",
        str(registry),
        "-e",
        "data/small.txt:dataset_DatasetPackage",
        "-e",
        "data/big.txt:dataset_DatasetPackage",
        *flags,
        cwd=root,
    )
    expect(result.returncode == 0, result.describe())
    capped = [ln for ln in result.stderr_lines if "max-dataset-hash-bytes" in ln]
    expect(
        len(capped) == 1 and capped[0].startswith("INFO: ID registry: dataset "),
        f"id generate: not one INFO naming the cap: {result.stderr_lines}",
    )


@check("24", "dataset hash cap: id generate -e and loom.run hash or omit alike")
def check_dataset_hash_cap(ctx: Context) -> None:
    root = ctx.work / "capped"
    (root / "data").mkdir(parents=True)
    (root / "data" / "small.txt").write_bytes(b"s" * _CAP)
    (root / "data" / "big.txt").write_bytes(b"b" * (_CAP + 4))
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "p"\nversion = "1"\n\n[tool.pitloom]\n'
        f"max-dataset-hash-bytes = {_CAP}\n",
        encoding="utf-8",
    )
    config = root / "cap.toml"
    config.write_text(
        f"[tool.pitloom]\nmax-dataset-hash-bytes = {_CAP}\n", encoding="utf-8"
    )
    flagged = ctx.work / "flag.json"
    keyed = ctx.work / "key.json"
    # The flag, then the project's own key; the 4 GiB default hashes both.
    _id_generate_with_cap(root, flagged, "--max-dataset-hash-bytes", str(_CAP))
    _id_generate_with_cap(root, keyed)
    pinned = _pinned_digests(flagged)
    expect(pinned == _pinned_digests(keyed), "the project key and the flag differ")
    expect(
        pinned["data/small.txt"] is not None and pinned["data/big.txt"] is None,
        f"id generate -e did not hash only the dataset within the cap: {pinned}",
    )

    script = ctx.work / "cap.py"
    script.write_text(_CAP_SCRIPT, encoding="utf-8")
    for mode, value in (("keyword", str(_CAP)), ("config", str(config))):
        out = ctx.work / f"{mode}.json"
        code, stderr = _python(script, root, str(out), mode, value)
        expect(code == 0 and "Traceback" not in stderr, f"loom {mode}:\n{stderr}")
        warned = [ln for ln in stderr.splitlines() if "max-dataset-hash-bytes" in ln]
        expect(
            len(warned) == 1 and warned[0].startswith("WARNING: "),
            f"loom {mode}: not one WARNING naming the cap:\n{stderr}",
        )
        packaged = _packaged_digests(load_graph(out))
        expect(packaged == pinned, f"loom {mode} {packaged} differs from {pinned}")
    ctx.note(f"cap {_CAP}: small hashed, big omitted, on both")
