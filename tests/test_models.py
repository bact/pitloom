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


def test_normalize_dep_pep503() -> None:
    """PEP 503 normalization lowercases and collapses separators in the name portion."""
    assert _normalize_dep("Foo_Bar>=1.0") == "foo-bar>=1.0"
    assert _normalize_dep("PyProject.Metadata") == "pyproject-metadata"
    assert _normalize_dep("tomli>=2.0; python_version<'3.11'") == "tomli>=2.0; python_version<'3.11'"
    assert _normalize_dep("my-lib") == "my-lib"
    assert _normalize_dep("My_Lib>=1.0") == "my-lib>=1.0"


def test_compute_doc_uuid_deterministic() -> None:
    """Same inputs always produce the same UUID."""
    uuid1 = compute_doc_uuid("myproject", "1.0.0", ["requests>=2.0", "click>=8.0"])
    uuid2 = compute_doc_uuid("myproject", "1.0.0", ["requests>=2.0", "click>=8.0"])
    assert uuid1 == uuid2


def test_compute_doc_uuid_dep_normalization() -> None:
    """my-lib, my_lib, and my.lib are treated as the same dependency."""
    uuid_hyphen = compute_doc_uuid("pkg", "1.0", ["my-lib>=1.0"])
    uuid_underscore = compute_doc_uuid("pkg", "1.0", ["my_lib>=1.0"])
    uuid_dot = compute_doc_uuid("pkg", "1.0", ["my.lib>=1.0"])
    assert uuid_hyphen == uuid_underscore == uuid_dot


def test_compute_doc_uuid_dep_order_independent() -> None:
    """Dependency list order does not affect the UUID."""
    uuid_ab = compute_doc_uuid("pkg", "1.0", ["aaa>=1.0", "bbb>=2.0"])
    uuid_ba = compute_doc_uuid("pkg", "1.0", ["bbb>=2.0", "aaa>=1.0"])
    assert uuid_ab == uuid_ba


def test_compute_doc_uuid_differs_on_change() -> None:
    """Each input field independently affects the UUID."""
    base = compute_doc_uuid("myproject", "1.0.0", ["requests>=2.0"])
    assert compute_doc_uuid("other", "1.0.0", ["requests>=2.0"]) != base
    assert compute_doc_uuid("myproject", "2.0.0", ["requests>=2.0"]) != base
    assert compute_doc_uuid("myproject", "1.0.0", ["click>=8.0"]) != base
    assert compute_doc_uuid("myproject", "1.0.0", ["requests>=2.0"], merkle_root="abc123") != base


def test_clear_doc_counters_resets_sequence() -> None:
    """After clearing, element IDs restart from 1."""
    doc_uuid = compute_doc_uuid("resettest", "1.0", [])
    _clear_doc_counters(doc_uuid)

    id1 = generate_spdx_id("Package", doc_name="resettest", doc_uuid=doc_uuid)
    assert id1.endswith("#Package-1")

    _clear_doc_counters(doc_uuid)

    id2 = generate_spdx_id("Package", doc_name="resettest", doc_uuid=doc_uuid)
    assert id2.endswith("#Package-1")
    assert id1 == id2


def test_compute_doc_uuid_field_boundary_no_collision() -> None:
    """NUL separator prevents collisions between adjacent fields."""
    # Without a proper separator, ("ab", "cd") and ("a", "bcd") could collide.
    uuid1 = compute_doc_uuid("ab", "cd", [])
    uuid2 = compute_doc_uuid("a", "bcd", [])
    assert uuid1 != uuid2

    uuid3 = compute_doc_uuid("pkg", "1.0", ["aabb"])
    uuid4 = compute_doc_uuid("pkg", "1.0", ["aa", "bb"])
    assert uuid3 != uuid4
