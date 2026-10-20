# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Requirements files named by ``setup.cfg``'s ``file:`` directive, alone
and filling a ``[project]``'s ``dynamic`` dependency fields, on every
route: the project directory, and the sdist and wheel real setuptools
builds of it (offline, in a child). The SBOMs list the same dependencies.

See also: tests/extract/project/test_setup_cfg_requirements_files.py (the
directory read, row by row) and tests/_dependency_view.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from tests._author_routes import CREATED, isolate
from tests._dependency_view import dependency_view
from tests._setuptools_build import build_dist

_OPTIONS = (
    "[options]\npackages = demo\ninstall_requires = file: req.txt, more.txt\n"
    "[options.extras_require]\nDev_X = file: dev.txt\n"
)
_FILES = {
    "req.txt": "# base\r\nFoo_Bar>=1 ; python_version>'3'  # why\r\n",
    "more.txt": "baz",
    "dev.txt": "not-installed-x\n",
    "demo/__init__.py": "",
}
_PROJECTS = {
    "setup-cfg": {
        "setup.cfg": f"[metadata]\nname = demo\nversion = 1.0\n{_OPTIONS}",
        "setup.py": "from setuptools import setup\nsetup()\n",
    },
    "pyproject-dynamic": {
        "pyproject.toml": '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "demo"\nversion = "1.0"\n'
        'dynamic = ["dependencies", "optional-dependencies"]\n',
        "setup.cfg": _OPTIONS,
    },
}
_EXPECTED = [
    ("baz", "pkg:pypi/baz", "baz", "dependsOn", "runtime", None),
    (
        "foo-bar",
        "pkg:pypi/foo-bar",
        'foo-bar>=1; python_version > "3"',
        "dependsOn",
        "runtime",
        None,
    ),
    (
        "not-installed-x",
        "pkg:pypi/not-installed-x",
        'not-installed-x; extra == "dev-x"',
        "hasOptionalDependency",
        None,
        "extras: dev-x",
    ),
]


@pytest.mark.parametrize("name", sorted(_PROJECTS))
def test_setup_cfg_requirements_files_on_every_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Every route lists the requirements files' dependencies, never a
    dependency named ``file: req.txt`` (``setup.cfg`` alone) or none
    (``[project]`` with ``dynamic``)."""
    isolate(tmp_path, monkeypatch)
    project = tmp_path / "p"
    for rel, text in {**_PROJECTS[name], **_FILES}.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text(text, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    sdist, wheel = (build_dist(project, out, kind) for kind in ("sdist", "wheel"))
    views = {
        "directory": generate_project_sbom(
            project, creation_metadata=CREATED, offline=True
        ),
        "sdist": generate_project_sbom(sdist, creation_metadata=CREATED, offline=True),
        "wheel": generate_wheel_sbom(wheel, creation_metadata=CREATED, offline=True),
    }

    assert {route: dependency_view(sbom) for route, sbom in views.items()} == (
        dict.fromkeys(views, _EXPECTED)
    )
