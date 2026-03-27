# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 core models."""

from pitloom.core.models import (
    _clear_doc_counters,
    _normalize_dep,
    compute_doc_uuid,
    generate_spdx_id,
)


def test_normalize_dep_pep503() -> None:
    """PEP 503 name normalization leaves version/marker portion untouched."""
    assert _normalize_dep("Foo_Bar>=1.0") == "foo-bar>=1.0"
    assert _normalize_dep("PyProject.Metadata") == "pyproject-metadata"
    assert _normalize_dep("hatchling>=1.28.0") == "hatchling>=1.28.0"
    assert _normalize_dep("  tomli>=2.0; python_version<'3.11'  ") == (
        "tomli>=2.0; python_version<'3.11'"
    )
    assert _normalize_dep("My---Pkg") == "my-pkg"


def test_compute_doc_uuid_deterministic() -> None:
    """Same inputs always produce the same UUID."""
    uuid1 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    uuid2 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    assert uuid1 == uuid2


def test_compute_doc_uuid_dep_normalization() -> None:
    """Dependency name normalization is applied before hashing."""
    uuid_canonical = compute_doc_uuid("mypkg", "1.0", ["my-lib>=1.0"])
    uuid_underscore = compute_doc_uuid("mypkg", "1.0", ["my_lib>=1.0"])
    uuid_dot = compute_doc_uuid("mypkg", "1.0", ["my.lib>=1.0"])
    assert uuid_canonical == uuid_underscore == uuid_dot


def test_compute_doc_uuid_dep_order_independent() -> None:
    """Dependency list order does not affect the UUID."""
    uuid_a = compute_doc_uuid("mypkg", "1.0", ["alpha>=1", "beta>=2"])
    uuid_b = compute_doc_uuid("mypkg", "1.0", ["beta>=2", "alpha>=1"])
    assert uuid_a == uuid_b


def test_compute_doc_uuid_differs_on_change() -> None:
    """Different name, version, deps, or merkle_root produce different UUIDs."""
    base = compute_doc_uuid("mypkg", "1.0", ["dep>=1"])
    assert base != compute_doc_uuid("other", "1.0", ["dep>=1"])
    assert base != compute_doc_uuid("mypkg", "2.0", ["dep>=1"])
    assert base != compute_doc_uuid("mypkg", "1.0", ["dep>=2"])
    assert base != compute_doc_uuid("mypkg", "1.0", ["dep>=1"], merkle_root="abc123")


def test_clear_doc_counters_resets_sequence() -> None:
    """Element IDs must restart from -1 after _clear_doc_counters()."""
    doc_uuid = compute_doc_uuid("resetpkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    id1 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    _clear_doc_counters(doc_uuid)
    id2 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    assert id1 == id2
    assert id1.endswith("#Package-1")


def test_compute_doc_uuid_field_boundary_no_collision() -> None:
    """Input combinations that would collide under a naive ':' separator must not.

    With ':' as separator, name="a:b" + version="c" + deps=[] and
    name="a" + version="b:c" + deps=[] both produce the seed "a:b:c:".
    The NUL separator is immune because PEP 508 names, PEP 440 versions, and
    SHA-256 hex digests cannot contain \\x00.
    """
    # Same number of ':' characters — would collide with ':' separator
    uuid_split_in_name = compute_doc_uuid("my-pkg", "1.0", ["dep-a>=1", "dep-b>=2"])
    uuid_split_in_version = compute_doc_uuid("my-pkg", "2.0", ["dep-a>=1"])
    uuid_no_deps = compute_doc_uuid("my-pkg", "1.0", [])
    assert len({uuid_split_in_name, uuid_split_in_version, uuid_no_deps}) == 3


def test_generate_spdx_id() -> None:
    """Test SPDX ID generation."""
    person_id = generate_spdx_id("Person")
    assert person_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#Person-" in person_id

    package_id = generate_spdx_id("Package")
    assert package_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#Package-" in package_id

    doc_id = generate_spdx_id("SpdxDocument")
    assert doc_id.startswith("https://spdx.org/spdxdocs/pitloom-")
    assert "#" not in doc_id
