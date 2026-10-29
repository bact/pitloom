# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A checkout's Git LFS pointer is emitted as its ``oid``: one SHA-256
``Hash`` with a comment giving the stated size, ``Method: lfs_pointer``
provenance, no SHA-512 and nothing read from the pointer text. An
archive's pointer is emitted as any other file.

See also: tests/test_lfs_pointer_surfaces.py (the digests every route
records); tests/_lfs.py (the pointer tree).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_project_sbom, generate_wheel_sbom
from pitloom.core.lfs_pointer import LfsPointer
from pitloom.core.provenance import ProvenanceConfig
from pitloom.export.spdx3_json import lfs_pointer_hashes
from tests._author_routes import CREATED
from tests._lfs import lfs_pointer_bytes, pointers, tree, write_project
from tests._raw_archive import write_raw_zip
from tests._spdx3_validate import assert_spdx3_valid

_Graph = list[dict[str, Any]]
_POSIX = sys.platform != "win32"
_INIT = "demo/__init__.py"
#: The ordinary file declares a licence and gets a content type, so their
#: absence on a pointer is not vacuous.


def _tree() -> dict[str, bytes]:
    return {**tree(), _INIT: b"# SPDX-License-Identifier: MIT\nx = 1\n"}


def _project_sbom(root: Path, **kwargs: Any) -> str:
    return generate_project_sbom(
        root,
        creation_metadata=CREATED,
        offline=True,
        extract_file_header=True,
        content_type=True,
        content_type_method="extension",
        **kwargs,
    )


def _files(sbom: str) -> dict[str, dict[str, Any]]:
    return {
        e["name"]: e
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "software_File" and e.get("software_fileKind") != "directory"
    }


def _provenance_of(sbom: str, element: dict[str, Any]) -> str:
    """Every provenance text about *element*: its comment and annotations."""
    graph: _Graph = json.loads(sbom)["@graph"]
    notes = [
        e["statement"]
        for e in graph
        if e["type"] == "Annotation" and e["subject"] == element["spdxId"]
    ]
    return "\n".join([element.get("comment", ""), *notes])


def _real_hashes(data: bytes) -> list[dict[str, str]]:
    return [
        {"type": "Hash", "algorithm": "sha256", "hashValue": _sha256(data)},
        {"type": "Hash", "algorithm": "sha512", "hashValue": _sha512(data)},
    ]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha512(data: bytes) -> str:
    return hashlib.sha512(data).hexdigest()


@pytest.mark.parametrize("detail", ["minimal", "full"])
@pytest.mark.parametrize("fmt", ["annotation", "comment", "both"])
def test_checkout_pointer_is_its_oid(tmp_path: Path, fmt: str, detail: str) -> None:
    """Each pointer: one SHA-256 that is its oid, the size in the Hash
    comment, ``lfs_pointer`` provenance at every detail, no content type
    or licence; the ordinary and the long file keep their read hashes."""
    contents = _tree()
    sbom = _project_sbom(
        write_project(tmp_path, contents),
        provenance=ProvenanceConfig(format=fmt, detail=detail),
    )
    files = _files(sbom)
    for name, pointer in pointers().items():
        element = files[name]
        assert pointer.oid != _sha256(contents[name])
        assert element["verifiedUsing"] == [
            {
                "type": "Hash",
                "algorithm": "sha256",
                "hashValue": pointer.oid,
                "comment": "Git LFS pointer oid; content not read; "
                f"size {pointer.size} bytes",
            }
        ]
        assert "Method: lfs_pointer" in _provenance_of(sbom, element) or (
            '"method":"lfs_pointer"' in _provenance_of(sbom, element)
        )
        assert "contentType" not in element
    for name in (_INIT, "demo/long.dat"):
        assert files[name]["verifiedUsing"] == _real_hashes(contents[name])
        assert "lfs_pointer" not in _provenance_of(sbom, files[name])
    assert "contentType" in files[_INIT]
    graph: _Graph = json.loads(sbom)["@graph"]
    licensed = {
        e["from"]
        for e in graph
        if e["type"] == "Relationship" and e["relationshipType"] == "hasDeclaredLicense"
    }
    assert files[_INIT]["spdxId"] in licensed
    assert not licensed & {files[n]["spdxId"] for n in pointers()}


def test_archive_pointer_is_an_ordinary_file(tmp_path: Path) -> None:
    """A wheel ships the pointer text: its own two hashes, no LFS comment
    and no ``lfs_pointer`` provenance anywhere."""
    info = "demo-1.0.dist-info/"
    members = {
        **tree(),
        f"{info}METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        f"{info}WHEEL": b"Wheel-Version: 1.0\n",
        f"{info}RECORD": b"",
    }
    wheel = write_raw_zip(tmp_path / "demo-1.0-py3-none-any.whl", members)
    sbom = generate_wheel_sbom(wheel, creation_metadata=CREATED)
    files = _files(sbom)
    contents = tree()
    for name, pointer in pointers().items():
        assert pointer.oid != _sha256(contents[name])
        assert files[name]["verifiedUsing"] == _real_hashes(contents[name])
    assert "lfs_pointer" not in sbom
    assert "Git LFS" not in sbom


def test_pull_keeps_the_sha256(tmp_path: Path) -> None:
    """After ``git lfs pull`` the file's SHA-256 and the package's Merkle
    root are unchanged; only the SHA-512 and the LFS comment differ."""
    content = b"real content\n"
    name = "demo/data.bin"
    before = {_INIT: _tree()[_INIT], name: lfs_pointer_bytes(content)}
    after = {**before, name: content}
    assert before[name] != after[name]
    sboms = [
        _project_sbom(write_project(tmp_path / label, files))
        for label, files in (("before", before), ("after", after))
    ]
    hashes = [_files(s)[name]["verifiedUsing"] for s in sboms]
    assert hashes[0][0]["hashValue"] == hashes[1][0]["hashValue"] == _sha256(content)
    assert [len(h) for h in hashes] == [1, 2]
    assert "comment" in hashes[0][0] and "comment" not in hashes[1][0]
    roots = [
        e["verifiedUsing"]
        for s in sboms
        for e in json.loads(s)["@graph"]
        if e["type"] == "software_Package" and "verifiedUsing" in e
    ]
    assert len(roots) == 2 and roots[0] == roots[1]


def test_pointer_sbom_is_valid_and_deterministic(tmp_path: Path) -> None:
    """Two runs give the same bytes, which validate; a newline in a
    pointer's path stays out of the Hash comment and off a line of its own."""
    odd = "demo/new\nline.dat"
    contents = _tree()
    if _POSIX:
        contents[odd] = lfs_pointer_bytes(b"odd")
    root = write_project(tmp_path / "p", contents)
    config = ProvenanceConfig(format="both")
    runs = [_project_sbom(root, provenance=config) for _ in range(2)]
    assert runs[0] == runs[1]
    out = tmp_path / "sbom.spdx3.json"
    out.write_text(runs[0], encoding="utf-8")
    assert_spdx3_valid(out)
    if _POSIX:
        element = _files(runs[0])[odd]
        assert "line.dat" not in element["verifiedUsing"][0]["comment"]
        assert "\n" not in element["comment"]
        assert "Method: lfs_pointer" in element["comment"]


@pytest.mark.parametrize(("size", "said"), [(0, "0 bytes"), (1, "1 byte")])
def test_hash_comment_size(size: int, said: str) -> None:
    """The stated size is written as a count of bytes."""
    (only,) = lfs_pointer_hashes(LfsPointer("a" * 64, size))
    assert only.comment == f"Git LFS pointer oid; content not read; size {said}"
