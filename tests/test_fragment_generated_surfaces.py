# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment's value for what Pitloom generated from a model file's format
(a CRFsuite model's description from its labels; a fastText model's domain and
output description) replaces it, on every route that merges configured
fragments into a project's SBOM (``project``, the library API, the Hatchling
hook, ``embed-wheel --project-dir``): the curated value, one ``INFO:`` per
property, no ``WARNING:``.

See also: tests/assemble/test_fragments_generated.py (the rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import generate_project_sbom
from pitloom.core.provenance import PROVENANCE_PROPERTY_FIELDS
from pitloom.embed import embed_wheel_sbom
from tests._author_routes import hook_sbom, isolate
from tests._license_graph import fragment_graph, write_fragment
from tests._wheel_models import write_model_wheel

_NS = "https://example.org/gv"
_REGISTRY = "ids.json"
_AIMODELS = Path(__file__).parent / "fixtures" / "aimodels"
#: Case -> (model file, member name, the fragment's fields, the properties it
#: replaces). The fastText model is the one of the ``sentimentdemo`` project.
_CASES: dict[str, tuple[Path, str, dict[str, Any], tuple[str, ...]]] = {
    "crfsuite-description": (
        _AIMODELS / "crfsuite" / "complete.crfsuite",
        "demo/m.crfsuite",
        {"description": "A curated description of the tagger."},
        ("description",),
    ),
    "fasttext-domain-and-outputs": (
        _AIMODELS / "fasttext" / "sentimentdemo.bin",
        "demo/m.bin",
        {
            "ai_domain": ["sentiment analysis"],
            "ai_informationAboutApplication": '{"outputs":[{"name":"sentiment"}]}',
        },
        ("ai_domain", "ai_informationAboutApplication"),
    ),
}
_PYPROJECT = f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
id-registry = "{_REGISTRY}"

[tool.pitloom.fragment]
files = ["frag.spdx3.json"]
"""
_INIT = b'"""Demo."""\n'


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _cli(mp: pytest.MonkeyPatch, *args: str | Path) -> None:
    mp.setattr(sys, "argv", ["loom", *map(str, args)])
    assert __main__.main() == 0


def _project(base: Path, mp: pytest.MonkeyPatch, case: str) -> tuple[Path, str]:
    """The demo project with the model of *case*, a registry and a fragment
    that gives the model's id the case's fields; also the model's member name."""
    source, member, fields, _ = _CASES[case]
    project = base / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_bytes(_INIT)
    (project / member).write_bytes(source.read_bytes())
    (project / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _cli(
        mp,
        *("id", "generate", "--namespace", _NS),
        *("-o", project / _REGISTRY, "--project-dir", project, project),
    )
    registry = json.loads((project / _REGISTRY).read_bytes())
    spdx_id = registry["elements"]["ai_AIPackage"][member]["spdxId"]
    element = {"type": "ai_AIPackage", "spdxId": spdx_id, "name": "m", **fields}
    write_fragment(project / "frag.spdx3.json", fragment_graph([element], _NS))
    return project, member


def _wheel(base: Path, project: Path, member: str) -> Path:
    members = {"demo/__init__.py": _INIT, member: (project / member).read_bytes()}
    return write_model_wheel(base / "dist", members)


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


Route = Callable[[Path, pytest.MonkeyPatch, Path, str], str]


def _cli_project(base: Path, mp: pytest.MonkeyPatch, project: Path, _m: str) -> str:
    _cli(mp, "project", project, "--offline", "-o", base / "out.json")
    return (base / "out.json").read_text(encoding="utf-8")


def _cli_embed_wheel(
    base: Path, mp: pytest.MonkeyPatch, project: Path, member: str
) -> str:
    wheel = _wheel(base, project, member)
    _cli(mp, "embed-wheel", wheel, "--project-dir", project, "--offline")
    return _embedded(wheel)


def _lib_project(_base: Path, _mp: pytest.MonkeyPatch, project: Path, _m: str) -> str:
    return generate_project_sbom(project, offline=True)


def _lib_embed(base: Path, _mp: pytest.MonkeyPatch, project: Path, member: str) -> str:
    wheel = _wheel(base, project, member)
    embed_wheel_sbom(wheel, project_dir=project)
    return _embedded(wheel)


def _hook(_base: Path, _mp: pytest.MonkeyPatch, project: Path, _m: str) -> str:
    return hook_sbom(project)


_ROUTES: dict[str, Route] = {
    "cli-project": _cli_project,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-project": _lib_project,
    "lib-embed": _lib_embed,
    "hook": _hook,
}


@pytest.mark.parametrize("case", sorted(_CASES))
@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_the_curated_value_wins_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    route: str,
    case: str,
) -> None:
    project, member = _project(tmp_path, monkeypatch, case)
    capsys.readouterr()
    sbom = _ROUTES[route](tmp_path, monkeypatch, project, member)
    models = [e for e in json.loads(sbom)["@graph"] if e["type"] == "ai_AIPackage"]
    assert len(models) == 1
    if case.startswith("fasttext"):
        pytest.importorskip("fasttext")  # the optional ``fasttext`` extra
    _, _, fields, replaced = _CASES[case]
    assert {name: models[0].get(name) for name in fields} == fields
    err = capsys.readouterr().err
    merge = [line for line in err.splitlines() if "Merge:" in line]
    assert len(merge) == len(replaced)
    for line, name in zip(merge, replaced, strict=True):
        assert line.startswith(f"INFO: Merge: '{name}' on ai_AIPackage")
        assert "replacing the value generated from the model file" in line
    comment = models[0].get("comment", "")
    for name in replaced:
        for field in PROVENANCE_PROPERTY_FIELDS[name]:
            assert f"{field}: Source:" not in comment
