# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``loom.set_model(name, path=...)`` fragment naming the project's model
file otherwise, merged on every route that merges configured fragments into
a project's SBOM (``project``, the library API, the Hatchling hook,
``embed-wheel --project-dir``): one ``ai_AIPackage`` with the loom name, the
id of the file's registry key and one ``INFO:``. ``loom merge`` has no base
document: both are fragments, the earlier file's name is kept with a
``WARNING:``.

See also: tests/assemble/test_fragments_model_names.py (the rule).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom import __main__, loom
from pitloom.assemble import generate_project_sbom
from pitloom.embed import embed_wheel_sbom
from tests._author_routes import hook_sbom, isolate
from tests._wheel_models import safetensors_bytes, write_model_wheel

_NS = "https://example.org/mn"
_MODEL = "demo/tiny.safetensors"
_LOOMED = "sentiment-classifier"
_REGISTRY = "loom-ids.json"
_FRAGMENT = "frag.spdx3.json"
_PYPROJECT = f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0.0"

[tool.pitloom]
id-registry = "{_REGISTRY}"
"""
_INIT = b'"""Demo."""\n'
_FRAGMENT_TABLE = f'\n[tool.pitloom.fragment]\nfiles = ["{_FRAGMENT}"]\n'
_INFO = (
    "INFO: Merge: 'name' on ai_AIPackage {id}: keeping the fragment's "
    f"'{_LOOMED}', dropping the project's 'tiny'."
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    isolate(tmp_path, monkeypatch)


def _cli(mp: pytest.MonkeyPatch, *args: str | Path) -> None:
    mp.setattr(sys, "argv", ["loom", *map(str, args)])
    assert __main__.main() == 0


def _project(
    base: Path,
    mp: pytest.MonkeyPatch,
    name: str | None = _LOOMED,
    *,
    path: bool = True,
    fragment: bool = True,
) -> Path:
    """The demo project with its model, a registry and a ``loom.run``
    fragment declaring the model as *name* (none when ``None``)."""
    project = base / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_bytes(_INIT)
    (project / _MODEL).write_bytes(safetensors_bytes())
    (project / "train.py").write_bytes(b"# train\n")
    toml = _PYPROJECT + (_FRAGMENT_TABLE if fragment else "")
    (project / "pyproject.toml").write_bytes(toml.encode())
    registry: list[str | Path] = ["-o", project / _REGISTRY, "--project-dir", project]
    _cli(mp, "id", "generate", "--namespace", _NS, *registry, project)
    if name is not None:
        mp.chdir(project)
        caller = "pitloom._loom_active_run._get_caller_script_path"
        with patch(caller, return_value="train.py"):
            with loom.run(_FRAGMENT, id_registry=_REGISTRY):
                loom.set_model(name, path=_MODEL if path else None)
        mp.chdir(base)
    return project


def _wheel(base: Path) -> Path:
    members = {"demo/__init__.py": _INIT, _MODEL: safetensors_bytes()}
    return write_model_wheel(base / "dist", members)


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        (name,) = [n for n in archive.namelist() if "/sboms/" in n]
        return archive.read(name).decode("utf-8")


def _cli_project(base: Path, mp: pytest.MonkeyPatch, project: Path) -> str:
    _cli(mp, "project", project, "--offline", "-o", base / "out.json")
    return (base / "out.json").read_text(encoding="utf-8")


def _cli_embed_wheel(base: Path, mp: pytest.MonkeyPatch, project: Path) -> str:
    wheel = _wheel(base)
    _cli(mp, "embed-wheel", wheel, "--project-dir", project, "--offline")
    return _embedded(wheel)


def _lib_project(_base: Path, _mp: pytest.MonkeyPatch, project: Path) -> str:
    return generate_project_sbom(project, offline=True)


def _lib_embed(base: Path, _mp: pytest.MonkeyPatch, project: Path) -> str:
    wheel = _wheel(base)
    embed_wheel_sbom(wheel, project_dir=project)
    return _embedded(wheel)


def _hook(_base: Path, _mp: pytest.MonkeyPatch, project: Path) -> str:
    return hook_sbom(project)


_ROUTES: dict[str, Callable[[Path, pytest.MonkeyPatch, Path], str]] = {
    "cli-project": _cli_project,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-project": _lib_project,
    "lib-embed": _lib_embed,
    "hook": _hook,
}


def _models(sbom: str) -> dict[str, str]:
    """``ai_AIPackage`` name -> id."""
    graph = json.loads(sbom)["@graph"]
    return {e["name"]: e["spdxId"] for e in graph if e["type"] == "ai_AIPackage"}


def _model_id(project: Path) -> str:
    registry = json.loads((project / _REGISTRY).read_bytes())
    return str(registry["elements"]["ai_AIPackage"][_MODEL]["spdxId"])


def _merge_lines(err: str) -> list[str]:
    return [line for line in err.splitlines() if "Merge:" in line]


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_the_loom_name_wins_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    route: str,
) -> None:
    project = _project(tmp_path, monkeypatch)
    capsys.readouterr()
    sbom = _ROUTES[route](tmp_path, monkeypatch, project)
    model_id = _model_id(project)
    assert _models(sbom) == {_LOOMED: model_id}
    assert _merge_lines(capsys.readouterr().err) == [_INFO.format(id=model_id)]


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        ("tiny", True, {"tiny"}),
        (_LOOMED, False, {"tiny", _LOOMED}),
        (None, True, {"tiny"}),
    ],
    ids=["same-name", "no-path", "no-fragment-model"],
)
def test_other_loom_declarations_merge_silently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str | None,
    path: bool,
    expected: set[str],
) -> None:
    """A loom model with no ``path=`` is keyed by its name: another id, no
    fold. Without a fragment model the project's is untouched."""
    project = _project(
        tmp_path, monkeypatch, name, path=path, fragment=name is not None
    )
    capsys.readouterr()
    models = _models(_cli_project(tmp_path, monkeypatch, project))
    assert set(models) == expected
    assert models["tiny"] == _model_id(project)
    assert not _merge_lines(capsys.readouterr().err)


