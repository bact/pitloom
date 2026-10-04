# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Blank space around a licence text (leading blank lines, spaces and tabs,
final line breaks) is serialisation: whatever it is,
every surface records one ``licenseText``, from the project's own file
through Hatchling's ``METADATA`` to a dependency's PyPI record.

See also: :mod:`tests.assemble.test_license_elements_classifier` (the text
kept as written) and :mod:`tests.assemble.test_license_elements_surfaces`.
"""

from __future__ import annotations

import email
import json
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any
from unittest.mock import patch

import hatchling.metadata.core as hatchling_metadata_core
import pytest
from hatchling.metadata.spec import get_core_metadata_constructors
from hatchling.plugin.manager import PluginManager
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import deps_installed, deps_pypi
from pitloom.assemble.spdx3.deps import add_dependencies
from pitloom.assemble.spdx3.document import build, build_deployed, build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid
from pitloom.core.project import ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.extract.project.hatchling import metadata_from_hatchling
from pitloom.extract.project.installed import _parse_installed_metadata
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import _populate_metadata_from_email
from tests._license_graph import graph_of

from .conftest import _FakeMetadata, _make_ci, _make_sdist

_TEXT = "Acme Licence\n  No use."  # an inner indent is text
#: The same text as a file may hold it: leading blank space and final line
#: breaks around it.
_AS_WRITTEN = [
    *(_TEXT + ending for ending in ("", "\n", "\n\n", "\r\n", "\r\n\r\n", "\r")),
    "   " + _TEXT,
    "\n\n  " + _TEXT + "\n",
    "\t" + _TEXT,
]


def _project_dir(tmp: Path, written: str) -> Path:
    """A project whose ``license = {file = ...}`` holds the text with
    *written*, byte for byte."""
    (tmp / "COPYING.txt").write_bytes(written.encode())
    (tmp / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0"\nlicense = {file = "COPYING.txt"}\n',
        encoding="utf-8",
    )
    (tmp / "demo").mkdir()
    (tmp / "demo" / "__init__.py").write_text("", encoding="utf-8")
    return tmp


def _core(tmp: Path) -> Any:
    return hatchling_metadata_core.ProjectMetadata(str(tmp), PluginManager())


def _metadata_file(tmp: Path) -> str:
    """The ``METADATA`` Hatchling writes for the project."""
    text: str = get_core_metadata_constructors()["2.4"](_core(tmp))
    return text


def _built(metadata: ProjectMetadata) -> list[dict[str, Any]]:
    metadata.version = metadata.version or "1.0"
    return graph_of(
        build(DocumentModel(project=metadata, creation_metadata=CreationMetadata()))
    )


def _directory(tmp: Path) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(generate_project_sbom(tmp, offline=True))[
        "@graph"
    ]
    return graph


def _hook(tmp: Path) -> list[dict[str, Any]]:
    return _built(metadata_from_hatchling(_core(tmp), tmp))


def _wheel(tmp: Path) -> list[dict[str, Any]]:
    metadata = ProjectMetadata(name="demo")
    _populate_metadata_from_email(
        metadata,
        metadata.provenance,
        email.message_from_string(_metadata_file(tmp)),
        "Source: wheel METADATA",
    )
    return _built(metadata)


def _sdist(tmp: Path) -> list[dict[str, Any]]:
    out = tmp / "out"
    out.mkdir()
    sdist = _make_sdist(out, members={"PKG-INFO": _metadata_file(tmp).encode()})
    return _built(read_sdist(sdist, read_config=False).metadata)


def _installed(tmp: Path) -> list[dict[str, Any]]:
    msg = email.message_from_string(_metadata_file(tmp))
    return _built(_parse_installed_metadata(msg, "Source: demo.dist-info"))


def _installed_value(tmp: Path) -> str:
    """The ``License`` value an installed copy's metadata gives, folded."""
    value = email.message_from_string(_metadata_file(tmp))["License"]
    return str(value)


def _env_package(tmp: Path) -> list[dict[str, Any]]:
    doc = DocumentModel(
        project=ProjectMetadata(name="env", version="0.0.0"),
        creation_metadata=CreationMetadata(),
    )
    tree = [{"package": {"key": "x", "package_name": "x", "installed_version": "1"}}]
    fake = _FakeMetadata({"Version": "1", "License": _installed_value(tmp)})
    with patch.object(deps_installed, "get_pkg_metadata", lambda _name: fake):
        return graph_of(build_deployed(doc, tree, offline=True))


def _uninstalled(*_args: object) -> None:
    raise PackageNotFoundError


def _dependency(tmp: Path, *, pypi: bool) -> list[dict[str, Any]]:
    """A dependency's installed copy (its folded METADATA value) or, not
    installed, its PyPI record (the text as uploaded)."""
    doc_uuid = compute_doc_uuid("breaks", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    exporter.add_creation_info(ci)
    main = spdx3.software_Package(
        spdxId="https://x/1#Package-1", name="main", creationInfo=ci
    )
    exporter.add_package(main)
    fake = _FakeMetadata({"Version": "1.0", "License": _installed_value(tmp)})
    raw = (tmp / "COPYING.txt").read_bytes().decode()
    with (
        patch.object(
            deps_installed,
            "get_pkg_metadata",
            _uninstalled if pypi else lambda _n: fake,
        ),
        patch.object(
            deps_installed,
            "get_package_version",
            _uninstalled if pypi else lambda _n: "1.0",
        ),
        patch.object(
            deps_pypi,
            "_fetch_pypi_release_info",
            lambda *_a: {"info": {"license": raw}},
        ),
    ):
        add_dependencies(
            ["dep==1.0"],
            "Source: pyproject.toml | Field: project.dependencies",
            require_spdx_id(main),
            ci,
            "breaks",
            doc_uuid,
            exporter,
            offline=not pypi,
        )
    return graph_of(exporter)


def _ai_model(tmp: Path) -> list[dict[str, Any]]:
    """An AI model's own metadata stating the text as read."""
    model = AiModelMetadata(
        format_info=AiModelFormatInfo(model_format=AiModelFormat.ONNX),
        name="m",
        license=(tmp / "COPYING.txt").read_bytes().decode(),
    )
    return graph_of(build_model(model, CreationMetadata()))


_SURFACES: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
    "directory": _directory,
    "hook": _hook,
    "wheel": _wheel,
    "sdist": _sdist,
    "installed-project": _installed,
    "env-package": _env_package,
    "dependency-installed": lambda tmp: _dependency(tmp, pypi=False),
    "dependency-pypi": lambda tmp: _dependency(tmp, pypi=True),
    "ai-model": _ai_model,
}


@pytest.mark.parametrize("surface", list(_SURFACES))
@pytest.mark.parametrize("written", _AS_WRITTEN, ids=repr)
def test_blank_space_around_a_text_gives_one_text_on_every_surface(
    surface: str, written: str, tmp_path: Path
) -> None:
    graph = _SURFACES[surface](_project_dir(tmp_path, written))
    texts = [
        e["simplelicensing_licenseText"]
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
    ]
    assert texts == [_TEXT]
