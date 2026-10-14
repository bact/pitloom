# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A requirement with an extra marker of its own, declared in another
extra (``dev = ["foo; extra == 'x'"]``), on every route: ``pyproject.toml``
on the directory route and through the Hatchling build hook, ``setup.cfg``
``extras_require``, an sdist with and without ``pyproject.toml``, and a
wheel's ``Requires-Dist`` as Hatchling, setuptools/pdm-backend and
flit_core write it.

It was recorded as required, though never installed without an extra.
Every route records it as optional for both extras, with one ``WARNING:``
that the inner condition is ignored.

See also: tests/assemble/test_dep_scope.py (the classifier).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from tests._author_routes import CREATED, hook_sbom, isolate, write_wheel
from tests.assemble.conftest import _make_sdist

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "demo"
version = "1.0"

[project.optional-dependencies]
dev = ["foo; extra == 'x'"]
x = ["baz"]
"""
_META = "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n"
#: ``Requires-Dist`` of ``foo`` as each backend writes it, then ``baz``.
_REQUIRES = {
    "hatchling": "foo; (extra == 'x') and extra == 'dev'",
    "setuptools": 'foo; extra == "x" and extra == "dev"',
    "flit": "foo ; extra == \"dev\" and ( extra == 'x')",
}
_WARNING = "Ignoring the inner extra condition of extra entry"


def _headers(backend: str) -> str:
    return (
        f"{_META}Provides-Extra: dev\nProvides-Extra: x\n"
        f"Requires-Dist: {_REQUIRES[backend]}\nRequires-Dist: baz; extra == 'x'\n"
    )


def _project(files: dict[str, str]) -> Callable[[Path], str]:
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


def _sdist(pyproject: str | None) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        members: dict[str, bytes | None] = {
            "PKG-INFO": _headers("setuptools").encode(),
            "pyproject.toml": None if pyproject is None else pyproject.encode(),
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
    "directory-pyproject": _project({"pyproject.toml": _PYPROJECT}),
    "hatchling-hook": _hook,
    "directory-setup-cfg": _project(
        {
            "setup.cfg": "[metadata]\nname = demo\nversion = 1.0\n"
            "[options.extras_require]\ndev =\n    foo; extra == 'x'\nx =\n    baz\n",
            "setup.py": "from setuptools import setup\nsetup()\n",
        }
    ),
    "sdist-pyproject": _sdist(_PYPROJECT),
    "sdist-pkg-info": _sdist(None),
    **{f"wheel-{backend}": _wheel(backend) for backend in _REQUIRES},
}


def _edge(sbom: str, name: str) -> tuple[str, str | None]:
    """``(relationshipType, comment)`` of the root's edge to *name*."""
    graph = json.loads(sbom)["@graph"]
    names = {node["spdxId"]: node.get("name") for node in graph if "spdxId" in node}
    (root,) = next(n for n in graph if n["type"] == "software_Sbom")["rootElement"]
    (edge,) = [
        node
        for node in graph
        if node.get("from") == root and names.get(node.get("to", [""])[0]) == name
    ]
    return edge["relationshipType"], edge.get("comment")


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_joined_extra_entry_is_optional_on_every_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    route: str,
) -> None:
    isolate(tmp_path, monkeypatch)
    with caplog.at_level(logging.WARNING):
        sbom = _ROUTES[route](tmp_path)
    assert _edge(sbom, "foo") == ("hasOptionalDependency", "extras: dev, x")
    assert _edge(sbom, "baz") == ("hasOptionalDependency", "extras: x")
    assert len([m for m in caplog.messages if _WARNING in m]) == 1
