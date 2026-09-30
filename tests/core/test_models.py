# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 core models.

See also: tests/core/models_wheel/test_models_wheel_files.py for
get_wheel_files() file-header scanning and content-type detection tests.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.core.models import (
    _clear_doc_counters,
    _normalize_dep,
    build_relationship,
    compute_doc_uuid,
    generate_spdx_id,
    get_wheel_files,
    normalize_dependency_specifier,
    reserve_spdx_ids,
)


def test_models_edge_cases() -> None:
    """normalize_dependency_specifier handles bad reqs and build_relationship None."""
    assert normalize_dependency_specifier("invalid requirement syntax >= 1.0 <=") == (
        "invalid requirement syntax >= 1.0 <="
    )
    assert _normalize_dep("") == ""
    assert _normalize_dep("---not-a-dep") == "---not-a-dep"
    assert (
        build_relationship(
            None,
            ["to_id"],
            "contains",
            "doc",
            "uuid",
            None,  # type: ignore[arg-type]
        )
        is None
    )


def test_normalize_dep_pep503() -> None:
    """PEP 503 name normalization leaves version/marker portion untouched."""
    assert _normalize_dep("Foo_Bar>=1.0") == "foo-bar>=1.0"
    assert _normalize_dep("PyProject.Metadata") == "pyproject-metadata"
    assert _normalize_dep("hatchling>=1.29.0") == "hatchling>=1.29.0"
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
    """Element IDs must restart from 1 after _clear_doc_counters()."""
    doc_uuid = compute_doc_uuid("resetpkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    id1 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    _clear_doc_counters(doc_uuid)
    id2 = generate_spdx_id("Package", doc_name="resetpkg", doc_uuid=doc_uuid)
    assert id1 == id2
    assert id1.endswith("#Package-1")


def test_reserve_spdx_ids_skips_reserved_numbers() -> None:
    """A reserved number is skipped by generate_spdx_id(), whatever order
    it's minted in -- regression for the wheel/directory id mint-collision
    (a registry-supplied id and a freshly-minted one landing on the exact
    same number in the same document namespace)."""
    doc_uuid = compute_doc_uuid("reservepkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    namespace = f"https://spdx.org/spdxdocs/reservepkg-{doc_uuid}"
    reserve_spdx_ids(
        "reservepkg",
        doc_uuid,
        [f"{namespace}#File-2", f"{namespace}#File-5"],
    )

    minted = [
        generate_spdx_id("File", doc_name="reservepkg", doc_uuid=doc_uuid)
        for _ in range(4)
    ]

    assert [i.rsplit("-", 1)[-1] for i in minted] == ["1", "3", "4", "6"]


def test_reserve_spdx_ids_ignores_other_namespaces() -> None:
    """An id from an unrelated document namespace is not reserved."""
    doc_uuid = compute_doc_uuid("nspkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    reserve_spdx_ids(
        "nspkg",
        doc_uuid,
        ["https://spdx.org/spdxdocs/other-project-deadbeef#File-1"],
    )

    minted = generate_spdx_id("File", doc_name="nspkg", doc_uuid=doc_uuid)

    assert minted.endswith("#File-1")


def test_generate_spdx_id_encodes_names_and_reserves_encoded_ids() -> None:
    """A name with a space yields a valid IRI in both the namespace and the
    id, and a registry-supplied id carrying that encoded prefix is reserved
    under the same counter key the next mint uses (no duplicate id)."""
    doc_uuid = compute_doc_uuid("my model", "1.0", [])
    _clear_doc_counters(doc_uuid)
    namespace = f"https://spdx.org/spdxdocs/my%20model-{doc_uuid}"
    reserve_spdx_ids(
        "my model", doc_uuid, [f"{namespace}#AIPackage-Stable%20Diffusion-1"]
    )

    minted = generate_spdx_id(
        "AIPackage-Stable Diffusion", doc_name="my model", doc_uuid=doc_uuid
    )

    assert minted == f"{namespace}#AIPackage-Stable%20Diffusion-2"
    assert generate_spdx_id("SpdxDocument", "my model", doc_uuid) == namespace


def test_clear_doc_counters_clears_reservations() -> None:
    """_clear_doc_counters() also drops any reservation for that doc_uuid --
    a caller must reserve *after* clearing, never before (see build()).

    Asserted through observable minting behaviour only (never by poking
    the internal ``_RESERVED`` dict): if the reservation survived the
    clear, this mint would skip ``#File-1`` and land on ``#File-2``
    instead."""
    doc_uuid = compute_doc_uuid("clearpkg", "1.0", [])
    _clear_doc_counters(doc_uuid)
    namespace = f"https://spdx.org/spdxdocs/clearpkg-{doc_uuid}"
    reserve_spdx_ids("clearpkg", doc_uuid, [f"{namespace}#File-1"])

    _clear_doc_counters(doc_uuid)

    minted = generate_spdx_id("File", doc_name="clearpkg", doc_uuid=doc_uuid)
    assert minted.endswith("#File-1")


def test_compute_doc_uuid_field_boundary_no_collision() -> None:
    """Input combinations that would collide under a naive ':' separator must not.

    With ':' as separator, name="a:b" + version="c" + deps=[] and
    name="a" + version="b:c" + deps=[] both produce the seed "a:b:c:".
    The NUL separator is immune because PEP 508 names, PEP 440 versions, and
    SHA-256 hex digests cannot contain \\x00.
    """
    # Same number of ':' characters -- would collide with ':' separator
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


# pylint: disable-next=too-few-public-methods
class _FakeIncludedFile:
    """Minimal stand-in for ``hatchling.builders.plugin.interface.IncludedFile``."""

    def __init__(self, path: str, distribution_path: str) -> None:
        self.path = path
        self.relative_path = distribution_path
        self.distribution_path = distribution_path


def test_get_wheel_files_normalizes_windows_style_distribution_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: Hatchling builds ``distribution_path`` with
    ``os.path.join``, which uses backslashes on Windows -- unlike a
    wheel's actual internal zip-entry paths, which the ZIP format itself
    requires to be forward-slash-separated regardless of host OS. Left
    un-normalized, the Merkle root (and the ``doc_uuid`` built from it)
    would differ by build platform for byte-identical source content,
    since both the sort key and the tree-combination input are exactly
    this string.

    Uses two files, ``pkg/zoo.py`` and ``pkg0/a.py``, deliberately chosen
    so their relative sort order flips depending on the separator: ``/``
    (0x2F) sorts before ``0`` (0x30), so ``pkg/zoo.py`` sorts first in
    POSIX form -- but ``\\`` (0x5C) sorts *after* ``0``, so
    ``pkg\\zoo.py`` would sort *second* in un-normalized Windows form.
    With only one file (or a pair whose order doesn't happen to flip),
    the Merkle root would trivially match either way and this test
    wouldn't actually prove anything.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "pkg"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    zoo_file = pkg_dir / "zoo.py"
    zoo_file.write_text("zoo = 1\n", encoding="utf-8")
    pkg0_dir = tmp_path / "pkg0"
    pkg0_dir.mkdir()
    a_file = pkg0_dir / "a.py"
    a_file.write_text("a = 1\n", encoding="utf-8")

    def _make_fake_recurse(
        sep: str,
    ) -> Callable[[WheelBuilder], Iterator[_FakeIncludedFile]]:
        def _fake_recurse(_self: WheelBuilder) -> Iterator[_FakeIncludedFile]:
            yield _FakeIncludedFile(str(zoo_file), f"pkg{sep}zoo.py")
            yield _FakeIncludedFile(str(a_file), f"pkg0{sep}a.py")

        return _fake_recurse

    monkeypatch.setattr(WheelBuilder, "recurse_included_files", _make_fake_recurse("/"))
    posix_root, posix_files, _ = get_wheel_files(tmp_path)

    monkeypatch.setattr(
        WheelBuilder, "recurse_included_files", _make_fake_recurse("\\")
    )
    windows_root, windows_files, _ = get_wheel_files(tmp_path)

    assert posix_root is not None
    assert posix_root == windows_root, (
        "Merkle root must not depend on the build platform's path separator"
    )
    assert [f.distribution_path for f in posix_files] == ["pkg/zoo.py", "pkg0/a.py"]
    assert [f.distribution_path for f in windows_files] == ["pkg/zoo.py", "pkg0/a.py"]