def test_a_second_run_keeps_the_file_key_and_the_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The registry harvests the renamed model under its file's key: run 2
    changes neither the registry nor the SBOM."""
    project = _project(tmp_path, monkeypatch)
    first = _cli_project(tmp_path, monkeypatch, project)
    registry = (project / _REGISTRY).read_bytes()
    assert _LOOMED in _models(first)
    assert list(json.loads(registry)["elements"]["ai_AIPackage"]) == [_MODEL]
    assert _cli_project(tmp_path, monkeypatch, project) == first
    assert (project / _REGISTRY).read_bytes() == registry


@pytest.mark.parametrize(
    ("project_file", "kept", "dropped"),
    [("a.spdx3.json", "tiny", _LOOMED), ("z.spdx3.json", _LOOMED, "tiny")],
    ids=["project-first", "loom-first"],
)
def test_loom_merge_keeps_the_earlier_fragment_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    project_file: str,
    kept: str,
    dropped: str,
) -> None:
    project = _project(tmp_path, monkeypatch, fragment=False)
    merge_dir = tmp_path / "frags"
    merge_dir.mkdir()
    (merge_dir / project_file).write_text(
        generate_project_sbom(project, offline=True), encoding="utf-8"
    )
    (merge_dir / "m.spdx3.json").write_bytes((project / _FRAGMENT).read_bytes())
    capsys.readouterr()
    _cli(monkeypatch, "merge", merge_dir, "-o", tmp_path / "merged.json")
    merged = (tmp_path / "merged.json").read_text(encoding="utf-8")
    assert list(_models(merged)) == [kept]
    (line,) = _merge_lines(capsys.readouterr().err)
    assert line.startswith("WARNING: Merge: conflicting 'name' on ai_AIPackage")
    assert line.endswith(f"keeping {kept!r}, dropping {dropped!r}.")
