# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for src/pitloom/_sbom_format.py."""

from __future__ import annotations

import json

from pitloom._sbom_format import (
    RECOMMENDED_EXTENSIONS,
    VALIDATED_FORMATS,
    check_spdx3_name_version,
    compare_name_version,
    detect_sbom_format,
    extract_spdx3_subject_identity,
    format_name_version_mismatch,
)

_TWO_HOP = {
    "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
    "@graph": [
        {"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["sbom"]},
        {"type": "software_Sbom", "spdxId": "sbom", "rootElement": ["pkg"]},
        {
            "type": "software_Package",
            "spdxId": "pkg",
            "name": "pkg-name",
            "software_packageVersion": "1.2.3",
        },
    ],
}

_ONE_HOP_AI_PACKAGE = {
    "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
    "@graph": [
        {"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["pkg"]},
        {"type": "ai_AIPackage", "spdxId": "pkg", "name": "ai-model"},
    ],
}


def test_validated_formats_is_subset_of_recommended_extensions() -> None:
    """Every format with a registered validator must also have a
    recommended-extension entry -- a validator for a format Pitloom can't
    even name a canonical extension for would be a contradiction.

    Deliberately NOT the reverse: `RECOMMENDED_EXTENSIONS` is allowed to
    know about a format `VALIDATED_FORMATS` doesn't support yet (see the
    reference table in _sbom_format.py) -- that's the whole reason the two
    are kept as independent literals instead of one derived from the
    other.

    The subset check alone is vacuous -- true even for an emptied
    VALIDATED_FORMATS -- so it's paired with a non-empty, specific
    membership check that would fail if the set were ever accidentally
    cleared or derived down to nothing.
    """
    assert VALIDATED_FORMATS <= RECOMMENDED_EXTENSIONS.keys()
    assert "spdx3-jsonld" in VALIDATED_FORMATS


def test_detect_sbom_format_unrecognized_returns_none() -> None:
    assert detect_sbom_format(b"not json at all") is None
    assert detect_sbom_format(b'{"no_context_or_graph": true}') is None


def test_detect_sbom_format_recognizes_spdx3_jsonld() -> None:
    assert detect_sbom_format(b'{"@context": "x", "@graph": []}') == "spdx3-jsonld"


# --- extract_spdx3_subject_identity ---------------------------------------


def test_extract_subject_identity_unparseable_json_returns_none() -> None:
    assert extract_spdx3_subject_identity(b"not json at all") is None


def test_extract_subject_identity_no_graph_returns_none() -> None:
    assert extract_spdx3_subject_identity(b'{"@context": "x"}') is None


def test_extract_subject_identity_two_hop_chain() -> None:
    identity = extract_spdx3_subject_identity(json.dumps(_TWO_HOP).encode())
    assert identity is not None
    assert identity.error is None
    assert identity.name == "pkg-name"
    assert identity.version == "1.2.3"


def test_extract_subject_identity_single_hop_direct_subject() -> None:
    """A third-party SBOM whose SpdxDocument.rootElement points straight
    at the subject, with no intermediate software_Sbom wrapper."""
    doc = {
        "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
        "@graph": [
            {"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["pkg"]},
            {"type": "software_Package", "spdxId": "pkg", "name": "directpkg"},
        ],
    }
    identity = extract_spdx3_subject_identity(json.dumps(doc).encode())
    assert identity is not None
    assert identity.error is None
    assert identity.name == "directpkg"
    assert identity.version is None


def test_extract_subject_identity_ai_package_no_version() -> None:
    identity = extract_spdx3_subject_identity(json.dumps(_ONE_HOP_AI_PACKAGE).encode())
    assert identity is not None
    assert identity.error is None
    assert identity.name == "ai-model"
    assert identity.version is None


def test_extract_subject_identity_no_spdx_document_node() -> None:
    doc = {"@context": "x", "@graph": [{"type": "CreationInfo", "spdxId": "ci"}]}
    identity = extract_spdx3_subject_identity(json.dumps(doc).encode())
    assert identity is not None
    assert identity.name is None
    assert identity.version is None
    assert identity.error == "no SpdxDocument node found"


def test_extract_subject_identity_dangling_document_root() -> None:
    doc = {
        "@context": "x",
        "@graph": [{"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["gone"]}],
    }
    identity = extract_spdx3_subject_identity(json.dumps(doc).encode())
    assert identity is not None
    assert identity.error == "SpdxDocument has no usable rootElement"


def test_extract_subject_identity_dangling_sbom_root() -> None:
    doc = {
        "@context": "x",
        "@graph": [
            {"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["sbom"]},
            {"type": "software_Sbom", "spdxId": "sbom", "rootElement": ["gone"]},
        ],
    }
    identity = extract_spdx3_subject_identity(json.dumps(doc).encode())
    assert identity is not None
    assert identity.error == "Sbom node has no usable rootElement"


def test_extract_subject_identity_rejects_non_package_subject_type() -> None:
    """A SoftwareAgent node with a `name` field must not be mistaken for
    the SBOM's real subject -- the node-type allowlist guard."""
    doc = {
        "@context": "x",
        "@graph": [
            {"type": "SpdxDocument", "spdxId": "doc", "rootElement": ["agent"]},
            {"type": "SoftwareAgent", "spdxId": "agent", "name": "Some Tool"},
        ],
    }
    identity = extract_spdx3_subject_identity(json.dumps(doc).encode())
    assert identity is not None
    assert identity.name is None
    assert identity.version is None
    assert "SoftwareAgent" in (identity.error or "")


# --- compare_name_version ---------------------------------------------------


def test_compare_name_version_match_no_mismatch() -> None:
    mismatches, warnings = compare_name_version("pkg", "1.0.0", "pkg", "1.0.0")
    assert mismatches == []
    assert warnings == []


def test_compare_name_version_pep503_pep440_equivalent_no_mismatch() -> None:
    mismatches, warnings = compare_name_version(
        "My-Package", "1.0", "my_package", "1.0.0"
    )
    assert mismatches == []
    assert warnings == []


def test_compare_name_version_name_mismatch() -> None:
    mismatches, _ = compare_name_version("pkg", "1.0.0", "otherpkg", "1.0.0")
    assert len(mismatches) == 1
    assert "name" in mismatches[0]


def test_compare_name_version_version_mismatch() -> None:
    mismatches, _ = compare_name_version("pkg", "1.0.0", "pkg", "2.0.0")
    assert len(mismatches) == 1
    assert "version" in mismatches[0]


def test_compare_name_version_missing_wheel_name_warns() -> None:
    """A missing wheel-side name must warn exactly like a missing
    SBOM-side name -- the asymmetric-elif regression guard."""
    _, warnings = compare_name_version(None, "1.0.0", "pkg", "1.0.0")
    assert any("wheel METADATA has no name" in w for w in warnings)


def test_compare_name_version_missing_sbom_name_warns() -> None:
    _, warnings = compare_name_version("pkg", "1.0.0", None, "1.0.0")
    assert any("SBOM subject has no name" in w for w in warnings)


def test_compare_name_version_missing_both_names_warns() -> None:
    _, warnings = compare_name_version(None, "1.0.0", None, "1.0.0")
    assert any(
        "neither the wheel nor the SBOM subject has a name" in w for w in warnings
    )


def test_compare_name_version_missing_wheel_version_warns() -> None:
    _, warnings = compare_name_version("pkg", None, "pkg", "1.0.0")
    assert any("wheel METADATA has no version" in w for w in warnings)


def test_compare_name_version_missing_sbom_version_warns() -> None:
    _, warnings = compare_name_version("pkg", "1.0.0", "pkg", None)
    assert any("SBOM subject has no version" in w for w in warnings)


def test_compare_name_version_invalid_wheel_version_warns() -> None:
    _, warnings = compare_name_version("pkg", "not-a-version", "pkg", "1.0.0")
    assert any("wheel METADATA version" in w for w in warnings)


def test_compare_name_version_invalid_sbom_version_warns() -> None:
    _, warnings = compare_name_version("pkg", "1.0.0", "pkg", "not-a-version")
    assert any("SBOM subject version" in w for w in warnings)


# --- check_spdx3_name_version -----------------------------------------------


def test_check_spdx3_name_version_unsupported_format_warns() -> None:
    mismatches, warnings = check_spdx3_name_version("pkg", "1.0.0", b"{}", None)
    assert mismatches == []
    assert any("unsupported SBOM format" in w for w in warnings)


def test_check_spdx3_name_version_extraction_failure_warns() -> None:
    mismatches, warnings = check_spdx3_name_version(
        "pkg", "1.0.0", b"not json", "spdx3-jsonld"
    )
    assert mismatches == []
    assert any("cannot cross-check SBOM name/version" in w for w in warnings)


def test_check_spdx3_name_version_delegates_to_compare() -> None:
    mismatches, _ = check_spdx3_name_version(
        "wrongname", "1.2.3", json.dumps(_TWO_HOP).encode(), "spdx3-jsonld"
    )
    assert len(mismatches) == 1
    assert "name" in mismatches[0]


# --- format_name_version_mismatch -------------------------------------------


def test_format_name_version_mismatch() -> None:
    message = format_name_version_mismatch("pkg-1.0.0.whl", ["name: a vs b"])
    assert message == "pkg-1.0.0.whl: SBOM/wheel name: a vs b"
