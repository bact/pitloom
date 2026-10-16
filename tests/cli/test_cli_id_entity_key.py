# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`pitloom id generate -e NAME:TYPE` stores a dataset, a model or a file
below the root by its path key and digest, anything else by name.

See also: tests/core/test_loom_dataset_path_keys.py (the loom lookup of it).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from pitloom.cli.id import _run_id_command
from pitloom.cli.parser import _build_parser
from pitloom.core import dataset_hash
from pitloom.core.dataset_hash import DatasetDigest, hash_dataset
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    FILE_TYPE,
    PACKAGE_TYPE,
    IdRegistry,
)

_DS = ":" + DATASET_PACKAGE_TYPE
_SHA = hashlib.sha256(b"x\n").hexdigest()
_WITHOUT = "pinned without SHA-256"


def _entities(
    registry_path: Path, proj: Path, spec: str
) -> tuple[list[tuple[str, str]], int]:
    """Run ``id generate -e SPEC``; the non-file keys saved, the exit code."""
    entries, code = _entries(registry_path, proj, spec)
    return [k for k, _ in entries], code


def _entries(
    registry_path: Path, proj: Path, spec: str
) -> tuple[list[tuple[tuple[str, str], str | None]], int]:
    """Run ``id generate -e SPEC``; the non-file entries saved (key, sha256),
    as loaded back, and the exit code."""
    args = _build_parser().parse_args(
        ["id", "generate", "--project-dir", str(proj), "-o", str(registry_path)]
        + ["-e", spec]
    )
    code = _run_id_command(args)
    loaded = IdRegistry.load(registry_path)
    return (
        sorted(
            (k, entry.sha256)
            for k, entry in loaded.elements.items()
            if k[0] != FILE_TYPE
        ),
        code,
    )


