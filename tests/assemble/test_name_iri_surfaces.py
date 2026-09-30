# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model name that is not a valid IRI segment still yields valid ids.

Every surface -- ``loom model``, ``loom project`` (project scan) and
``pitloom.loom.run()`` -- emits a percent-encoded ``spdxId`` and keeps the
original text in ``name``; the ID registry round-trips the encoded id.

See also: tests/core/test_iri.py (the encoding rule itself).
"""

from __future__ import annotations

import json
import re
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__, loom
from pitloom.id_registry import IdRegistry
from tests._network import assert_spdx3_validate_ok

_TITLE = "Stable Diffusion XL #2/β"
_ENCODED = "Stable%20Diffusion%20XL%20%232%2Fβ"

# An IRI path segment or fragment: no space, control, "#", "/", "?", a bare
# "%" or an ASCII character outside RFC 3987 ipchar.
_IRI_PART = re.compile(r'(?:[^\x00-\x20\x7f-\x9f#/?%<>"{}|\\^`]|%[0-9A-F]{2})*')
_BASE = "https://spdx.org/spdxdocs/"


def _write_safetensors(path: Path, title: str) -> Path:
    """Write a minimal Safetensors file whose ``modelspec.title`` is *title*."""
    header: dict[str, Any] = {
        "__metadata__": {"modelspec.title": title},
        "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
    }
    raw = json.dumps(header).encode("utf-8")
    raw += b" " * (-len(raw) % 8)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\0\0\0\0")
    return path


def _cli(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0


def _model_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    model = _write_safetensors(tmp_path / "weights.safetensors", _TITLE)
    out = tmp_path / "model.spdx3.json"
    _cli(monkeypatch, "model", str(model), "-o", str(out))
    return out


def _project_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "proj"
    _write_safetensors(project / "src" / "demo" / "weights.safetensors", _TITLE)
    (project / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    out = tmp_path / "project.spdx3.json"
    _cli(monkeypatch, "project", str(project), "-o", str(out))
    return out


def _loom_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    del monkeypatch
    out = tmp_path / "run.spdx3.json"
    with loom.run(out):
        loom.set_model(_TITLE)
        loom.add_dataset(_TITLE)
    return out


_SURFACES: list[Any] = [
    pytest.param(_model_cli, id="loom-model"),
    pytest.param(_project_cli, id="loom-project"),
    pytest.param(_loom_run, id="loom-run"),
]

Surface = Callable[[Path, pytest.MonkeyPatch], Path]


def _graph(sbom: Path) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(sbom.read_bytes())["@graph"]
    return graph


@pytest.mark.parametrize("surface", _SURFACES)
def test_surface_emits_valid_iri_ids_and_keeps_the_name(
    surface: Surface, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _TITLE != _ENCODED  # the name really needs sanitising
    monkeypatch.chdir(tmp_path)
    graph = _graph(surface(tmp_path, monkeypatch))

    ids = [str(el["spdxId"]) for el in graph if "spdxId" in el]
    for spdx_id in ids:
        assert spdx_id.startswith(_BASE), spdx_id
        for part in spdx_id[len(_BASE) :].split("#", 1):
            assert _IRI_PART.fullmatch(part), spdx_id
    models = [el for el in graph if el.get("type") == "ai_AIPackage"]
    assert [el["name"] for el in models] == [_TITLE]
    assert _ENCODED in models[0]["spdxId"]


def test_registry_round_trips_an_encoded_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An encoded id harvested into the registry is reused, not re-minted.

    Via ``pitloom.loom.run()``, which looks the model up by its name. The
    stored id is renumbered first: the second run mints under the registry's
    namespace, so a fresh mint would also give ``AIPackage-1``.
    """
    monkeypatch.chdir(tmp_path)
    first = _loom_run(tmp_path, monkeypatch)
    registry_path = tmp_path / "reg.json"
    registry = IdRegistry.new("unused", path=registry_path)
    registry.import_sbom(first)
    registry.save()
    minted_id = registry.lookup_entity(_TITLE, "ai_AIPackage")
    assert minted_id is not None
    assert minted_id.startswith(f"{_BASE}{_ENCODED}-")
    assert minted_id.endswith("#AIPackage-1")
    model_id = minted_id[: -len("-1")] + "-7"
    raw = registry_path.read_text(encoding="utf-8")
    assert raw.count(minted_id) == 1
    registry_path.write_text(raw.replace(minted_id, model_id), encoding="utf-8")

    second = tmp_path / "again.spdx3.json"
    with loom.run(second, id_registry=registry_path):
        loom.set_model(_TITLE)
    models = [el for el in _graph(second) if el.get("type") == "ai_AIPackage"]
    assert [el["spdxId"] for el in models] == [model_id]


@pytest.mark.network
@pytest.mark.parametrize("surface", _SURFACES)
def test_surface_output_passes_spdx3_validate(
    surface: Surface, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert_spdx3_validate_ok(surface(tmp_path, monkeypatch))
