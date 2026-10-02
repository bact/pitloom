# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for :mod:`tests.id_registry.test_package_ids` and
:mod:`tests.id_registry.test_package_ids_ambiguous`: reading a registry's or an
SBOM's ``software_Package`` ids, and building a document directly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3.document import build
from pitloom.core.creation import CreationMetadata
from pitloom.core.document import DocumentModel
from pitloom.core.project import PhantomDependency, ProjectMetadata
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id
from pitloom.id_registry import PACKAGE_ENTITY_TYPE, IdRegistry
from tests.conftest import _assert_no_duplicate_spdx_ids

MAIN = "demo"


class Package(NamedTuple):
    """One emitted ``software_Package``: name, version and spdxId."""

    name: str
    version: str
    spdx_id: str


def package_entries(registry_path: Path) -> dict[str, str]:
    """The registry's ``software_Package`` entries, name -> spdxId."""
    registry = IdRegistry.load(registry_path)
    return {
        name: entry.spdx_id
        for (type_name, name), entry in sorted(registry.entities.items())
        if type_name == PACKAGE_ENTITY_TYPE
    }


def sbom_package_ids(sbom_json: str) -> dict[str, str]:
    """Name -> spdxId of each ``software_Package`` (last one wins on a
    repeated name -- use :func:`sbom_packages` for those)."""
    return {
        node["name"]: node["spdxId"]
        for node in json.loads(sbom_json)["@graph"]
        if node.get("type") == "software_Package"
    }


def sbom_packages(sbom_json: str) -> list[Package]:
    """Every ``software_Package`` of *sbom_json*, sorted."""
    return sorted(
        Package(
            node["name"],
            node.get("software_packageVersion", ""),
            node["spdxId"],
        )
        for node in json.loads(sbom_json)["@graph"]
        if node.get("type") == "software_Package"
    )


def root_element_id(sbom_json: str) -> str:
    """The id of the SBOM's single root element."""
    graph = json.loads(sbom_json)["@graph"]
    (root,) = next(n for n in graph if n["type"] == "software_Sbom")["rootElement"]
    return str(root)


def new_registry(
    tmp_path: Path, pins: Sequence[str] = (), project_name: str = "pins"
) -> tuple[Path, list[str]]:
    """Save a registry (namespace derived from *project_name*) pinning each
    of *pins* as a ``software_Package``."""
    registry = IdRegistry.new(project_name)
    ids = [registry.register_entity(name, PACKAGE_ENTITY_TYPE) for name in pins]
    path = tmp_path / "registry.json"
    registry.save(path)
    return path, ids


def make_doc(
    *,
    name: str = MAIN,
    dependencies: Sequence[str] = (),
    locked: Sequence[str] = (),
    # pylint: disable-next=redefined-outer-name
    phantom: Sequence[PhantomDependency] = (),
) -> DocumentModel:
    return DocumentModel(
        project=ProjectMetadata(
            name=name,
            version="1.0.0",
            dependencies=list(dependencies),
            locked_dependencies=list(locked),
        ),
        creation_metadata=CreationMetadata(
            creation_datetime="2026-01-01T00:00:00+00:00"
        ),
        phantom_dependencies=list(phantom),
    )


def build_doc(doc: DocumentModel, registry: IdRegistry | None) -> Spdx3JsonExporter:
    exporter = build(doc, registry=registry, offline=True)
    _assert_no_duplicate_spdx_ids(exporter=exporter)
    return exporter


def packages(exporter: Spdx3JsonExporter) -> list[Package]:
    return sorted(
        Package(obj.name or "", obj.software_packageVersion or "", require_spdx_id(obj))
        for obj in exporter.object_set.objects
        if isinstance(obj, spdx3.software_Package)
    )


def claim_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and "ID registry:" in r.getMessage()
    ]


def phantom(name: str, version: str | None = None) -> PhantomDependency:
    return PhantomDependency(
        name=name, file_path=f"libs/{name}.so", digest_sha256="c" * 64, version=version
    )


def wheel_with_libs(
    directory: Path, requires_dist: Sequence[str], libs: Sequence[str]
) -> Path:
    """A ``demo`` wheel declaring *requires_dist* and bundling one shared
    library file per stem of *libs* under ``demo.libs/`` -- Pitloom reads
    each as a phantom dependency."""
    directory.mkdir(parents=True, exist_ok=True)
    dist_info = f"{MAIN}-1.0.0.dist-info"
    content: dict[str, bytes] = {f"{MAIN}/__init__.py": b"__version__ = '1.0.0'\n"}
    for lib in libs:
        content[f"{MAIN}.libs/{lib}.so"] = b"\x7fELF" + lib.encode()
    content[f"{dist_info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {MAIN}\nVersion: 1.0.0\n"
        + "".join(f"Requires-Dist: {req}\n" for req in requires_dist)
    ).encode()
    content[f"{dist_info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    records = [
        f"{arcname},sha256="
        + base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
        .decode("ascii")
        .rstrip("=")
        + f",{len(payload)}"
        for arcname, payload in content.items()
    ]
    content[f"{dist_info}/RECORD"] = (
        "\n".join([*records, f"{dist_info}/RECORD,,"]) + "\n"
    ).encode()
    wheel_path = directory / f"{MAIN}-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for arcname in sorted(content):
            zf.writestr(
                zipfile.ZipInfo(arcname, (2020, 1, 1, 0, 0, 0)), content[arcname]
            )
    return wheel_path


def project_with_dependencies(root: Path, dependencies: Sequence[str]) -> Path:
    """A ``demo`` project directory declaring *dependencies*."""
    (root / MAIN).mkdir(parents=True, exist_ok=True)
    (root / MAIN / "__init__.py").write_bytes(b"__version__ = '1.0.0'\n")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
        f'[project]\nname = "{MAIN}"\nversion = "1.0.0"\n'
        f"dependencies = {json.dumps(list(dependencies))}\n",
        encoding="utf-8",
    )
    return root
