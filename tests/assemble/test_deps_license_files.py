# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.assemble.spdx3._deps_license_files: an installed
dependency's licence files, and the licence they name when its Core
Metadata names none.

See also: test_deps_enrichment_originator_license.py (the same files read
for copyright notices) and test_license_detection_corpus.py (the licence
texts used here).
"""

from __future__ import annotations

import functools
import json
import logging
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any

import pytest
from licenseid import LicenseDetector
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _deps_license_files as files_mod
from pitloom.assemble.spdx3 import deps_installed
from pitloom.assemble.spdx3._deps_license_files import (
    dist_license_files,
    license_from_dist_files,
    with_dist_license_files,
)
from pitloom.assemble.spdx3.deps import _enrich_from_installed
from pitloom.assemble.spdx3.provenance import (
    DEPLOYED_PACKAGE_SOURCE,
    INSTALLED_DEPENDENCY_SOURCE,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract import _license_text_match
from pitloom.logging_config import CODE_ATTR

from .conftest import _FakeDistribution, _FakeMetadata, _FakePackagePath, _make_ci

# Installed-file paths, licence-file reads and the database's home directory
# are the operating system's.
pytestmark = pytest.mark.platform

_TEXTS = Path(__file__).resolve().parent.parent / "fixtures" / "license-texts"
_MIT = (_TEXTS / "attrs-26.1.0-LICENSE").read_text(encoding="utf-8")
_LGPL3 = (_TEXTS / "fickling-0.1.13-LICENSE").read_text(encoding="utf-8")
_SEVERAL = (_TEXTS / "numpy-2.5.5-LICENSE").read_text(encoding="utf-8")
_DI = "dep-1.0.dist-info"
_APACHE_CLASSIFIER = "License :: OSI Approved :: Apache Software License"
_BSD_CLASSIFIER = "License :: OSI Approved :: BSD License"
_LGPL3_PLUS = (
    "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)"
)


def _dist(root: Path, files: dict[str, str]) -> _FakeDistribution:
    return _FakeDistribution(
        root, [_FakePackagePath(root, path, text) for path, text in files.items()]
    )


@pytest.mark.parametrize(
    ("files", "license_files", "expected"),
    [
        # PEP 639: under licenses/, by its exact path, nested too.
        (
            [f"{_DI}/licenses/LICENSE", f"{_DI}/licenses/sub/COPYING"],
            ["sub/COPYING", "LICENSE"],
            [f"{_DI}/licenses/sub/COPYING", f"{_DI}/licenses/LICENSE"],
        ),
        # Older back-ends: at the dist-info root.
        ([f"{_DI}/LICENSE.txt"], ["LICENSE.txt"], [f"{_DI}/LICENSE.txt"]),
        # A same-named file elsewhere is not the listed one.
        (
            ["dep/vendor/LICENSE", f"{_DI}/licenses/x/LICENSE"],
            ["LICENSE"],
            [],
        ),
        # Listed twice, or missing: once, or not at all.
        (
            [f"{_DI}/licenses/LICENSE"],
            ["LICENSE", "LICENSE", "NOPE"],
            [f"{_DI}/licenses/LICENSE"],
        ),
        # No header: the dist-info root's licence files, by name.
        (
            [f"{_DI}/METADATA", f"{_DI}/COPYING", f"{_DI}/LICENSE", f"{_DI}/x/LICENSE"],
            [],
            [f"{_DI}/LICENSE", f"{_DI}/COPYING"],
        ),
        (["dep/__init__.py"], [], []),
        # Listed and at both places: under licenses/ first.
        (
            [f"{_DI}/LICENSE", f"{_DI}/licenses/LICENSE"],
            ["LICENSE"],
            [f"{_DI}/licenses/LICENSE"],
        ),
        # Two .dist-info trees in RECORD: the first by name.
        (
            ["z-1.dist-info/LICENSE", "a-1.dist-info/LICENSE"],
            [],
            ["a-1.dist-info/LICENSE"],
        ),
    ],
    ids=[
        "pep639",
        "root",
        "not-basename",
        "once",
        "unlisted",
        "no-dist-info",
        "licenses-first",
        "two-dist-info",
    ],
)
def test_dist_license_files(
    tmp_path: Path, files: list[str], license_files: list[str], expected: list[str]
) -> None:
    dist = _dist(tmp_path, dict.fromkeys(files, "x"))
    assert [str(p) for p in dist_license_files(dist, license_files)] == expected


def test_no_record_lists_no_file(tmp_path: Path) -> None:
    """A distribution without ``RECORD`` (``files`` is ``None``) lists
    none."""
    assert not dist_license_files(_FakeDistribution(tmp_path, None), ["LICENSE"])


class _NulPackagePath:
    """A ``RECORD`` entry holding a NUL: no file can have its name."""

    def __init__(self, root: Path, path: str):
        self._path, self._root = path, root

    def __str__(self) -> str:
        return self._path

    def locate(self) -> Path:
        return self._root / self._path


def test_a_nul_in_license_file_names_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``License-File`` value holding a NUL names no file, even when a
    ``RECORD`` entry spells it: not read (``os.stat`` would raise
    ``ValueError``)."""
    value = "LIC\x00ENSE"
    entry = _NulPackagePath(tmp_path, f"{_DI}/licenses/{value}")
    dist = _FakeDistribution(tmp_path, [entry])  # type: ignore[list-item]
    assert not dist_license_files(dist, [value])
    _patch_dist(monkeypatch, dist)
    meta = _FakeMetadata({}, license_files=[value])
    assert license_from_dist_files("dep", meta, None, "s") is None