@pytest.mark.parametrize(
    ("spec", "key", "info", "hashed"),
    [
        ("data/t.txt" + _DS, "data/t.txt", False, "file"),
        ("./data/t.txt" + _DS, "data/t.txt", True, "file"),
        ("../proj/data/t.txt" + _DS, "data/t.txt", True, "file"),
        ("data" + _DS, "data", False, "dir"),
        ("./data/" + _DS, "data", True, "dir"),
        ("data/missing.txt" + _DS, "data/missing.txt", False, "not found"),
        ("../other/x.txt" + _DS, "../other/x.txt", False, "outside the project"),
    ],
    ids=[
        "same",
        "dot",
        "sibling-dotdot",
        "dir",
        "dir-slash",
        "missing",
        "outside",
    ],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_entity_dataset_path_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    spec: str,
    key: str,
    info: bool,
    hashed: str | None,
) -> None:
    """An existing dataset path is stored as its key, one INFO if changed,
    with its digest (a file's SHA-256, a directory's Merkle root); a
    dataset keyed by its name is pinned with no hash and one INFO saying
    why; nothing warns."""
    proj = tmp_path / "proj"
    (proj / "data").mkdir(parents=True)
    (proj / "data" / "t.txt").write_bytes(b"x\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "x.txt").write_bytes(b"x\n")
    monkeypatch.chdir(tmp_path / "other")
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")

    entries, code = _entries(tmp_path / "reg.json", proj, spec)

    digest = {
        "file": _SHA,
        "dir": hash_dataset(proj / "data", max_bytes=1 << 20).hex_digest,
    }.get(str(hashed))
    assert code == 0
    assert [(name, sha) for (_, name), sha in entries] == [(key, digest)]
    stored = [r.getMessage() for r in caplog.records if "stored as" in r.getMessage()]
    assert len(stored) == int(info)
    without = [r.getMessage() for r in caplog.records if _WITHOUT in r.getMessage()]
    expected = [] if digest or hashed is None else [f"ID registry: dataset {key}"]
    assert [w.split(f" {_WITHOUT}: ")[0] for w in without] == expected
    assert all(str(hashed) in w for w in without)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_entity_dataset_absolute_inside_root(tmp_path: Path) -> None:
    """An absolute path inside the root becomes a relative key."""
    proj = tmp_path / "proj"
    (proj / "data").mkdir(parents=True)
    (proj / "data" / "t.txt").write_bytes(b"x\n")

    entities, code = _entities(
        tmp_path / "reg.json", proj, str(proj / "data" / "t.txt") + _DS
    )

    assert code == 0
    assert [name for _, name in entities] == ["data/t.txt"]


def _warns_yet_hashes(
    registry: IdRegistry, path: Path, *, max_bytes: int
) -> DatasetDigest:
    """A hashing that logs a warning and still gives a digest."""
    del registry, path, max_bytes
    logging.getLogger(dataset_hash.__name__).warning("FILE=x: odd but read")
    return DatasetDigest("file", _SHA, 1)


@pytest.mark.parametrize(
    ("name", "case", "reason"),
    [
        ("data/t.txt", "ceiling", "max-dataset-hash-bytes"),
        ("data", "ceiling", "max-dataset-hash-bytes"),
        ("empty", "empty", "nothing to hash"),
        ("data/t.txt", "warns-yet-hashes", None),
    ],
    ids=["file-ceiling", "dir-ceiling", "empty-dir", "warns-yet-hashes"],
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_entity_dataset_unhashed_is_a_hashless_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
    case: str,
    reason: str | None,
) -> None:
    """A dataset the hash refuses (ceiling) or that has nothing to hash is
    pinned with no hash and one ``ID registry:`` INFO naming its key and
    why, the hashing's own warning taken into it; a hashing that warns yet
    gives a digest stores it, its warning passed on as is."""
    proj = tmp_path / "proj"
    (proj / "data").mkdir(parents=True)
    (proj / "empty").mkdir()
    (proj / "data" / "t.txt").write_bytes(b"x\n")
    if case == "ceiling":
        monkeypatch.setattr("pitloom.cli._id_entity._pin_hash_ceiling", lambda: 1)
    elif case == "warns-yet-hashes":
        monkeypatch.setattr("pitloom.cli._id_entity.dataset_digest", _warns_yet_hashes)

    with caplog.at_level(logging.INFO, logger="pitloom"):
        entries, code = _entries(tmp_path / "reg.json", proj, f"./{name}{_DS}")

    assert code == 0
    pinned = [(n, sha) for (_, n), sha in entries]
    without = [r for r in caplog.records if _WITHOUT in r.getMessage()]
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    if reason is None:
        assert (pinned, without) == ([(name, _SHA)], [])
        assert warnings == ["FILE=x: odd but read"]
        return
    assert pinned == [(name, None)]
    (info,) = without
    assert info.levelno == logging.INFO
    assert info.getMessage().startswith(f"ID registry: dataset {name} {_WITHOUT}: ")
    assert reason in info.getMessage()
    assert not warnings


@pytest.mark.parametrize("change", [None, b"y\n"], ids=["same", "changed"])
def test_entity_dataset_pin_rerun(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, change: bytes | None
) -> None:
    """``-e`` again on the same content keeps the id; on other content,
    the pin is re-minted with the new digest ("content changed")."""
    proj = tmp_path / "proj"
    (proj / "data").mkdir(parents=True)
    target = proj / "data" / "t.txt"
    target.write_bytes(b"x\n")
    registry_path = tmp_path / "reg.json"
    _entries(registry_path, proj, "data/t.txt" + _DS)
    first = IdRegistry.load(registry_path).get(DATASET_PACKAGE_TYPE, "data/t.txt")
    if change is not None:
        target.write_bytes(change)
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")

    _entries(registry_path, proj, "data/t.txt" + _DS)

    second = IdRegistry.load(registry_path).get(DATASET_PACKAGE_TYPE, "data/t.txt")
    assert first is not None and second is not None
    assert (second.spdx_id == first.spdx_id) is (change is None)
    assert second.sha256 == hashlib.sha256(change or b"x\n").hexdigest()
    changed = [
        r
        for r in caplog.records
        if "content changed" in r.getMessage() and first.spdx_id in r.getMessage()
    ]
    assert len(changed) == int(change is not None)


@pytest.mark.parametrize(
    ("spec", "key", "info"),
    [
        ("m/x.bin", "m/x.bin", None),
        ("./m/x.bin", "m/x.bin", "stored as m/x.bin"),
        ("user/repo", None, "stored by name: used only by a model with no file"),
        ("m", None, "stored by name: used only by a model with no file"),
        ("../other/x.txt", None, "stored by name: used only by a model with no file"),
        ("m/x.bin:" + FILE_TYPE, "m/x.bin", None),
        ("./m/x.bin:" + FILE_TYPE, "m/x.bin", "stored as m/x.bin"),
        ("m/none.bin:" + FILE_TYPE, None, "stored by name: not found"),
        (
            "../other/x.txt:" + FILE_TYPE,
            None,
            "stored by name: outside the project root",
        ),
        ("m:" + FILE_TYPE, None, "stored by name: not a regular file"),
        ("requests:" + PACKAGE_TYPE, None, None),
    ],
    ids=["model", "model-dot", "model-hf", "model-dir", "model-outside"]
    + ["file", "file-dot", "file-missing", "file-outside", "file-dir", "package"],
)
def test_entity_model_or_file_path_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    spec: str,
    key: str | None,
    info: str | None,
) -> None:
    """A model or a file that is a regular file below the root is stored by
    its path key with its SHA-256, the key every lookup of it uses (one INFO
    when spelt otherwise); else by name, hash-less, one INFO saying why. A
    package is stored as given, silently."""
    proj = tmp_path / "proj"
    (proj / "m").mkdir(parents=True)
    (proj / "data").mkdir()
    (proj / "m" / "x.bin").write_bytes(b"x\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "x.txt").write_bytes(b"x\n")
    monkeypatch.chdir(tmp_path / "other")
    caplog.set_level(logging.INFO, logger="pitloom.id_registry")
    text, _, type_name = spec.partition(":")
    type_name = type_name or AI_PACKAGE_TYPE

    _, code = _entries(tmp_path / "reg.json", proj, spec)

    loaded = IdRegistry.load(tmp_path / "reg.json")
    stored = loaded.get(type_name, key or text)
    assert code == 0 and stored is not None
    assert stored.sha256 == (_SHA if key else None)
    assert key in (None, text) or loaded.get(type_name, text) is None
    said = [m for m in caplog.messages if m.startswith("ID registry: -e ")]
    assert said == ([] if info is None else [f"ID registry: -e {text} {info}"])
