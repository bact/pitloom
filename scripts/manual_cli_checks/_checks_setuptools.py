# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Check 18 of manual-cli-checks.md: one declared licence for a setuptools
project on the directory, sdist and wheel surfaces.

See also: ``_checks_wheel.py`` and ``_checks_build.py`` (the other checks
that build), ``_fixtures.py``, ``_harness.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _fixtures import build_setuptools
from _harness import Context, check, expect, load_graph, package, run_ok

_DISAGREE = "setup.py and setup.cfg disagree on license"
_NAME = "demo"


def _write_project(root: Path) -> Path:
    """A setuptools project whose ``setup.py`` and ``setup.cfg`` state
    different licences, and no licence file."""
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / "setup.cfg").write_text(
        "[metadata]\nname = demo\nversion = 1.0\nlicense = Apache-2.0\n",
        encoding="utf-8",
    )
    (root / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(name='demo', version='1.0', license='MIT')\n",
        encoding="utf-8",
    )
    return root


def _declared(graph: list[dict[str, Any]]) -> list[str]:
    """The licence values ``demo``'s declared-licence relationships name."""
    pkg_id = package(graph, _NAME)["spdxId"]
    names = {
        e["spdxId"]: e.get("simplelicensing_licenseExpression")
        or e.get("simplelicensing_licenseText")
        or e.get("name")
        for e in graph
        if "spdxId" in e
    }
    return sorted(
        str(names.get(target, target))
        for rel in graph
        if rel.get("relationshipType") == "hasDeclaredLicense" and rel["from"] == pkg_id
        for target in rel["to"]
    )


def _setuptools_conflicts(graph: list[dict[str, Any]]) -> int:
    """How many conflict Annotations name ``setup.py`` as a source."""
    count = 0
    for element in graph:
        if element.get("type") != "Annotation":
            continue
        statement = json.loads(element["statement"])
        sources = [c["source"] for c in statement.get("candidates", [])]
        count += statement.get("kind") == "conflict" and any(
            "setup.py" in s for s in sources
        )
    return count


@check(
    "18",
    "setuptools: setup.py over setup.cfg; dir, sdist, wheel agree; "
    "conflict on dir only",
)
def check_setuptools_licence_surfaces(ctx: Context) -> None:
    """``loom project`` on a directory whose ``setup.py`` says MIT and
    ``setup.cfg`` Apache-2.0 keeps MIT, warns once (``setup.py and
    setup.cfg disagree on license``) and records a conflict Annotation;
    ``loom generate`` on its sdist and ``loom wheel`` on its wheel declare
    the same MIT, with no such warning or Annotation."""
    project = _write_project(ctx.work / "proj")
    dist = ctx.work / "dist"
    sdist = build_setuptools(project, dist, "sdist")
    wheel = build_setuptools(project, dist, "wheel")
    runs = {
        "project": ["project", str(project)],
        "sdist": ["generate", str(sdist)],
        "wheel": ["wheel", str(wheel)],
    }
    for name, argv in runs.items():
        out = ctx.work / f"{name}.spdx3.json"
        result = run_ok(*argv, "--offline", "-o", str(out))
        graph = load_graph(out)
        warned = [ln for ln in result.stderr_lines if _DISAGREE in ln]
        want = 1 if name == "project" else 0
        expect(len(warned) == want, f"{name}: want {want} disagree WARNING: {warned}")
        expect(
            all(ln.startswith("WARNING:") for ln in warned),
            f"{name}: disagreement not tagged WARNING: {warned}",
        )
        expect(_declared(graph) == ["MIT"], f"{name}: declared {_declared(graph)}")
        conflicts = _setuptools_conflicts(graph)
        expect(conflicts == want, f"{name}: {conflicts} setuptools conflicts")
    ctx.note("MIT on directory, sdist and wheel; conflict recorded on the directory")
