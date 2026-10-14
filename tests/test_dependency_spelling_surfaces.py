# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A dependency's spelling on every route: ``Foo_Bar``, ``foo.bar2``,
``FOO-baz``, and ``Foo_Bar`` again as ``foo-bar``, with an extra spelt
``Zed_Extra``, of a project named ``DEMO``. A ``[project]`` read and
Hatchling write the PEP 503 name; setuptools keeps the spelling in
``Requires-Dist``. The SBOM shows one spelling whatever the route read:
the PEP 503 name the ``pkg:pypi`` PURL uses, the declared constraint as
``packaging`` spells it, the two spellings of ``foo-bar`` one package,
their constraints sorted. ``loom env`` shows each installed distribution
by that name too, whatever its ``.dist-info`` spells. The project itself
keeps its declared name (``DEMO``) on every route, its PURL the PEP 503
name.

See also: tests/_dependency_view.py (what is compared) and
tests/test_joined_extra_surfaces.py (the same routes for extras).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import (
    generate_env_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from tests._author_routes import CREATED, hook_sbom, isolate, write_wheel
from tests._dependency_view import dependency_view, root_package
from tests.assemble.conftest import _make_sdist

_DEPS = ["Foo_Bar>=1", "foo.bar2", "FOO-baz", "foo-bar<3"]
_EXTRA = "Qux_Q; python_version>'3'"
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    f'[project]\nname = "DEMO"\nversion = "1.0"\ndependencies = {_DEPS!r}\n'
    f'[project.optional-dependencies]\nZed_Extra = ["{_EXTRA}"]\n'
)
_SETUP_CFG = (
    "[metadata]\nname = DEMO\nversion = 1.0\n[options]\ninstall_requires =\n"
    + "".join(f"    {d}\n" for d in _DEPS)
    + f"[options.extras_require]\nZed_Extra =\n    {_EXTRA}\n"
)
#: ``Requires-Dist`` as each backend writes it: setuptools keeps the
#: spelling and order; Hatchling 1.32.3 writes the PEP 503 name, sorted,
#: and its own marker.
_REQUIRES = {
    "setuptools": [*_DEPS, 'Qux_Q; python_version > "3" and extra == "zed-extra"'],
    "hatchling": [
        "foo-bar2",
        "foo-bar<3",
        "foo-bar>=1",
        "foo-baz",
        "qux-q; (python_version > '3') and extra == 'zed-extra'",
    ],
}


def _headers(backend: str) -> str:
    lines = "".join(f"Requires-Dist: {r}\n" for r in _REQUIRES[backend])
    return (
        "Metadata-Version: 2.1\nName: DEMO\nVersion: 1.0\n"
        f"Provides-Extra: zed-extra\n{lines}"
    )


def _directory(files: dict[str, str]) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        (tmp_path / "demo").mkdir()
        (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
        for name, text in files.items():
            (tmp_path / name).write_text(text, encoding="utf-8")
        return generate_project_sbom(tmp_path, creation_metadata=CREATED, offline=True)

    return run


def _hook(tmp_path: Path) -> str:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return hook_sbom(tmp_path)


def _sdist(pkg_info: str | None) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        members = {
            "PKG-INFO": None if pkg_info is None else pkg_info.encode(),
            "pyproject.toml": _PYPROJECT.encode(),
        }
        sdist = _make_sdist(tmp_path, members=members)
        return generate_project_sbom(sdist, creation_metadata=CREATED, offline=True)

    return run


def _wheel(backend: str) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        wheel = write_wheel(tmp_path, _headers(backend))
        return generate_wheel_sbom(wheel, creation_metadata=CREATED)

    return run


_ROUTES: dict[str, Callable[[Path], str]] = {
    "directory-pyproject": _directory({"pyproject.toml": _PYPROJECT}),
    "directory-setup-cfg": _directory(
        {"setup.cfg": _SETUP_CFG, "setup.py": "from setuptools import setup\nsetup()\n"}
    ),
    "hatchling-hook": _hook,
    "sdist-setuptools-pkg-info": _sdist(_headers("setuptools")),
    "sdist-pyproject": _sdist(None),
    **{f"wheel-{backend}": _wheel(backend) for backend in _REQUIRES},
}

_PURL = "pkg:pypi/{}"
_EXPECTED = [
    ("foo-bar", _PURL.format("foo-bar"), "foo-bar<3 | foo-bar>=1", "dependsOn"),
    ("foo-bar2", _PURL.format("foo-bar2"), "foo-bar2", "dependsOn"),
    ("foo-baz", _PURL.format("foo-baz"), "foo-baz", "dependsOn"),
    (
        "qux-q",
        _PURL.format("qux-q"),
        'qux-q; python_version > "3" and extra == "zed-extra"',
        "hasOptionalDependency",
    ),
]


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_dependency_spelling_is_one_on_every_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """Regression: a setuptools-built wheel or sdist, and ``setup.cfg``,
    named the package ``Foo_Bar`` (two spellings of one package, ``Foo_Bar``
    and ``foo-bar``, kept the first) where a ``[project]`` read named it
    ``foo-bar``; the declared constraint kept each route's spelling."""
    isolate(tmp_path, monkeypatch)

    sbom = _ROUTES[route](tmp_path)

    view = dependency_view(sbom)
    assert [row[:4] for row in view] == _EXPECTED
    assert view[-1][5] == "extras: zed-extra"
    assert root_package(sbom) == ("DEMO", "pkg:pypi/demo@1.0")


#: Installed distributions as their ``.dist-info`` spells them, and the
#: name every route shows (:data:`_EXPECTED`).
_INSTALLED = {"Foo_Bar": "foo-bar", "foo.bar2": "foo-bar2", "FOO_baz": "foo-baz"}


def test_installed_distribution_shows_the_canonical_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: ``loom env`` named a package as its ``.dist-info``
    spells it (``Foo_Bar``) where every other route shows ``foo-bar``; the
    installed metadata is still found by the canonical name."""
    isolate(tmp_path, monkeypatch)
    site = tmp_path / "site"
    tree = []
    for name, canonical in _INSTALLED.items():
        (site / f"{name}-1.0.dist-info").mkdir(parents=True)
        (site / f"{name}-1.0.dist-info" / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\nSummary: {name}\n",
            encoding="utf-8",
        )
        package = {"key": canonical, "package_name": name, "installed_version": "1.0"}
        tree.append({"package": package, "dependencies": []})
    monkeypatch.syspath_prepend(str(site))
    pipdeptree = subprocess.CompletedProcess([], 0, json.dumps(tree).encode(), b"")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: pipdeptree)

    sbom = generate_env_sbom(creation_metadata=CREATED, offline=True)

    view = dependency_view(sbom)
    assert [row[:2] for row in view] == [
        (n, f"{p}@1.0") for n, p, *_ in _EXPECTED if n in _INSTALLED.values()
    ]
    described = {
        node["name"]: node.get("description")
        for node in json.loads(sbom)["@graph"]
        if node["type"] == "software_Package"
    }
    assert {described[c] for c in _INSTALLED.values()} == set(_INSTALLED)
