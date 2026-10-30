# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The registry's package key holds the version (check ``26``): each
release of a dependency gets its own id through the real ``loom`` entry
point, and going back to a release gets that release's id again.

See also: ``_checks_core.py`` (check ``9``, the registry round trip),
``docs/id-registry-keys.md`` (the package key).
"""

from __future__ import annotations

import json
from pathlib import Path

from _fixtures import write_project
from _harness import DATETIME, Context, check, expect, run_ok

#: The dependency the fixture declares, and the pins this check swaps in.
_DECLARED = '"packaging>=20"'
_PINS = ("24.0", "25.0", "24.0")


def _package_ids(sbom: Path) -> dict[str, str]:
    """Name -> spdxId of each ``software_Package`` of *sbom*."""
    graph = json.loads(sbom.read_bytes())["@graph"]
    return {
        node["name"]: node["spdxId"]
        for node in graph
        if node.get("type") == "software_Package"
    }


@check("26", "registry package key: two versions two ids, back to v1 gets v1's id")
def check_package_version_ids(ctx: Context) -> None:
    project = write_project(ctx.work / "proj")
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    expect(_DECLARED in text, f"fixture no longer declares {_DECLARED}")
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
    ids = []
    for run, pin in enumerate(_PINS):
        pyproject.write_text(
            text.replace(_DECLARED, f'"packaging=={pin}"'), encoding="utf-8"
        )
        out = ctx.work / f"run{run}.json"
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
        ids.append(_package_ids(out))
    keys = sorted(json.loads(registry.read_bytes())["elements"]["software_Package"])
    first, second, back = (found["packaging"] for found in ids)
    expect(first != second, f"packaging 24.0 and 25.0 share one id: {first}")
    expect(back == first, f"back to 24.0 gave {back}, not 24.0's {first}")
    expect(len({found["demo"] for found in ids}) == 1, "the main package id changed")
    expect(
        {"packaging@24", "packaging@25"} <= set(keys),
        f"registry package keys {keys} lack packaging@24 and packaging@25",
    )
    ctx.note(f"packaging 24.0 -> {first}, 25.0 -> {second}; keys {keys}")
