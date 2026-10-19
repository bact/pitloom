# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every file whose bytes Pitloom reads carries its SHA-256 then its SHA-512
in ``verifiedUsing``, on every surface; what Pitloom did not read (a locked
dependency) or did not hash as one file (the main package's Merkle root)
stays SHA-256 only.

See also: tests/core/test_file_hash.py (the reader),
tests/hash_helpers.py (the expected hashes) and
tests/conformance/test_g7ai_surfaces.py (the cross-surface value parity).
"""

from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import loom
from pitloom.assemble import generate_project_sbom
from tests._spdx3_validate import assert_spdx3_valid
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.conformance.g7ai_shared import AIMODELS, BACKENDS, write_project
from tests.conformance.g7ai_surfaces import (
    MODEL_SURFACES,
    PROJECT_SURFACES,
    WHEEL_SURFACES,
    Runner,
    hook_surface,
)
from tests.hash_helpers import algorithms, file_hashes_json

_Graph = list[dict[str, Any]]
#: Builds the input in a temporary directory; gives it and its files' bytes
#: by element name (the model's under ``"<model>"``).
_Build = Callable[[Path], tuple[Path, dict[str, bytes]]]

_MODEL = AIMODELS / "safetensors/phi-tiny-random.safetensors"
_MERKLE = "Merkle root"


def _model(_tmp: Path) -> tuple[Path, dict[str, bytes]]:
    return _MODEL, {"<model>": _MODEL.read_bytes()}


def _project(tmp: Path) -> tuple[Path, dict[str, bytes]]:
    root = tmp / "proj"
    root.mkdir()
    write_project(root, BACKENDS["hatchling"])
    files = {
        name: (root / name).read_bytes()
        for name in ("demo/__init__.py", "demo/m.safetensors")
    }
    return root, {**files, "<model>": files["demo/m.safetensors"]}


def _wheel(tmp: Path) -> tuple[Path, dict[str, bytes]]:
    members = {
        "demo/__init__.py": b"x = 1\n",
        "demo/m.safetensors": safetensors_bytes(),
        # A bundled library: a phantom dependency of bytes Pitloom read.
        "demo.libs/libz.so": b"\x7fELF not really\n",
    }
    wheel = write_model_wheel(tmp / "dist", members)
    return wheel, {**members, "<model>": members["demo/m.safetensors"]}


def _sdist(tmp: Path) -> tuple[Path, dict[str, bytes]]:
    members = {
        "PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n",
        "pyproject.toml": b'[project]\nname = "demo"\nversion = "1.0.0"\n',
        "demo/__init__.py": b"x = 1\n",
        "demo/empty.py": b"",
    }
    sdist = tmp / "demo-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(f"demo-1.0.0/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    # A member is named under the sdist's top directory.
    return sdist, {f"demo-1.0.0/{name}": data for name, data in members.items()}


_SDIST_SURFACES = {k: v for k, v in PROJECT_SURFACES.items() if k != "cli-generate"}

CASES: list[tuple[str, _Build, dict[str, Runner]]] = [
    ("model", _model, MODEL_SURFACES),
    ("project", _project, PROJECT_SURFACES | {"hook": hook_surface}),
    ("wheel", _wheel, WHEEL_SURFACES),
    ("sdist", _sdist, _SDIST_SURFACES),
]
_RUNS = [
    (case, build, surface, run)
    for case, build, surfaces in CASES
    for surface, run in surfaces.items()
]


def _graph(sbom: str) -> _Graph:
    return [e for e in json.loads(sbom)["@graph"] if "verifiedUsing" in e]


def _is_merkle(element: dict[str, Any]) -> bool:
    return any(_MERKLE in h.get("comment", "") for h in element["verifiedUsing"])


def _assert_hashes(case: str, hashed: _Graph, contents: dict[str, bytes]) -> None:
    """Every hashed element of *case*'s SBOM *hashed* is checked: a file
    against its bytes in *contents*, the model and a bundled library
    against theirs, the Merkle root for SHA-256 only."""
    expected: dict[tuple[str, str | None], Any] = {
        ("software_File", name): file_hashes_json(data)
        for name, data in contents.items()
        if name != "<model>"
    }
    if "<model>" in contents:
        expected["ai_AIPackage", None] = file_hashes_json(contents["<model>"])
    if case == "wheel":
        expected["software_Package", "libz"] = file_hashes_json(
            contents["demo.libs/libz.so"]
        )
    merkle = [e for e in hashed if _is_merkle(e)]
    found = {
        (e["type"], None if e["type"] == "ai_AIPackage" else e["name"]): e[
            "verifiedUsing"
        ]
        for e in hashed
        if e not in merkle
    }
    assert found == expected
    assert [algorithms(e) for e in merkle] == [["sha256"]] * len(merkle)
    # An sdist's main package states no Merkle root, a model has none.
    assert len(merkle) == (case in ("project", "wheel"))


@pytest.mark.parametrize(
    ("case", "build", "surface", "run"),
    _RUNS,
    ids=[f"{case}-{surface}" for case, _b, surface, _r in _RUNS],
)
def test_every_read_file_has_both_hashes(
    case: str,
    build: _Build,
    surface: str,
    run: Runner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ``software_File``, the model's ``ai_AIPackage`` and a bundled
    library's package carry the SHA-256 and SHA-512 of the bytes it names,
    in that order; the main package's Merkle root stays SHA-256 only. The
    SBOM is schema- and SHACL-valid."""
    source, contents = build(tmp_path)
    scratch = tmp_path / "out"
    scratch.mkdir()
    sbom = run(source, scratch, monkeypatch)
    _assert_hashes(case, _graph(sbom), contents)
    path = tmp_path / f"{case}-{surface}.spdx3.json"
    path.write_text(sbom, encoding="utf-8")
    assert_spdx3_valid(path)


def test_a_locked_dependency_hash_stays_sha256_only(tmp_path: Path) -> None:
    """A dependency's hash is copied from its lock file, never computed:
    SHA-256 only, even when the lock also states a SHA-512; the project's
    own files, which Pitloom read, carry both."""
    sha256, sha512 = "a" * 64, "b" * 128
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\nversion = "1.0"\n'
        'dependencies = ["requests==2.31.0"]\n',
        encoding="utf-8",
    )
    (tmp_path / "pylock.toml").write_text(
        'lock-version = "1.0"\ncreated-by = "test"\n'
        '[[packages]]\nname = "requests"\nversion = "2.31.0"\n'
        'wheels = [{ name = "requests-2.31.0-py3-none-any.whl", '
        f'hashes = {{ sha256 = "{sha256}", sha512 = "{sha512}" }} }}]\n',
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_bytes(b"")
    hashed = _graph(generate_project_sbom(tmp_path, offline=True))
    (dependency,) = [e for e in hashed if e.get("name") == "requests"]
    assert dependency["verifiedUsing"] == [
        {"type": "Hash", "algorithm": "sha256", "hashValue": sha256}
    ]
    (own,) = [e for e in hashed if e.get("name") == "app/__init__.py"]
    assert own["verifiedUsing"] == file_hashes_json(b"")


def test_loom_hashes_its_model_dataset_and_script_both_ways(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loom SDK: the model's package, a file dataset's package and its
    ``software_File``, and the run's script, each with both hashes; a
    directory dataset's Merkle root, SHA-256 only. Valid."""
    monkeypatch.chdir(tmp_path)
    contents = {"m.bin": b"weights", "data.txt": b"rows\n", "train.py": b"run()\n"}
    for name, data in contents.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "a.txt").write_bytes(b"a\n")
    monkeypatch.setattr(
        "pitloom._loom_active_run._get_caller_script_path", lambda: "train.py"
    )
    output = tmp_path / "loom.spdx3.json"
    with loom.run(output):
        loom.set_model("m", path="m.bin")
        loom.add_dataset("data.txt")
        loom.add_dataset("corpus")
    hashed = _graph(output.read_text(encoding="utf-8"))
    by_name = {(e["type"], e["name"]): e for e in hashed}
    corpus = by_name.pop(("dataset_DatasetPackage", "corpus"))
    assert algorithms(corpus) == ["sha256"] and _is_merkle(corpus)
    assert {k: e["verifiedUsing"] for k, e in by_name.items()} == {
        ("ai_AIPackage", "m"): file_hashes_json(contents["m.bin"]),
        ("dataset_DatasetPackage", "data.txt"): file_hashes_json(contents["data.txt"]),
        ("software_File", "data.txt"): file_hashes_json(contents["data.txt"]),
        ("software_File", "train.py"): file_hashes_json(contents["train.py"]),
    }
    assert_spdx3_valid(output)
