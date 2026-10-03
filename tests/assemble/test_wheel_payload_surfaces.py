# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every wheel surface lists the same payload and the same package Merkle
root: ``loom wheel``, ``loom embed-wheel`` and ``loom wheel --embed``.

See also: tests/extract/test_wheel_payload.py (the filter and the root).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import run_cli

_DI = "demo_pkg-1.0.0.dist-info/"
_EXTRA = {
    f"{_DI}licenses/LICENSE": b"MIT\n",
    "demo_pkg/mod.py": b"mod = 1\n",
    "demo_pkg/vendored-2.0.dist-info/METADATA": b"vendored\n",
}
_PAYLOAD = {
    "demo_pkg/__init__.py",
    "demo_pkg/mod.py",
    "demo_pkg/vendored-2.0.dist-info/METADATA",
}


@pytest.fixture(autouse=True)
def _fixed_creation_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


def _graph(sbom: str) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom)["@graph"]
    return graph


def _embedded(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        (name,) = [n for n in zf.namelist() if "/sboms/" in n]
        return zf.read(name).decode("utf-8")


def _surfaces(tmp_path: Path, mp: pytest.MonkeyPatch, wheel: Path) -> dict[str, str]:
    """The SBOM each surface gives for its own copy of *wheel*."""
    tmp_path.mkdir(exist_ok=True)
    out = tmp_path / "out.spdx3.json"
    run_cli(["wheel", str(wheel), "--offline", "-o", str(out)], mp)
    sboms = {"wheel": out.read_text(encoding="utf-8")}
    for key, argv in {
        "embed-wheel": ["embed-wheel"],
        "wheel-embed": ["wheel", "--embed", "--offline"],
    }.items():
        copy = tmp_path / key / wheel.name
        copy.parent.mkdir()
        shutil.copy(wheel, copy)
        run_cli([*argv[:1], str(copy), *argv[1:]], mp)
        sboms[key] = _embedded(copy)
    return sboms


def _package_root(sbom: str) -> str:
    (package,) = [e for e in _graph(sbom) if e["type"] == "software_Package"]
    (root,) = package["verifiedUsing"]
    return str(root["hashValue"])


def _reference_root(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as zf:
        leaves = [
            hashlib.sha256(zf.read(n)).digest()
            for n in sorted(zf.namelist())
            if not n.startswith(_DI)
        ]
    while len(leaves) > 1:
        leaves = [
            hashlib.sha256(leaves[i] + leaves[i + 1]).digest()
            if i + 1 < len(leaves)
            else leaves[i]
            for i in range(0, len(leaves), 2)
        ]
    return leaves[0].hex()


def test_every_surface_lists_the_same_payload_and_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "src", extra_members=_EXTRA)
    with zipfile.ZipFile(wheel) as zf:
        # Not vacuous: the dist-info files the SBOMs must not list exist.
        assert {f"{_DI}METADATA", f"{_DI}RECORD", f"{_DI}licenses/LICENSE"} <= set(
            zf.namelist()
        )
    expected_root = _reference_root(wheel)

    sboms = _surfaces(tmp_path, monkeypatch, wheel)

    assert sboms.keys() == {"wheel", "embed-wheel", "wheel-embed"}
    for key, sbom in sboms.items():
        names = {
            e["name"]
            for e in _graph(sbom)
            if e["type"] == "software_File" and e["software_fileKind"].endswith("file")
        }
        assert names == _PAYLOAD, key
        assert _package_root(sbom) == expected_root, key


def test_same_wheel_gives_identical_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _make_dummy_wheel(tmp_path / "src", extra_members=_EXTRA)
    first = _surfaces(tmp_path / "one", monkeypatch, wheel)
    second = _surfaces(tmp_path / "two", monkeypatch, wheel)

    assert first == second


@pytest.mark.parametrize("command", ["wheel", "embed-wheel"])
def test_wheel_without_payload_has_no_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    wheel = tmp_path / "demo_pkg-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(
            f"{_DI}METADATA", "Metadata-Version: 2.1\nName: demo_pkg\nVersion: 1.0.0\n"
        )
        zf.writestr(f"{_DI}WHEEL", "Wheel-Version: 1.0\n")
    out = tmp_path / "out.spdx3.json"

    if command == "wheel":
        run_cli(["wheel", str(wheel), "--offline", "-o", str(out)], monkeypatch)
        sbom = out.read_text(encoding="utf-8")
    else:
        run_cli(["embed-wheel", str(wheel)], monkeypatch)
        sbom = _embedded(wheel)

    graph = _graph(sbom)
    assert not [e for e in graph if e["type"] == "software_File"]
    (package,) = [e for e in graph if e["type"] == "software_Package"]
    assert not package.get("verifiedUsing")
