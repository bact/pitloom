# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""PEP 639 ``[project.license-files]`` entries are not listed in an SBOM.

The build backend copies them into the wheel's own ``.dist-info/licenses/``;
an SBOM describes the packaged project, not that container, so no file,
directory or file-level ``hasDeclaredLicense`` element is emitted for them.
The package-level declared license stays.

See also:
- :mod:`tests.extract.test_wheel_payload` for the wheel-reading surfaces.
- ``tests/fixtures/real-world-projects/README.md`` for fixture provenance.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble._generators import generate_project_sbom
from tests.extract.conftest import make_hook
from tests.fixtures.real_world import REAL_WORLD_ROOT, extract_sdist, sdist_available

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "lfdemo"
version = "1.0.0"
license = "MIT"
license-files = ["LICENSE", "NOTICE"]
"""


def _library(project: Path) -> str:
    return generate_project_sbom(project, offline=True)


def _hatchling_hook(project: Path) -> str:
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        (staged,) = build_data["sbom_files"]
        return Path(staged).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def _declared_license_targets(graph: list[dict[str, Any]]) -> dict[str, str]:
    """``from`` spdxId -> ``to`` license spdxId, per hasDeclaredLicense."""
    return {
        n["from"]: n["to"][0]
        for n in graph
        if n.get("type") == "Relationship"
        and n.get("relationshipType") == "hasDeclaredLicense"
    }


def _assert_no_dist_info(graph: list[dict[str, Any]]) -> None:
    names = [str(n.get("name", "")) for n in graph]
    assert not [name for name in names if ".dist-info" in name]


@pytest.mark.parametrize(
    "surface", [_library, _hatchling_hook], ids=["library", "hatchling-hook"]
)
def test_declared_license_files_not_listed(
    tmp_path: Path, surface: Callable[[Path], str]
) -> None:
    """A declared license file yields no file/directory element and no
    file-level license link; the package-level declared license and a
    source file's own ``SPDX-License-Identifier`` header link both stay."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Notice\n", encoding="utf-8")
    (tmp_path / "lfdemo").mkdir()
    (tmp_path / "lfdemo" / "__init__.py").write_text(
        "# SPDX-License-Identifier: Apache-2.0\n", encoding="utf-8"
    )

    graph = json.loads(surface(tmp_path))["@graph"]

    _assert_no_dist_info(graph)
    files = {n["name"]: n for n in graph if n.get("type") == "software_File"}
    assert "LICENSE" not in files
    assert "NOTICE" not in files
    licenses = {
        n["spdxId"]: n["name"]
        for n in graph
        if str(n.get("type")).startswith("simplelicensing_")
    }
    targets = _declared_license_targets(graph)
    main_id = next(n for n in graph if n.get("type") == "software_Sbom")["rootElement"][
        0
    ]
    assert licenses[targets.pop(main_id)] == "MIT"
    header_file_id = files["lfdemo/__init__.py"]["spdxId"]
    assert licenses[targets.pop(header_file_id)] == "Apache-2.0"
    assert not targets  # nothing else carries a declared license
    assert "project.license-files" not in json.dumps(graph)


@pytest.mark.parametrize(
    "fixture",
    ["cachetools-7.1.8", "markupsafe-3.0.3"],
)
def test_real_world_license_files_not_listed(tmp_path: Path, fixture: str) -> None:
    """Real sdists declaring ``[project.license-files]``: nothing under
    ``.dist-info`` in the SBOM, package-level declared license kept."""
    fixture_dir = REAL_WORLD_ROOT / "setuptools" / fixture
    if not sdist_available(fixture_dir):
        pytest.skip(f"{fixture}: vendored sdist not present")

    graph = json.loads(_library(extract_sdist(fixture_dir, tmp_path)))["@graph"]

    _assert_no_dist_info(graph)
    main_id = next(n for n in graph if n.get("type") == "software_Sbom")["rootElement"][
        0
    ]
    assert main_id in _declared_license_targets(graph)
