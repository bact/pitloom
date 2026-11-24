# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for SPDX 3 core models.

See also: tests/core/models_wheel/test_models_wheel_files.py for
get_wheel_files() file-header scanning and content-type detection tests.
"""

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

from pitloom.assemble import project_document_id
from pitloom.core.models import (
    _build_merkle_tree,
    _clear_doc_counters,
    _normalize_dep,
    build_relationship,
    compute_doc_uuid,
    generate_spdx_id,
    get_wheel_files,
    merkle_root,
    reserve_spdx_ids,
)
from tests.fixtures.locked_deps import (
    PYLOCK_WITH_TRANSITIVE_IDNA,
    PYPROJECT_WITH_REQUESTS_DEPENDENCY,
    write_locked_deps_project,
)


def _pair(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(left + right).digest()


_A, _B, _C = (hashlib.sha256(s).digest() for s in (b"a", b"b", b"c"))


@pytest.mark.parametrize(
    ("leaves", "expected"),
    [
        ([_A], _A),  # one leaf is its own root
        ([_A, _B], _pair(_A, _B)),
        ([_A, _B, _C], _pair(_pair(_A, _B), _C)),  # odd: C promoted unchanged
    ],
    ids=["one", "pair", "odd"],
)
def test_merkle_root_tree_shape(leaves: list[bytes], expected: bytes) -> None:
    """Pairs hash left then right; an unpaired node is promoted, not
    duplicated; the result is the same on every call."""
    assert merkle_root(leaves) == expected.hex()
    assert merkle_root(tuple(leaves)) == _build_merkle_tree(list(leaves))
    assert merkle_root([_B, _A]) != merkle_root([_A, _B])  # order is the caller's


def test_merkle_root_refuses_no_leaves() -> None:
    """No leaves, no root: the caller decides what an empty set means."""
    with pytest.raises(ValueError, match="at least one leaf"):
        merkle_root([])


def test_models_edge_cases() -> None:
    """_normalize_dep handles bad reqs and build_relationship None."""
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
    """PEP 503 name normalisation leaves version/marker portion untouched."""
    assert _normalize_dep("Foo_Bar>=1.0") == "foo-bar>=1.0"
    assert _normalize_dep("PyProject.Metadata") == "pyproject-metadata"
    assert _normalize_dep("hatchling>=1.29.0") == "hatchling>=1.29.0"
    assert _normalize_dep("  tomli>=2.0; python_version<'3.11'  ") == (
        'tomli>=2.0; python_version < "3.11"'
    )
    assert _normalize_dep("Not A Req!") == "not A Req!"
    assert _normalize_dep("My---Pkg") == "my-pkg"


def test_compute_doc_uuid_deterministic() -> None:
    """Same inputs always produce the same UUID."""
    uuid1 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    uuid2 = compute_doc_uuid("mypkg", "1.0.0", ["requests>=2.0", "click>=8.0"])
    assert uuid1 == uuid2


def test_compute_doc_uuid_dep_normalization() -> None:
    """Dependency name normalisation is applied before hashing."""
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
    it's minted in, so a registry-supplied id and a freshly minted one never
    land on the same number in one document namespace."""
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
    """Hatchling builds ``distribution_path`` with ``os.path.join``, which
    uses backslashes on Windows, unlike a wheel's zip-entry paths (always
    forward-slash-separated). Un-normalised, the Merkle root (and the
    ``doc_uuid`` built from it) would differ by build platform for
    byte-identical content, since this string is the sort key that orders
    the leaves (a leaf is the file's digest alone).

    Uses two files, ``pkg/zoo.py`` and ``pkg0/a.py``, deliberately chosen
    so their relative sort order flips depending on the separator: ``/``
    (0x2F) sorts before ``0`` (0x30), so ``pkg/zoo.py`` sorts first in
    POSIX form -- but ``\\`` (0x5C) sorts *after* ``0``, so
    ``pkg\\zoo.py`` would sort *second* in un-normalised Windows form.
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


_LOCKED = ["requests==2.31.0", "idna==3.7"]


def _lock_provenance(source: str, method: str = "resolved_lockfile") -> str:
    return f"Source: {source} | Method: {method}"


# Today's ids, pinned on purpose: the provenance string of the locked
# dependencies is a seed input of compute_doc_uuid, so rewording a label
# changes every SPDX id of a document with a lock. A failure here means
# exactly that; change the literals only as a deliberate id break.
# Each provenance shape is one a reader builds (extract/lock/cascade.py
# `_LOCK_SOURCES` with `provenance_source`/`provenance_segment`,
# extract/project/pyproject.py poetry.lock, deps_installed.py default).
_PINNED_DOC_UUIDS = [
    pytest.param(None, None, "941f9857-d3b0-59e6-ac6f-4682c38fee73", id="no-lock"),
    pytest.param(
        _LOCKED, None, "7bbd3b4a-5cda-5459-ad80-485c4f7d7a39", id="no-provenance"
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("lock file"),
        "1fc24d64-bd8d-552c-8282-3c65de6fc874",
        id="default",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("pylock.toml"),
        "f5442da8-76ae-5e87-9f89-0f60a76a5b2d",
        id="pylock",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("uv.lock"),
        "edfc06bd-d6ee-5286-b28c-130f46833012",
        id="uv",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("poetry.lock"),
        "bf2edfb5-0095-53d7-a448-e61f1fd6d7b1",
        id="poetry",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("pdm.lock"),
        "b775aa51-9326-5572-ad4a-063cc6a15716",
        id="pdm",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("Pipfile.lock"),
        "0f0aba83-6143-526e-b085-bb8d2596b801",
        id="pipfile",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("requirements.txt", "pinned_requirements"),
        "65ab7efb-ef90-57de-be10-e672ceabc0ee",
        id="requirements",
    ),
    pytest.param(
        _LOCKED,
        _lock_provenance("uv.lock") + " | Note: supersedes poetry.lock",
        "4d187b2e-b3e0-5d47-bd31-e9ddd36aa2a4",
        id="supersedes",
    ),
    pytest.param(
        [],
        _lock_provenance("pylock.toml"),
        "21ccb408-ad3e-5440-870f-1ae164dd6dd6",
        id="empty-lock",
    ),
]


@pytest.mark.parametrize(("locked", "provenance", "expected"), _PINNED_DOC_UUIDS)
def test_compute_doc_uuid_pinned_per_lock_provenance(
    locked: list[str] | None, provenance: str | None, expected: str
) -> None:
    """Each locked-dependencies provenance shape keeps today's document id."""
    assert (
        compute_doc_uuid(
            "demo",
            "1.0",
            ["requests>=2.0"],
            locked_dependencies=locked,
            locked_dependencies_provenance=provenance,
        )
        == expected
    )


