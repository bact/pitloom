# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A setuptools project's declared licence on every surface: the directory
(``loom project`` and the library), where ``setup.py`` and ``setup.cfg`` are
both read, and the sdist and wheel setuptools built from it, where only the
PKG-INFO/METADATA setuptools wrote is read. The directory records a real
``setup.py``/``setup.cfg`` disagreement as a conflict Annotation; the built
artefacts carry the one value setuptools chose and no conflict.

See also: tests/extract/project/test_setuptools_merge_license.py (the merge
itself) and test_license_sdist_parity.py (the same check for ``pyproject``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from tests._license_graph import license_value
from tests.assemble.embed_surfaces_shared import run_cli

pytest.importorskip("build", reason="PyPA build is required to build the artefacts")
pytest.importorskip("setuptools", reason="setuptools is required to build")

#: id -> (setup.cfg licence, setup.py licence).
_VARIANTS = {
    "real-real": ("Apache-2.0", "MIT"),
    "weak-cfg": ("UNKNOWN", "MIT"),
    "weak-py": ("MIT", "UNKNOWN"),
}
#: The built artefacts: setuptools wrote ``License: UNKNOWN`` for "weak-py"
#: (setup.py's placeholder wins over setup.cfg's MIT), read as NOASSERTION.
_NO_ASSERTION = "expandedlicensing_NoAssertionLicense"
_BUILT_DECLARED = {
    "real-real": ["MIT"],
    "weak-cfg": ["MIT"],
    "weak-py": [_NO_ASSERTION],
}
_DIR_DECLARED = {"real-real": ["MIT"], "weak-cfg": ["MIT"], "weak-py": ["MIT"]}
_DIR_SURFACES = ("dir-cli", "dir-lib")
_BUILT_SURFACES = ("sdist", "wheel")


def _write_project(root: Path, cfg_licence: str, py_licence: str) -> Path:
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (root / "setup.cfg").write_text(
        f"[metadata]\nname = demo\nversion = 1.0\nlicense = {cfg_licence}\n",
        encoding="utf-8",
    )
    (root / "setup.py").write_text(
        "from setuptools import setup\n"
        f"setup(name='demo', version='1.0', license='{py_licence}')\n",
        encoding="utf-8",
    )
    return root


def _build(project: Path, out: Path, kind: str) -> Path:
    """Build *project*'s *kind* (``sdist``/``wheel``) from a copy: building
    writes ``*.egg-info`` into the directory it builds."""
    copy = out / f"copy-{kind}"
    shutil.copytree(project, copy)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    argv = [sys.executable, "-m", "build", f"--{kind}", "--no-isolation"]
    argv += ["--skip-dependency-check", "--outdir", str(out), str(copy)]
    proc = subprocess.run(  # nosec B603
        argv,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=180,
        check=False,
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"{kind} build failed:\n{stderr[-1500:]}"
    (artefact,) = out.glob("*.tar.gz" if kind == "sdist" else "*.whl")
    return artefact


@pytest.fixture(scope="module", name="built_projects")
def _built_projects(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, dict[str, Path]]:
    """Per variant: the project directory, its sdist and its wheel."""
    built: dict[str, dict[str, Path]] = {}
    for name, (cfg, py) in _VARIANTS.items():
        root = tmp_path_factory.mktemp(name)
        project = _write_project(root / "proj", cfg, py)
        out = root / "dist"
        out.mkdir()
        built[name] = {
            "dir": project,
            "sdist": _build(project, out, "sdist"),
            "wheel": _build(project, out, "wheel"),
        }
    return built


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _cli(argv: list[str], out: Path, mp: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    run_cli([*argv, "--offline", "-o", str(out)], mp)
    return _graph(out.read_text(encoding="utf-8"))


def _run(
    surface: str, paths: dict[str, Path], tmp: Path, mp: pytest.MonkeyPatch
) -> list[dict[str, Any]]:
    out = tmp / "out.spdx3.json"
    runners: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "dir-cli": lambda: _cli(["project", str(paths["dir"])], out, mp),
        "dir-lib": lambda: _graph(generate_project_sbom(paths["dir"], offline=True)),
        "sdist": lambda: _cli(["generate", str(paths["sdist"])], out, mp),
        "wheel": lambda: _cli(["wheel", str(paths["wheel"])], out, mp),
    }
    return runners[surface]()


def _declared(graph: list[dict[str, Any]]) -> list[str]:
    """Values ``demo``'s declared-licence relationships point at."""
    (package,) = [
        e["spdxId"]
        for e in graph
        if e["type"] == "software_Package" and e["name"] == "demo"
    ]
    values = {e["spdxId"]: license_value(e) for e in graph if "spdxId" in e}
    return sorted(
        str(values.get(target, target))
        for rel in graph
        if rel.get("relationshipType") == "hasDeclaredLicense"
        and rel["from"] == package
        for target in rel["to"]
    )


def _setuptools_conflicts(graph: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Licence conflict statements naming ``setup.py``/``setup.cfg``."""
    found = []
    for element in graph:
        if element.get("type") != "Annotation":
            continue
        statement = json.loads(element["statement"])
        sources = [c["source"] for c in statement.get("candidates", [])]
        is_conflict = statement.get("kind") == "conflict"
        if is_conflict and any("setup.py" in s for s in sources):
            found.append(statement)
    return found


@pytest.mark.parametrize("surface", _DIR_SURFACES + _BUILT_SURFACES)
@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_one_declared_licence_on_every_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    built_projects: dict[str, dict[str, Path]],
    variant: str,
    surface: str,
) -> None:
    monkeypatch.chdir(tmp_path)  # no [tool.pitloom] to borrow
    graph = _run(surface, built_projects[variant], tmp_path, monkeypatch)

    table = _DIR_DECLARED if surface in _DIR_SURFACES else _BUILT_DECLARED
    assert _declared(graph) == table[variant]
    conflicts = _setuptools_conflicts(graph)
    if variant == "real-real" and surface in _DIR_SURFACES:
        assert len(conflicts) == 1
        statement = conflicts[0]
        assert statement["field"] == "license"
        sources = {c["source"]: c["value"] for c in statement["candidates"]}
        assert sources == {
            "Source: setup.py | Field: setup(license=...)": "MIT",
            "Source: setup.cfg | Field: metadata.license": "Apache-2.0",
        }
    else:
        assert not conflicts
