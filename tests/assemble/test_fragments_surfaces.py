# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A project's configured fragments merge alike on every surface that reads
them: the library, ``loom project``, ``loom embed-wheel --project-dir`` and
the Hatchling build hook.

- An earlier SBOM of the same project, configured as a fragment, is skipped
  with one ``WARNING:`` (it once crashed on a duplicate ``spdxId``), and an
  error when it is ``required``.
- ``loom fragment list`` reports that fragment as the build treats it.
- A fragment licence equal to the project's own unifies with it.

See also: tests/core/test_fragments_merge_licenses.py (the unification
rules) and tests/assemble/embed_surfaces_shared.py (the demo project).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import FragmentMergeError, generate_project_sbom
from pitloom.embed import find_embedded_sbom
from tests._license_graph import (
    fragment_graph,
    license_elements,
    license_node,
    license_targets,
    license_values,
    licensed_package,
)
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import DEPENDENCY, demo_project, run_cli
from tests.extract.conftest import make_hook

_LICENSE = 'license = "MIT"\n'
_PINNED = "2026-01-01T00:00:00Z"
_SAME_DOCUMENT = "is the document being merged into"


def _project(tmp: Path, fragment: dict[str, Any] | None, required: bool) -> Path:
    """The demo project, with *fragment* written and configured."""
    toml = ""
    if fragment is not None:
        (tmp / "proj").mkdir(parents=True, exist_ok=True)
        (tmp / "proj" / "frag.spdx3.json").write_text(
            json.dumps(fragment), encoding="utf-8"
        )
        entry = (
            '{ path = "frag.spdx3.json", required = true }'
            if required
            else '"frag.spdx3.json"'
        )
        toml = f"\n[tool.pitloom.fragment]\nfiles = [{entry}]\n"
    project = demo_project(tmp, toml)
    pyproject = project / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(
        text.replace('version = "1.0.0"\n', f'version = "1.0.0"\n{_LICENSE}', 1),
        encoding="utf-8",
    )
    return project


def _lib(_tmp: Path, project: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(project, offline=True)


def _cli_project(tmp: Path, project: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "out.spdx3.json"
    run_cli(["project", str(project), "--offline", "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


def _cli_embed(tmp: Path, project: Path, mp: pytest.MonkeyPatch) -> str:
    wheel = _make_dummy_wheel(
        tmp / "w",
        "demo",
        "1.0.0",
        requires_dist=(f"{DEPENDENCY}==1.0",),
        license_expression="MIT",
    )
    run_cli(["embed-wheel", str(wheel), "--project-dir", str(project), "--offline"], mp)
    found = find_embedded_sbom(wheel)
    assert found is not None
    return found.data.decode("utf-8")


def _hook(_tmp: Path, project: Path, _mp: pytest.MonkeyPatch) -> str:
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        return Path(build_data["sbom_files"][0]).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


_SURFACES: dict[str, Callable[[Path, Path, pytest.MonkeyPatch], str]] = {
    "lib": _lib,
    "cli-project": _cli_project,
    "cli-embed-wheel": _cli_embed,
    "hook": _hook,
}


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _relicensed(sbom: str) -> dict[str, Any]:
    """*sbom* with its licence changed to ``Apache-2.0``."""
    data: dict[str, Any] = json.loads(sbom)
    for element in license_elements(data["@graph"]):
        element["simplelicensing_licenseExpression"] = "Apache-2.0"
    return data


@pytest.fixture(autouse=True, name="_pinned")
def pinned_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")


@pytest.mark.parametrize("relicense", [False, True], ids=["same", "relicensed"])
@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_earlier_sbom_of_the_project_is_skipped(
    surface: str,
    relicense: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run = _SURFACES[surface]
    earlier = run(tmp_path / "a", _project(tmp_path / "a", None, False), monkeypatch)
    fragment = _relicensed(earlier) if relicense else json.loads(earlier)
    assert (fragment != json.loads(earlier)) is relicense
    project = _project(tmp_path / "b", fragment, False)
    with caplog.at_level(logging.WARNING):
        again = run(tmp_path / "b", project, monkeypatch)
    skips = [r for r in caplog.records if _SAME_DOCUMENT in r.getMessage()]
    assert len(skips) == 1
    assert again == earlier


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_earlier_sbom_required_fails(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = _SURFACES[surface]
    earlier = run(tmp_path / "a", _project(tmp_path / "a", None, False), monkeypatch)
    project = _project(tmp_path / "b", json.loads(earlier), True)
    # A CLI run exits 1 (run_cli asserts 0) and prints the error instead.
    cli = surface.startswith("cli-")
    with pytest.raises(AssertionError if cli else FragmentMergeError) as raised:
        run(tmp_path / "b", project, monkeypatch)
    message = capsys.readouterr().err if cli else str(raised.value)
    assert "1 required fragment(s) could not be merged" in message


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_fragment_licence_unifies_with_the_project_licence(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ns = "https://spdx.org/spdxdocs/frag"
    fragment = fragment_graph(
        [
            license_node(f"{ns}#L", "expression", "mit"),
            *licensed_package("P", f"{ns}#L"),
        ]
    )
    project = _project(tmp_path, fragment, False)
    graph = _graph(_SURFACES[surface](tmp_path, project, monkeypatch))
    values = license_values(graph)
    assert list(values.values()) == ["MIT"]
    assert not next(iter(values)).startswith(ns)
    assert license_targets(graph) == ["MIT", "MIT"]


@pytest.mark.parametrize(
    ("same", "required"),
    [(False, True), (True, False), (True, True)],
    ids=["other", "same", "same-required"],
)
def test_fragment_list_flags_an_earlier_sbom(
    same: bool,
    required: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom fragment list`` sees an earlier SBOM of the project as a build
    does: ``SAME_DOCUMENT=true``, the build's ``WARNING:``, and exit 1 when
    it is required."""
    earlier = json.loads(
        _lib(tmp_path / "a", _project(tmp_path / "a", None, False), monkeypatch)
    )
    if not same:
        (document,) = [e for e in earlier["@graph"] if e["type"] == "SpdxDocument"]
        document["spdxId"] += "-other"
    project = _project(tmp_path / "b", earlier, required)
    capsys.readouterr()
    monkeypatch.setattr(
        sys, "argv", ["loom", "fragment", "list", "--project-dir", str(project)]
    )
    assert __main__.main() == int(same and required)
    out, err = capsys.readouterr()
    assert f"SAME_DOCUMENT={str(same).lower()}" in out
    assert len([x for x in err.splitlines() if _SAME_DOCUMENT in x]) == int(same)
