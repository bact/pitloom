# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A direct-reference dependency (``name @ URL``) is not looked up on PyPI,
on every route: ``loom generate``, :func:`generate_project_sbom`, the
Hatchling hook, a requirements file a setuptools directive lists, and a
project whose ``pylock.toml`` locks the dependency to a VCS source.

PyPI knows a package by name only, so its record for that name may be
another project's: its licence, supplier and hash were written into the
dependency's package. The package is still listed, with its declared
constraint; a registry dependency beside it is still looked up.

See also: tests/core/test_pep508.py (:func:`is_direct_reference`).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from packaging.utils import canonicalize_name

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps, deps_pypi
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._author_routes import CREATED, hook_sbom, isolate
from tests.assemble.conftest import _make_ci
from tests.assemble.embed_surfaces_shared import run_cli

_URL = "Impostor_Pkg @ git+https://example.com/impostor.git@v1"
_PLAIN = "plain-pkg==1.0"
_HEAD = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0"\n'
)
_HATCH = "[tool.hatch.metadata]\nallow-direct-references = true\n"

Calls = list[tuple[str, "str | None"]]


def _record(name: str) -> dict[str, Any]:
    """The PyPI record the fake serves for *name*: every fact names it."""
    key = canonicalize_name(name)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return {
        "info": {
            "license_expression": f"LicenseRef-pypi-{key}",
            "author": f"pypi-author-{key}",
        },
        "urls": [
            {
                "packagetype": "bdist_wheel",
                "filename": f"{key}-1.0-py3-none-any.whl",
                "digests": {"sha256": digest},
            }
        ],
    }


@pytest.fixture(name="calls")
def calls_fixture(monkeypatch: pytest.MonkeyPatch) -> Calls:
    """Every PyPI lookup, by PEP 503 name and version; none reaches PyPI."""
    seen: Calls = []

    def fetch(name: str, version: str | None) -> dict[str, Any]:
        seen.append((canonicalize_name(name), version))
        return _record(name)

    monkeypatch.setattr(deps_pypi, "_fetch_pypi_release_info", fetch)
    monkeypatch.setattr(deps, "_fetch_pypi_release_info", fetch)
    return seen


def _pypi_facts(sbom: str, name: str) -> list[str]:
    """The facts of *name*'s PyPI record found in *sbom*."""
    record = _record(name)
    facts = [
        record["info"]["license_expression"],
        record["urls"][0]["digests"]["sha256"],
        f'"{record["info"]["author"]}"',
    ]
    return [fact for fact in facts if fact in sbom]


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "__init__.py").write_text("", encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def _library(files: dict[str, str]) -> Callable[[Path], str]:
    def run(tmp_path: Path) -> str:
        return generate_project_sbom(
            _project(tmp_path, files), creation_metadata=CREATED
        )

    return run


def _cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    project = _project(tmp_path, {"pyproject.toml": _pyproject([_URL, _PLAIN])})
    output = tmp_path / "sbom.json"
    run_cli(["generate", str(project), "-o", str(output)], monkeypatch)
    return output.read_text(encoding="utf-8")


def _hook(tmp_path: Path) -> str:
    files = {"pyproject.toml": _pyproject([_URL, _PLAIN]) + _HATCH}
    return hook_sbom(_project(tmp_path, files))


def _pyproject(dependencies: list[str]) -> str:
    return f"{_HEAD}dependencies = {json.dumps(dependencies)}\n"


_REQUIREMENTS = (
    '[build-system]\nrequires = ["setuptools"]\n'
    'build-backend = "setuptools.build_meta"\n'
    '[project]\nname = "demo"\nversion = "1.0"\ndynamic = ["dependencies"]\n'
    '[tool.setuptools.dynamic]\ndependencies = {file = ["requirements.in"]}\n'
)
_PYLOCK = (
    'lock-version = "1.0"\ncreated-by = "x"\n'
    '[[packages]]\nname = "impostor-pkg"\n'
    '[packages.vcs]\ntype = "git"\nurl = "https://example.com/impostor.git"\n'
    'commit-id = "0123456789abcdef0123456789abcdef01234567"\n'
    '[[packages]]\nname = "plain-pkg"\nversion = "1.0"\n'
)
_ROUTES: dict[str, Callable[[Path], str]] = {
    "library": _library({"pyproject.toml": _pyproject([_URL, _PLAIN])}),
    "hatchling-hook": _hook,
    "requirements-file": _library(
        {"pyproject.toml": _REQUIREMENTS, "requirements.in": f"{_URL}\n{_PLAIN}\n"}
    ),
    "pylock-vcs": _library(
        {"pyproject.toml": _pyproject([_URL, _PLAIN]), "pylock.toml": _PYLOCK}
    ),
}


@pytest.mark.parametrize("route", ["cli", *sorted(_ROUTES)])
def test_a_direct_reference_is_not_looked_up_on_pypi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: Calls, route: str
) -> None:
    """No lookup and no PyPI fact for the direct reference; the registry
    dependency beside it is still looked up, its facts written."""
    isolate(tmp_path, monkeypatch)
    sbom = _cli(tmp_path, monkeypatch) if route == "cli" else _ROUTES[route](tmp_path)
    assert [name for name, _version in calls if name == "impostor-pkg"] == []
    assert _pypi_facts(sbom, "impostor-pkg") == []
    assert ("plain-pkg", "1.0") in calls
    assert len(_pypi_facts(sbom, "plain-pkg")) == 3
    names = {e.get("name") for e in json.loads(sbom)["@graph"]}
    assert {"impostor-pkg", "plain-pkg"} <= names


