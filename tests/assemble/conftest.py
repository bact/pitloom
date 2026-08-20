# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Shared test helpers for tests/assemble/.

Consolidates fixtures/helpers that were duplicated (or would become
duplicated by splitting oversized test files) across multiple modules in
this directory:

- ``_FakeMetadata`` -- from ``test_deps_enrichment.py``.
- ``_make_dummy_wheel`` / ``_SAMPLE_SPDX3_JSON`` -- from ``test_embed.py``.
- ``_DOC_NAME`` / ``_DOC_UUID`` / ``_make_ci`` -- previously byte-for-byte
  duplicated (bar one comment) between ``test_annotation_provenance.py``
  and ``test_spdx3_dataset.py``.
- ``_make_subject`` -- from ``test_annotation_provenance.py``.
- ``_make_meta`` -- from ``test_spdx3_dataset.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.core.dataset_metadata import DatasetMetadata
from pitloom.core.models import compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter, require_spdx_id

_DOC_NAME = "testproject"
_DOC_UUID = compute_doc_uuid("testproject", "1.0", [])


def _make_ci() -> spdx3.CreationInfo:
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    # createdBy is required for serialisation; use a dummy spdxId.
    person = spdx3.Person(
        spdxId=generate_spdx_id("Person", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="Test",
        creationInfo=ci,
    )
    ci.createdBy = [require_spdx_id(person)]
    return ci


def _make_subject(
    exporter: Spdx3JsonExporter, ci: spdx3.CreationInfo
) -> spdx3.software_Package:
    pkg = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name=_DOC_NAME, doc_uuid=_DOC_UUID),
        name="dep",
        creationInfo=ci,
    )
    exporter.add_package(pkg)
    return pkg


def _make_meta(**kwargs) -> DatasetMetadata:  # type: ignore[no-untyped-def]
    return DatasetMetadata(name="Test Dataset", **kwargs)


class _FakeMetadata:
    """Minimal stand-in satisfying the ``importlib.metadata.PackageMetadata``
    protocol. ``__getitem__`` returns ``None`` for a missing key at runtime
    (matching the real, ``email.message.Message``-backed implementation,
    which the ``-> str`` protocol signature doesn't accurately capture
    either) -- callers here always guard with ``pkg_meta[field] or ""``,
    same as production code.
    """

    def __init__(
        self,
        fields: dict[str, str],
        project_urls: list[str] | None = None,
        license_files: list[str] | None = None,
    ):
        self._fields = fields
        self._project_urls = project_urls or []
        self._license_files = license_files or []

    def __len__(self) -> int:
        return len(self._fields)

    def __contains__(self, item: str) -> bool:
        return item in self._fields

    def __getitem__(self, key: str) -> str:
        return cast(str, self._fields.get(key))

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def get_all(self, name: str, failobj: Any = None) -> Any:
        if name == "Project-URL":
            return self._project_urls
        if name == "License-File":
            return self._license_files
        return failobj

    @property
    def json(self) -> dict[str, Any]:
        return dict(self._fields)


_SAMPLE_SPDX3_JSON = json.dumps(
    {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {
                "type": "SpdxDocument",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123",
                "name": "sample",
                "specVersion": "3.0.1",
                "profileConformance": ["core", "software"],
                "creationInfo": "_:creationInfo1",
                "rootElement": ["https://spdx.org/spdxdocs/sample-doc-123/package"],
            },
            {
                "type": "CreationInfo",
                "@id": "_:creationInfo1",
                "specVersion": "3.0.1",
                "createdBy": ["https://spdx.org/spdxdocs/sample-doc-123/agent"],
                "created": "2026-08-14T00:00:00Z",
            },
            {
                "type": "software_Package",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/package",
                "name": "demo_pkg",
                "software_packageVersion": "1.0.0",
                "software_packageUrl": "pkg:pypi/demo-pkg@1.0.0",
            },
            {
                "type": "SoftwareAgent",
                "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/agent",
                "name": "Pitloom",
            },
        ],
    }
)


def _make_dummy_wheel(
    directory: Path,
    name: str = "demo_pkg",
    version: str = "1.0.0",
) -> Path:
    """Create a minimal valid wheel with a valid RECORD file."""
    directory.mkdir(parents=True, exist_ok=True)
    wheel_filename = f"{name}-{version}-py3-none-any.whl"
    wheel_path = directory / wheel_filename
    dist_info = f"{name}-{version}.dist-info"

    init_code = b"__version__ = '1.0.0'\n"
    metadata_content = (
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    ).encode()
    wheel_content = (
        b"Wheel-Version: 1.0\n"
        b"Generator: test\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )

    def _rec_entry(arcname: str, payload: bytes) -> str:
        d = hashlib.sha256(payload).digest()
        h = base64.urlsafe_b64encode(d).decode("ascii").rstrip("=")
        return f"{arcname},sha256={h},{len(payload)}"

    records = [
        _rec_entry(f"{name}/__init__.py", init_code),
        _rec_entry(f"{dist_info}/METADATA", metadata_content),
        _rec_entry(f"{dist_info}/WHEEL", wheel_content),
        f"{dist_info}/RECORD,,",
    ]
    record_content = "\n".join(records).encode("utf-8") + b"\n"

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{name}/__init__.py", init_code)
        zf.writestr(f"{dist_info}/METADATA", metadata_content)
        zf.writestr(f"{dist_info}/WHEEL", wheel_content)
        zf.writestr(f"{dist_info}/RECORD", record_content)

    return wheel_path