def _patch_dist(monkeypatch: pytest.MonkeyPatch, dist: Any) -> list[str]:
    asked: list[str] = []

    def fake(name: str) -> Any:
        asked.append(name)
        return dist

    monkeypatch.setattr(files_mod, "get_pkg_distribution", fake)
    return asked


@pytest.mark.usefixtures("licenseid_db_path")
@pytest.mark.parametrize(
    ("stated", "classifiers", "files", "expected"),
    [
        # A classifier's own name, no version: the file says which.
        (
            "Apache Software License",
            [_APACHE_CLASSIFIER],
            {f"{_DI}/licenses/LICENSE": _MIT},
            "MIT",
        ),
        (None, [], {f"{_DI}/LICENSE": _MIT}, "MIT"),
        ("", [], {f"{_DI}/LICENSE": _MIT}, "MIT"),
        ("UNKNOWN", [], {f"{_DI}/LICENSE": _MIT}, "MIT"),
        # Several licences (python-dateutil): no file narrows them to one.
        (
            "Dual License",
            [_BSD_CLASSIFIER, _APACHE_CLASSIFIER],
            {f"{_DI}/LICENSE": _MIT},
            None,
        ),
        # A verbatim LGPL 3 text: the LGPLv3+ classifier wins the tie.
        (_LGPL3, [_LGPL3_PLUS], {f"{_DI}/LICENSE": _LGPL3}, "LGPL-3.0-or-later"),
        (None, [], {f"{_DI}/LICENSE": _LGPL3}, "LGPL-3.0-only"),
        # A file of several licence texts first ends the search.
        (
            None,
            [],
            {f"{_DI}/LICENSE": _SEVERAL, f"{_DI}/COPYING": _MIT},
            None,
        ),
        (None, [], {f"{_DI}/LICENSE": "not a licence"}, None),
        (None, [], {}, None),
    ],
    ids=[
        "classifier-name",
        "absent",
        "blank",
        "unknown",
        "dual",
        "classifier-breaks-tie",
        "tie-unstated",
        "several-texts",
        "no-match",
        "no-file",
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_license_from_dist_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stated: str | None,
    classifiers: list[str],
    files: dict[str, str],
    expected: str | None,
) -> None:
    _patch_dist(monkeypatch, _dist(tmp_path, files))
    # A file under licenses/ is listed, as PEP 639 writes it.
    listed = [p.split("/licenses/", 1)[1] for p in files if "/licenses/" in p]
    meta = _FakeMetadata({}, license_files=listed, classifiers=classifiers)
    found = license_from_dist_files("dep", meta, stated, "Source: s | Package: dep")
    assert (found and found[0]) == expected
    if found:
        path = next(iter(files))
        assert found[1].startswith(
            f"Source: s | Package: dep | File: {path} | Method: licenseid_detection"
        )


@pytest.mark.parametrize(
    ("stated", "g2"),
    [
        ("Apache Software License", True),
        (None, False),
        ("", False),
        ("  ", False),
        ("UNKNOWN", False),
        ("NOASSERTION", False),
    ],
    ids=["text", "absent", "empty", "blank", "unknown", "noassertion"],
)
def test_stated_text_keeps_its_place(
    monkeypatch: pytest.MonkeyPatch, stated: str | None, g2: bool
) -> None:
    """Stated text stays the declared licence, the files' the concluded
    one (G2); a placeholder or nothing gives way to the files' licence."""
    monkeypatch.setattr(
        files_mod, "license_from_dist_files", lambda *_: ("MIT", "from-file")
    )
    found = with_dist_license_files("dep", _FakeMetadata({}), (stated, "meta"), "s")
    if g2:
        assert found == (stated, "meta", ("MIT", "from-file"))
    else:
        assert found == ("MIT", "from-file", (None, None))


def test_no_file_licence_keeps_the_stated_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(files_mod, "license_from_dist_files", lambda *_: None)
    found = with_dist_license_files("dep", _FakeMetadata({}), ("x y", "meta"), "s")
    assert found == ("x y", "meta", (None, None))


@pytest.mark.parametrize("stated", ["MIT", "Apache-2.0 OR MIT", "NONE"])
def test_a_named_licence_reads_no_file(
    monkeypatch: pytest.MonkeyPatch, stated: str
) -> None:
    """Metadata that names a licence, or states none, is the answer."""
    asked = _patch_dist(monkeypatch, None)
    assert license_from_dist_files("dep", _FakeMetadata({}), stated, "s") is None
    assert not asked


def test_a_missing_distribution_gives_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> Any:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(files_mod, "get_pkg_distribution", missing)
    assert license_from_dist_files("dep", _FakeMetadata({}), None, "s") is None


def _licence_of(element: dict[str, Any]) -> str:
    return str(
        element.get("simplelicensing_licenseExpression")
        or element.get("simplelicensing_licenseText")
    )


@pytest.mark.usefixtures("licenseid_db_path")
@pytest.mark.parametrize(
    "source", [INSTALLED_DEPENDENCY_SOURCE, DEPLOYED_PACKAGE_SOURCE]
)
@pytest.mark.parametrize(
    ("fields", "classifiers", "expected", "conflicts"),
    [
        # Stated text is the declared licence, the file's the concluded one
        # (G2), as for a project's own; they differ, so a conflict is noted.
        (
            {},
            [_APACHE_CLASSIFIER],
            {
                "hasDeclaredLicense": "Apache Software License",
                "hasConcludedLicense": "MIT",
            },
            1,
        ),
        # Nothing stated: the file's licence, declared or concluded by its
        # source (single mode).
        ({}, [], {"single": "MIT"}, 0),
        # python-dateutil: a dual licence the file would narrow, not read.
        (
            {"License": "Dual License"},
            [_BSD_CLASSIFIER, _APACHE_CLASSIFIER],
            {"single": "Dual License"},
            0,
        ),
    ],
    ids=["stated-text", "unstated", "dual"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments,too-many-locals
def test_dependency_licence_from_its_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    fields: dict[str, str],
    classifiers: list[str],
    expected: dict[str, str],
    conflicts: int,
) -> None:
    """A dependency's licence file is read on the project and the
    environment route alike, with the file in provenance: beside stated
    text (the classifier name ``Apache Software License``) as the concluded
    second opinion, else as the licence."""
    monkeypatch.setattr(
        deps_installed,
        "get_pkg_metadata",
        lambda name: _FakeMetadata(
            {"Version": "1.0", **fields}, classifiers=classifiers
        ),
    )
    _patch_dist(monkeypatch, _dist(tmp_path, {f"{_DI}/LICENSE": _MIT}))
    doc_uuid = compute_doc_uuid("demo", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="demo", doc_uuid=doc_uuid),
        name="dep",
        creationInfo=ci,
    )
    dep.software_packageVersion = "1.0"
    exporter.add_package(dep)
    filled = _enrich_from_installed(
        "dep", dep, ci, "demo", doc_uuid, exporter, installed_source=source
    )
    assert "license" in filled
    graph = json.loads(exporter.to_json(pretty=False))["@graph"]
    by_id = {e.get("spdxId"): e for e in graph}
    custom = {
        d["key"]: d["value"]
        for e in graph
        for d in e.get("simplelicensing_customIdToUri", ())
    }

    def licence(ref: str) -> str:
        value = _licence_of(by_id[ref])
        return _licence_of(by_id[custom[value]]) if value in custom else value

    found = {
        e["relationshipType"]: licence(e["to"][0])
        for e in graph
        if e.get("type") == "Relationship" and e["relationshipType"].endswith("License")
    }
    if "single" in expected:
        single = (
            "hasDeclaredLicense"
            if source == DEPLOYED_PACKAGE_SOURCE
            else "hasConcludedLicense"
        )
        expected = {single: expected["single"]}
    assert found == expected
    assert (f"File: {_DI}/LICENSE" in json.dumps(graph)) == ("MIT" in found.values())
    assert json.dumps(graph).count('\\"kind\\":\\"conflict\\"') == conflicts


@pytest.mark.parametrize(
    ("stated", "classifiers", "level"),
    [
        (None, [_LGPL3_PLUS], logging.INFO),
        ("Apache Software License", [_APACHE_CLASSIFIER], logging.WARNING),
        (None, [], logging.WARNING),
    ],
    ids=["classifier-id", "classifier-name", "nothing"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_a_missing_database_is_said_as_for_a_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    stated: str | None,
    classifiers: list[str],
    level: int,
) -> None:
    """With no database the file gives no licence, said as for a project
    (``license-db-missing``): ``INFO:`` when a classifier names an SPDX
    licence, so only the file's reading is lost; else ``WARNING:``."""
    _patch_dist(monkeypatch, _dist(tmp_path, {f"{_DI}/LICENSE": _MIT}))
    real = functools.partial(LicenseDetector, db_path=str(tmp_path / "none.db"))
    monkeypatch.setattr(_license_text_match, "LicenseDetector", real)
    meta = _FakeMetadata({}, classifiers=classifiers)
    with caplog.at_level(logging.INFO):
        assert license_from_dist_files("dep", meta, stated, "s") is None
    assert [(r.levelno, getattr(r, CODE_ATTR, None)) for r in caplog.records] == [
        (level, "license-db-missing")
    ]
