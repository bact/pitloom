# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for dependency exact pin extraction and version resolution
(:mod:`pitloom.assemble.spdx3.deps_installed`).

See also: test_deps_enrichment_names_versions.py for display name and basic
version resolution tests; this file covers specifier operator nuances (==, ===,
wildcards, multi-specifiers) and installed metadata version mismatch isolation.
"""

from __future__ import annotations

import logging

import pytest
from packaging.requirements import Requirement
from spdx_python_model.bindings import v3_0_1 as spdx3

import pitloom.assemble.spdx3.deps_installed as deps_installed_mod
from pitloom.assemble.spdx3.deps_installed import (
    _enrich_from_installed,
    _extract_exact_pin,
    _resolve_version,
)
from pitloom.core.models import _clear_doc_counters, compute_doc_uuid, generate_spdx_id
from pitloom.export.spdx3_json import Spdx3JsonExporter

from .conftest import _FakeMetadata, _make_ci


def test_extract_exact_pin_accepts_single_exact_pins() -> None:
    req, pin = _extract_exact_pin("requests==2.31.0")
    assert isinstance(req, Requirement)
    assert pin == "2.31.0"

    req_arb, pin_arb = _extract_exact_pin("legacy-pkg===2021.01.01-legacy")
    assert isinstance(req_arb, Requirement)
    assert pin_arb == "2021.01.01-legacy"


def test_extract_exact_pin_rejects_wildcards_and_ranges() -> None:
    """A prefix wildcard (==1.*) or multi-clause specifier is a range,
    not an exact release pin."""
    req_wild, pin_wild = _extract_exact_pin("requests==1.*")
    assert isinstance(req_wild, Requirement)
    assert pin_wild is None

    req_multi, pin_multi = _extract_exact_pin("requests==1.*,>=1.0")
    assert isinstance(req_multi, Requirement)
    assert pin_multi is None

    req_two, pin_two = _extract_exact_pin("requests==1.0,<=2.0")
    assert isinstance(req_two, Requirement)
    assert pin_two is None

    req_range, pin_range = _extract_exact_pin("requests>=2.0")
    assert isinstance(req_range, Requirement)
    assert pin_range is None


def test_extract_exact_pin_unparseable_requirements() -> None:
    """Unparseable requirements fallback cleanly for == and === while rejecting
    wildcards and multiple clauses."""
    _, pin = _extract_exact_pin("unparseable-pkg==1.0; invalid @ marker")
    assert pin == "1.0"

    _, pin_arb = _extract_exact_pin(
        "unparseable-pkg===2021.01.01-legacy; invalid @ marker"
    )
    assert pin_arb == "2021.01.01-legacy"

    _, pin_wild = _extract_exact_pin("unparseable-pkg==1.*; invalid @ marker")
    assert pin_wild is None

    _, pin_multi = _extract_exact_pin("unparseable-pkg==1.0,<=2.0; invalid @ marker")
    assert pin_multi is None


def test_resolve_version_wildcard_prefix_defers_to_locked_version(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When a declared dependency uses a wildcard (pkg==1.*), it must not be
    treated as an exact pin; the locked version is authoritative and emitted."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests==1.*", locked_version="1.2.3"
        )

    assert version == "1.2.3"
    assert note == "Version resolved: Project lock file"
    assert "conflicts with declared exact pin" not in caplog.text


def test_resolve_version_pep440_equivalent_pins_emit_no_conflict_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Declared pkg==1.0 and locked 1.0.0 are PEP 440 equivalent and must not
    trigger a false-positive conflict warning."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests==1.0", locked_version="1.0.0"
        )

    assert version == "1.0"
    assert note is None
    assert "conflicts with declared exact pin" not in caplog.text


def test_resolve_version_pep440_different_pins_emit_conflict_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Declared pkg==1.0 and locked 2.0.0 genuinely conflict; declared pin wins
    with a warning."""
    with caplog.at_level(logging.WARNING):
        version, note = _resolve_version(
            "requests", "requests==1.0", locked_version="2.0.0"
        )

    assert version == "1.0"
    assert note is None
    assert "conflicts with declared exact pin '1.0'" in caplog.text


def test_resolve_version_arbitrary_equality_pins_matching_and_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Declared pkg===legacy-1 and locked legacy-1 match without warning;
    differing locked legacy-2 triggers conflict warning and uses declared pin."""
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        ver_match, note_match = _resolve_version(
            "legacy-pkg",
            "legacy-pkg===2021.01.01-legacy",
            locked_version="2021.01.01-legacy",
        )
    assert ver_match == "2021.01.01-legacy"
    assert note_match is None
    assert "conflicts with declared exact pin" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        ver_mismatch, note_mismatch = _resolve_version(
            "legacy-pkg",
            "legacy-pkg===2021.01.01-legacy",
            locked_version="2021.01.02-legacy",
        )
    assert ver_mismatch == "2021.01.01-legacy"
    assert note_mismatch is None
    assert "conflicts with declared exact pin '2021.01.01-legacy'" in caplog.text


def test_enrich_from_installed_skips_when_installed_version_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the host has another release installed (e.g. 2.28.0), but the expected
    version is 2.31.0, installed metadata must NOT be attached to the SBOM package."""
    fake_meta = _FakeMetadata(
        {
            "Version": "2.28.0",
            "Summary": "Host installed summary for 2.28.0",
            "Home-page": "https://host-installed.example.com",
            "License-Expression": "MIT",
        }
    )
    monkeypatch.setattr(deps_installed_mod, "get_pkg_metadata", lambda name: fake_meta)

    doc_uuid = compute_doc_uuid("mismatch-test", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="mismatch-test", doc_uuid=doc_uuid),
        name="requests",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "2.31.0"
    exporter.add_package(dep_package)

    filled = _enrich_from_installed(
        "requests",
        dep_package,
        ci,
        "mismatch-test",
        doc_uuid,
        exporter,
        expected_version="2.31.0",
    )

    assert filled == set()
    assert dep_package.description is None
    assert dep_package.software_homePage is None


def test_enrich_from_installed_accepts_matching_or_equivalent_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If installed version matches or is PEP 440 equivalent (e.g. 1.0.0 vs 1.0),
    installed metadata is safely used."""
    fake_meta = _FakeMetadata(
        {
            "Version": "1.0.0",
            "Summary": "Installed matching summary",
            "Home-page": "https://matching.example.com",
        }
    )
    monkeypatch.setattr(deps_installed_mod, "get_pkg_metadata", lambda name: fake_meta)

    doc_uuid = compute_doc_uuid("match-test", "1.0", [])
    _clear_doc_counters(doc_uuid)
    exporter = Spdx3JsonExporter()
    ci = _make_ci()
    dep_package = spdx3.software_Package(
        spdxId=generate_spdx_id("Package", doc_name="match-test", doc_uuid=doc_uuid),
        name="requests",
        creationInfo=ci,
    )
    dep_package.software_packageVersion = "1.0"
    exporter.add_package(dep_package)

    filled = _enrich_from_installed(
        "requests",
        dep_package,
        ci,
        "match-test",
        doc_uuid,
        exporter,
        expected_version="1.0",
    )

    assert "originator" in filled or "license" in filled or dep_package.description
    assert dep_package.description == "Installed matching summary"
    assert dep_package.software_homePage == "https://matching.example.com"