def test_compute_doc_uuid_lock_gate_and_wording_are_id_inputs() -> None:
    """An empty lock with a provenance differs from no lock, and two wordings
    of one lock differ: the label text is an id input today."""
    args = ("demo", "1.0", ["requests>=2.0"])
    no_lock = compute_doc_uuid(*args)
    empty_lock = compute_doc_uuid(
        *args, locked_dependencies=[], locked_dependencies_provenance="Source: x"
    )
    reworded = [
        compute_doc_uuid(
            *args,
            locked_dependencies=_LOCKED,
            locked_dependencies_provenance=label,
        )
        for label in ("Source: pylock.toml", "Source: pylock.toml file")
    ]
    assert empty_lock != no_lock
    assert reworded[0] != reworded[1]


@pytest.mark.platform
def test_project_document_id_pinned_through_real_lock_reader(
    tmp_path: Path,
) -> None:
    """The pylock.toml reader's real provenance string yields today's id."""
    root = write_locked_deps_project(tmp_path / "proj")
    # write_bytes: the id covers file digests, so no CRLF on Windows.
    for name, text in (
        ("pyproject.toml", PYPROJECT_WITH_REQUESTS_DEPENDENCY),
        ("pylock.toml", PYLOCK_WITH_TRANSITIVE_IDNA),
    ):
        (root / name).write_bytes(text.encode())
    assert project_document_id(root) == (
        "https://spdx.org/spdxdocs/locked-app-e3a81b9b-c82a-5658-ad0a-9f82a2758350"
    )


_POETRY_PYPROJECT = """
[tool.poetry]
name = "poetry-app"
version = "0.1.0"
description = "demo"
authors = ["A <a@example.com>"]

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.0"
""".strip()

_POETRY_LOCK = """
[[package]]
name = "requests"
version = "2.31.0"
description = "demo"
optional = false
python-versions = ">=3.7"

[[package]]
name = "idna"
version = "3.7"
description = "demo"
optional = false
python-versions = ">=3.5"

[metadata]
lock-version = "2.0"
python-versions = "^3.10"
content-hash = "0"
""".strip()


@pytest.mark.platform
def test_project_document_id_pinned_through_poetry_lock_route(
    tmp_path: Path,
) -> None:
    """The hand-written poetry.lock provenance (extract/project/pyproject.py)
    yields today's id; reading it needs the real poetry.lock reader."""
    root = tmp_path / "proj"
    root.mkdir()
    # write_bytes: the id covers file digests, so no CRLF on Windows.
    (root / "pyproject.toml").write_bytes(_POETRY_PYPROJECT.encode())
    (root / "poetry.lock").write_bytes(_POETRY_LOCK.encode())
    assert project_document_id(root) == (
        "https://spdx.org/spdxdocs/poetry-app-19c9284a-4a45-5dc9-a4d7-507d9655d956"
    )