@pytest.mark.parametrize(
    "dependency",
    [
        _URL,
        "IMPOSTOR.pkg[a,b] @ https://example.com/x.whl ; python_version >= '3.8'",
        "impostor-pkg @ https://example.com/a;b/impostor-pkg-1.0.whl",
        "impostor_pkg @ file:///C:/wheels/impostor_pkg-1.0-py3-none-any.whl",
    ],
    ids=["git-tag", "extras-marker", "semicolon", "windows-file"],
)
def test_every_spelling_of_a_direct_reference_is_not_looked_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: Calls, dependency: str
) -> None:
    """With only the direct reference declared, the SBOM is the offline
    one, byte for byte, and the same on a second run."""
    isolate(tmp_path, monkeypatch)
    project = _project(tmp_path, {"pyproject.toml": _pyproject([dependency])})
    online = generate_project_sbom(project, creation_metadata=CREATED)
    again = generate_project_sbom(project, creation_metadata=CREATED)
    offline = generate_project_sbom(project, creation_metadata=CREATED, offline=True)
    assert not calls
    assert online == again == offline
    assert "impostor-pkg" in {e.get("name") for e in json.loads(online)["@graph"]}


def test_a_package_one_extra_declares_by_url_gets_no_pypi_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: Calls
) -> None:
    """``impostor-pkg>=1`` in an extra and the direct reference collapse into
    one package: it comes from the URL, so PyPI's record is not used."""
    isolate(tmp_path, monkeypatch)
    text = _pyproject([_URL]) + (
        '[project.optional-dependencies]\nx = ["impostor-pkg>=1"]\n'
    )
    sbom = _library({"pyproject.toml": text})(tmp_path)
    assert ("impostor-pkg", None) in calls  # the registry spelling's prefetch
    assert _pypi_facts(sbom, "impostor-pkg") == []
    packages = [
        e for e in json.loads(sbom)["@graph"] if e.get("name") == "impostor-pkg"
    ]
    assert len(packages) == 1


def test_add_dependencies_prefetches_no_direct_reference(calls: Calls) -> None:
    """Called without a prefetched cache, it fetches only the registry
    dependency."""
    doc_uuid = compute_doc_uuid("demo", "1.0", [], None)
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    add_dependencies(
        [_URL, _PLAIN],
        "Source: pyproject.toml",
        "https://example.com/demo/Package-1",
        _make_ci(),
        "demo",
        doc_uuid,
        exporter,
    )
    assert calls == [("plain-pkg", "1.0")]
