# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""One project, one licence value on every surface: the directory through
``loom project`` and the library, the Hatchling hook's reader, and the
project's sdist as ``.tar.gz`` (``loom generate``) and ``.zip`` (library).
The project's own licence files give the concluded second opinion when the
manifest states a licence, the declared licence when it is silent.

See also: tests/extract/project/test_sdist_license.py (the sdist reader's
adversarial archives) and test_license_elements_surfaces.py (one value, one
element on every surface).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom
from tests._license_graph import hook_metadata, license_value, project_graph
from tests.assemble.embed_surfaces_shared import run_cli

from .conftest import _make_sdist

_DECLARED = "hasDeclaredLicense"
_CONCLUDED = "hasConcludedLicense"
_MIT = 'license = "MIT"\n'
_MIT_HEADER = "License-Expression: MIT\n"

#: id -> (``[project]`` licence line, PKG-INFO licence header (``None``: no
#: PKG-INFO), root members), and the expected (declared, concluded).
_Variant = tuple[str, str | None, dict[str, bytes]]
_VARIANTS: dict[str, tuple[_Variant, tuple[list[str], list[str]]]] = {
    "agree": ((_MIT, _MIT_HEADER, {"LICENSE": b"MIT\n"}), (["MIT"], ["MIT"])),
    "conflict": (
        (_MIT, _MIT_HEADER, {"LICENSE": b"Apache-2.0\n"}),
        (["MIT"], ["Apache-2.0"]),
    ),
    "silent": (("", "", {"LICENSE": b"Apache-2.0\n"}), (["Apache-2.0"], [])),
    "blank": (
        ('license = ""\n', "License: \n", {"LICENSE": b"Apache-2.0\n"}),
        (["Apache-2.0"], []),
    ),
    "cff": (
        (
            "",
            "",
            {
                "CITATION.cff": b"license: BSD-3-Clause\n",
                "LICENSE": b"Apache-2.0\n",
            },
        ),
        (["BSD-3-Clause"], []),
    ),
    "no-file": ((_MIT, _MIT_HEADER, {}), (["MIT"], [])),
    "no-pkg-info": (
        (_MIT, None, {"LICENSE": b"Apache-2.0\n"}),
        (["MIT"], ["Apache-2.0"]),
    ),
}


#: Variants the Hatchling hook cannot read, and why.
_NOT_HOOK = {
    "blank": "Hatchling refuses a blank project.license",
    "no-pkg-info": "a directory has no PKG-INFO: same project as 'conflict'",
}


def _write_dir(root: Path, variant: _Variant) -> Path:
    line, _, members = variant
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\nversion = "1.0.0"\n{line}', encoding="utf-8"
    )
    for name, data in members.items():
        (root / name).write_bytes(data)
    return root


def _write_sdist(tmp: Path, variant: _Variant, fmt: str) -> Path:
    line, header, members = variant
    pkg_info = (
        None
        if header is None
        else f"Metadata-Version: 2.4\nName: demo\nVersion: 1.0.0\n{header}".encode()
    )
    tmp.mkdir()
    return _make_sdist(tmp, line, members={"PKG-INFO": pkg_info, **members}, fmt=fmt)


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _dir_cli(tmp: Path, variant: _Variant, mp: pytest.MonkeyPatch) -> Any:
    out = tmp / "out.spdx3.json"
    run_cli(
        ["project", str(_write_dir(tmp / "d", variant)), "--offline", "-o", str(out)],
        mp,
    )
    return _graph(out.read_text(encoding="utf-8"))


def _dir_lib(tmp: Path, variant: _Variant, _mp: pytest.MonkeyPatch) -> Any:
    return _graph(generate_project_sbom(_write_dir(tmp / "d", variant), offline=True))


def _hook(tmp: Path, variant: _Variant, _mp: pytest.MonkeyPatch) -> Any:
    return project_graph(hook_metadata(_write_dir(tmp / "d", variant)))


def _sdist_tar_cli(tmp: Path, variant: _Variant, mp: pytest.MonkeyPatch) -> Any:
    out = tmp / "out.spdx3.json"
    sdist = _write_sdist(tmp / "s", variant, "tar")
    run_cli(["generate", str(sdist), "--offline", "-o", str(out)], mp)
    return _graph(out.read_text(encoding="utf-8"))


def _sdist_zip_lib(tmp: Path, variant: _Variant, _mp: pytest.MonkeyPatch) -> Any:
    sdist = _write_sdist(tmp / "s", variant, "zip")
    return _graph(generate_project_sbom(sdist, offline=True))


_SURFACES: dict[str, Callable[[Path, _Variant, pytest.MonkeyPatch], Any]] = {
    "dir-cli": _dir_cli,
    "dir-lib": _dir_lib,
    "hook": _hook,
    "sdist-tar-cli": _sdist_tar_cli,
    "sdist-zip-lib": _sdist_zip_lib,
}


def _package_licences(graph: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """The values ``demo``'s declared and concluded relationships point at."""
    (package,) = [
        e["spdxId"]
        for e in graph
        if e["type"] == "software_Package" and e["name"] == "demo"
    ]
    values = {e["spdxId"]: license_value(e) for e in graph if "spdxId" in e}
    found: dict[str, list[str]] = {_DECLARED: [], _CONCLUDED: []}
    for rel in graph:
        kind = rel.get("relationshipType")
        if kind in found and rel["from"] == package:
            found[kind] += [str(values[target]) for target in rel["to"]]
    return sorted(found[_DECLARED]), sorted(found[_CONCLUDED])


@pytest.mark.parametrize("surface", sorted(_SURFACES))
@pytest.mark.parametrize("variant", sorted(_VARIANTS))
def test_one_licence_value_on_every_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variant: str, surface: str
) -> None:
    # No [tool.pitloom] to borrow from the current directory.
    monkeypatch.chdir(tmp_path)
    project, expected = _VARIANTS[variant]
    if surface == "hook" and variant in _NOT_HOOK:
        pytest.skip(_NOT_HOOK[variant])

    graph = _SURFACES[surface](tmp_path, project, monkeypatch)

    assert _package_licences(graph) == expected
