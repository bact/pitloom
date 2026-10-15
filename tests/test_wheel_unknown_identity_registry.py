# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A wheel whose name did not come from ``METADATA`` (no single own
``.dist-info``, or one without ``Name``) is called ``unknown``; that
placeholder is neither looked up in nor recorded into an ID registry, on
``loom wheel``, ``generate_wheel_sbom()`` and the embed's generator.

See also: tests/test_wheel_identity_surfaces.py (the identity itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import sys
import zipfile
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate_wheel_sbom
from pitloom.embed import embed_wheel_sbom
from pitloom.id_registry import PACKAGE_TYPE
from tests.registry_helpers import entries_of, make_registry

_PINNED = "https://example.org/pinned#Package-1"
_NAMELESS = "Metadata-Version: 2.1\nVersion: 1.0\n"


def _wheel(tmp_path: Path, stem: str, *, nameless: bool) -> Path:
    path = tmp_path / f"{stem}-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{stem}/__init__.py", "")
        if nameless:
            zf.writestr(f"{stem}-1.0.dist-info/METADATA", _NAMELESS)
    return path


def _main_id(sbom_json: str) -> str:
    graph = json.loads(sbom_json)["@graph"]
    (pkg,) = [e for e in graph if e["type"] == "software_Package"]
    return str(pkg["spdxId"])


def _packages(reg: Path) -> dict[str, str]:
    """The registry's software_Package entries, name -> id."""
    elements = json.loads(reg.read_text(encoding="utf-8"))["elements"]
    return {n: e["spdxId"] for n, e in elements.get(PACKAGE_TYPE, {}).items()}


def _cli(wheel: Path, registry: Path | None, mp: pytest.MonkeyPatch) -> str:
    out = wheel.with_suffix(".json")
    argv = ["loom", "wheel", str(wheel), "-o", str(out)]
    if registry is not None:
        argv += ["--id-registry", str(registry)]
    mp.setattr(sys, "argv", argv)
    assert __main__.main() == 0
    return out.read_text(encoding="utf-8")


def _library(wheel: Path, registry: Path | None, mp: pytest.MonkeyPatch) -> str:
    del mp
    return generate_wheel_sbom(wheel, id_registry=registry)


def _embed(wheel: Path, registry: Path | None, mp: pytest.MonkeyPatch) -> str:
    del mp
    return embed_wheel_sbom(wheel, id_registry=registry)[2]


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")


@pytest.mark.parametrize("surface", [_cli, _library], ids=["cli", "library"])
@pytest.mark.parametrize("nameless", [False, True], ids=["no-dist-info", "no-name"])
@pytest.mark.parametrize("declared", [True, False], ids=["declared", "undeclared"])
def test_placeholder_name_skips_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    surface: object,
    nameless: bool,
    declared: bool,
) -> None:
    reg = tmp_path / "reg.json"
    if declared:
        make_registry({(PACKAGE_TYPE, "unknown"): (_PINNED, None)}, path=reg)
    caplog.set_level(logging.INFO, logger="pitloom")
    ids = [
        _main_id(
            surface(  # type: ignore[operator]
                _wheel(tmp_path, stem, nameless=nameless),
                reg if declared else None,
                monkeypatch,
            )
        )
        for stem in ("a", "b")
    ]
    assert _PINNED not in ids
    if declared:
        assert _packages(reg) == {"unknown": _PINNED}
        assert caplog.text.count("package identity unknown") == 2
    else:
        assert not reg.exists()
        assert "package identity unknown" not in caplog.text


def test_embed_generator_skips_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg = tmp_path / "reg.json"
    make_registry({(PACKAGE_TYPE, "unknown"): (_PINNED, None)}, path=reg)
    sbom = _embed(_wheel(tmp_path, "a", nameless=True), reg, monkeypatch)
    assert _main_id(sbom) != _PINNED
    assert _packages(reg) == {"unknown": _PINNED}


def test_real_name_still_uses_registry(tmp_path: Path) -> None:
    reg = tmp_path / "reg.json"
    make_registry({(PACKAGE_TYPE, "a"): (_PINNED, None)}, path=reg)
    path = tmp_path / "a-1.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a-1.0.dist-info/METADATA", "Name: a\nVersion: 1.0\n")
        zf.writestr("a/__init__.py", "")
    assert _main_id(generate_wheel_sbom(path, id_registry=reg)) == _PINNED
    assert entries_of(make_registry(path=None)) == {}
