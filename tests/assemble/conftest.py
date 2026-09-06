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
- ``_embed_sbom_entry`` -- previously near-identical ``_embed_sbom``/
  ``_embed_raw`` helpers in ``test_verify_wheel_cli.py`` and
  ``test_validate_wheel_cli.py``.
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
import os
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom._wheel_sbom_location import _find_dist_info_prefix
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
    """Minimal stand-in for the ``importlib.metadata.PackageMetadata``
    protocol. ``__contains__`` is real, so production code's
    ``pkg_meta_get()`` (see ``pitloom.extract._extract_utils``) works
    against it without hitting ``__getitem__``'s missing-key path."""

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


def _spdx3_json_with_subject(
    name: str | None, version: str | None, *, subject_type: str = "software_Package"
) -> str:
    """Render a minimal valid SPDX3 JSON-LD ``SpdxDocument`` ->
    ``software_Sbom`` -> subject-package id-chain, with a controllable
    subject *name*/*version* -- unlike `_SAMPLE_SPDX3_JSON`, which is
    hardcoded to ``demo_pkg``/``1.0.0``. Used by
    `test_verify_wheel_cli.py`'s name/version cross-check tests.

    *name*/*version* of ``None`` omit that field from the subject node
    entirely (e.g. to model an `ai_AIPackage`-shaped subject with no
    `software_packageVersion`).
    """
    subject: dict[str, Any] = {
        "type": subject_type,
        "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/subject",
    }
    if name is not None:
        subject["name"] = name
    if version is not None:
        subject["software_packageVersion"] = version
    return json.dumps(
        {
            "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
            "@graph": [
                {
                    "type": "SpdxDocument",
                    "spdxId": "https://spdx.org/spdxdocs/sample-doc-123",
                    "rootElement": ["https://spdx.org/spdxdocs/sample-doc-123/sbom"],
                },
                {
                    "type": "software_Sbom",
                    "spdxId": "https://spdx.org/spdxdocs/sample-doc-123/sbom",
                    "rootElement": [subject["spdxId"]],
                },
                subject,
            ],
        }
    )


def _embed_sbom_entry(
    wheel_path: Path, sbom_basename: str, content: str = _SAMPLE_SPDX3_JSON
) -> None:
    """Add a ``.dist-info/sboms/<sbom_basename>`` entry to *wheel_path*
    with arbitrary *content* (defaults to the standard sample fixture).

    Unlike `embed-wheel` itself (which always appends `.spdx3.json`), this
    writes whatever basename/content is given verbatim -- needed by
    `test_verify_wheel_cli.py`/`test_validate_wheel_cli.py` to construct
    deliberately non-conventional-extension or invalid-content fixtures
    that `embed-wheel`'s own self-correction makes otherwise unreachable.

    Reuses production's own `_find_dist_info_prefix` (rather than a
    second, test-only dist-info-detection algorithm) so this fixture
    can't silently diverge from what `find_embedded_sbom` actually looks
    for -- a single append-mode ZipFile handle can both read the
    existing namelist and write the new entry.
    """
    with zipfile.ZipFile(wheel_path, "a") as zf:
        dist_info = _find_dist_info_prefix(zf, wheel_path)
        zf.writestr(f"{dist_info}sboms/{sbom_basename}", content)


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
    fixed_time = (2026, 1, 1, 0, 0, 0)
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if raw_epoch:
        try:
            ts = int(raw_epoch)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            if dt.year >= 1980:
                fixed_time = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
        except (ValueError, OverflowError):
            pass

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, payload in (
            (f"{name}/__init__.py", init_code),
            (f"{dist_info}/METADATA", metadata_content),
            (f"{dist_info}/WHEEL", wheel_content),
            (f"{dist_info}/RECORD", record_content),
        ):
            zinfo = zipfile.ZipInfo(arcname, date_time=fixed_time)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o600 << 16
            zf.writestr(zinfo, payload)

    return wheel_path
