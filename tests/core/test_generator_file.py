# ruff: noqa: F403, F405
from __future__ import annotations

from pitloom.core.project import ProjectFile

from .conftest import *


def test_build_file_native_copyright_and_declared_license() -> None:
    """A file's own SPDX-FileCopyrightText/License-Identifier tags set
    native fields directly; the license relationship is hasDeclaredLicense,
    never hasConcludedLicense (a file's own tag always is its own claim,
    nothing to classify against)."""
    files = [
        ProjectFile(
            physical_path="src/pkg/tagged.py",
            distribution_path="pkg/tagged.py",
            digest_sha256="a" * 64,
            copyright_text="2026 Test Author",
            copyright_source="spdx_tag",
            spdx_license_identifier="MIT",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/tagged.py")

    assert file_elem["software_copyrightText"] == "2026 Test Author"

    relationships = [e for e in graph if e.get("type") == "Relationship"]
    license_rels = [r for r in relationships if r.get("from") == file_elem["spdxId"]]
    assert [r["relationshipType"] for r in license_rels] == ["hasDeclaredLicense"]

    license_targets = license_rels[0]["to"]
    assert isinstance(license_targets, list)
    license_target_id = license_targets[0]
    license_elem = next(
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("spdxId") == license_target_id
    )
    assert license_elem["simplelicensing_licenseText"] == "MIT"


def test_build_file_primary_purpose_and_content_type_independent() -> None:
    """The README.md case: SPDX-FileType: DOCUMENTATION maps to
    primaryPurpose, and an independently-resolved content_type sets
    contentType -- both native, both set, neither gated on the other."""
    files = [
        ProjectFile(
            physical_path="README.md",
            distribution_path="README.md",
            digest_sha256="a" * 64,
            file_type="DOCUMENTATION",
            content_type="text/markdown",
            content_type_method="extension_guess",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "README.md")

    assert file_elem["software_primaryPurpose"] == "documentation"
    assert file_elem["contentType"] == "text/markdown"
    assert "summary" not in file_elem

    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    # declared: no Method segment recorded.
    assert "method" not in fields["file_type"]
    # detected: Method segment present, distinct field key from file_type.
    assert fields["content_type"]["method"] == "extension_guess"


def test_build_file_content_type_config_override_is_sbom_author_supplied() -> None:
    """A [[tool.pitloom.content-type.override]] match
    (content_type_method="config_override") sets contentType natively,
    same as a detected value, but records role sbomAuthorSupplied in
    provenance -- never magika_content_detection/extension_guess,
    since Pitloom didn't detect anything for this file."""
    files = [
        ProjectFile(
            physical_path="vendor/lib.bin",
            distribution_path="vendor/lib.bin",
            digest_sha256="a" * 64,
            content_type="application/octet-stream",
            content_type_method="config_override",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "vendor/lib.bin")

    assert file_elem["contentType"] == "application/octet-stream"

    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    assert fields["content_type"]["role"] == "sbomAuthorSupplied"
    assert "method" not in fields["content_type"]
    assert "tool" not in fields["content_type"]


def test_build_file_unmapped_file_type_goes_to_summary_not_content_type() -> None:
    """An unmapped SPDX-FileType (no SoftwarePurpose equivalent) with no
    content_type resolved: the raw tag value lands in File.summary, no
    primaryPurpose or contentType is set, no error."""
    files = [
        ProjectFile(
            physical_path="logo.png",
            distribution_path="logo.png",
            digest_sha256="a" * 64,
            file_type="IMAGE",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "logo.png")

    assert "software_primaryPurpose" not in file_elem
    assert "contentType" not in file_elem
    assert file_elem["summary"] == "FileType: IMAGE"

    # An unmapped file_type still gets a provenance entry recording where
    # the raw value came from, same as the mapped case -- summary-only
    # placement isn't a reason to drop provenance.
    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    assert fields["file_type"]["source"] == "logo.png"
    assert fields["file_type"]["location"] == "SPDX-FileType"


def test_build_file_primary_purpose_never_inferred_from_content_type() -> None:
    """Regression guard: a resolved content_type must never backfill
    primaryPurpose, even when file_type is absent entirely -- SoftwarePurpose
    is about usage, not content, per the SPDX 3 spec."""
    files = [
        ProjectFile(
            physical_path="photo.jpg",
            distribution_path="photo.jpg",
            digest_sha256="a" * 64,
            content_type="image/jpeg",
            content_type_method="magika",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "photo.jpg")

    assert file_elem["contentType"] == "image/jpeg"
    assert "software_primaryPurpose" not in file_elem
    assert "summary" not in file_elem  # no file_type tag at all -- nothing to record


def test_build_file_contributors_only_in_summary_never_native() -> None:
    """FileContributor values appear only in File.summary, sorted, never
    natively -- the Annotation carries a plain source-tracking entry with
    no value duplicated into it."""
    files = [
        ProjectFile(
            physical_path="pkg/mod.py",
            distribution_path="pkg/mod.py",
            digest_sha256="a" * 64,
            file_contributors=["Bob", "Alice"],
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/mod.py")

    assert file_elem["summary"] == "Contributor: Alice; Contributor: Bob"

    fields = _annotation_fields_for(graph, file_elem["spdxId"])
    assert fields is not None
    assert "Alice" not in fields["file_contributors"]["source"]
    assert "Bob" not in fields["file_contributors"]["source"]


def test_build_file_summary_combines_contributors_and_file_type_sorted() -> None:
    """A file with both contributors and an unmapped file_type produces one
    combined summary string, sorted by key then value ('Contributor'
    entries before 'FileType', per the alphabetical-by-key rule)."""
    files = [
        ProjectFile(
            physical_path="pkg/mixed.bin",
            distribution_path="pkg/mixed.bin",
            digest_sha256="a" * 64,
            file_contributors=["Zoe", "Amy"],
            file_type="BINARY",
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/mixed.bin")

    assert file_elem["summary"] == (
        "Contributor: Amy; Contributor: Zoe; FileType: BINARY"
    )


def test_build_file_no_header_data_emits_nothing_extra() -> None:
    """A file with no header-derived data at all gets no summary, no
    Annotation, no license relationship, and no native copyright/purpose/
    contentType fields -- matches today's pre-feature output exactly."""
    files = [
        ProjectFile(
            physical_path="pkg/plain.py",
            distribution_path="pkg/plain.py",
            digest_sha256="a" * 64,
        )
    ]
    graph = _build_graph_for_files(files)
    file_elem = _find_file_element(graph, "pkg/plain.py")

    assert "summary" not in file_elem
    assert "software_copyrightText" not in file_elem
    assert "software_primaryPurpose" not in file_elem
    assert "contentType" not in file_elem
    assert _annotation_fields_for(graph, file_elem["spdxId"]) is None
    relationships = [e for e in graph if e.get("type") == "Relationship"]
    assert not [r for r in relationships if r.get("from") == file_elem["spdxId"]]


def test_build_file_shared_license_dedupes_to_one_element() -> None:
    """Two files declaring the same SPDX-License-Identifier reuse one
    SimpleLicensingText element, with two separate relationships."""
    files = [
        ProjectFile(
            physical_path="pkg/a.py",
            distribution_path="pkg/a.py",
            digest_sha256="a" * 64,
            spdx_license_identifier="Apache-2.0",
        ),
        ProjectFile(
            physical_path="pkg/b.py",
            distribution_path="pkg/b.py",
            digest_sha256="b" * 64,
            spdx_license_identifier="Apache-2.0",
        ),
    ]
    graph = _build_graph_for_files(files)

    license_elements = [
        e
        for e in graph
        if e.get("type") == "simplelicensing_SimpleLicensingText"
        and e.get("simplelicensing_licenseText") == "Apache-2.0"
    ]
    assert len(license_elements) == 1

    license_spdx_id = license_elements[0]["spdxId"]
    declared_rels = [
        e
        for e in graph
        if e.get("type") == "Relationship"
        and e.get("relationshipType") == "hasDeclaredLicense"
        and e.get("to") == [license_spdx_id]
    ]
    assert len(declared_rels) == 2
