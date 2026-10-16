# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``loom model`` and ``loom enrich`` with a registry on the model
document's namespace: a mint never takes an id the registry holds for
another key, yet the model's and its model card datasets' own held ids
(``id import``) stay, so no id flaps across runs.

See also: tests/core/generator/test_generator_registry_reserve_held.py
(the reservation per document builder), surfaces_base.py (``_run_cli``).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pitloom.assemble import enrich_model, generate_model_sbom
from pitloom.id_registry import (
    AI_PACKAGE_TYPE,
    DATASET_PACKAGE_TYPE,
    IdRegistry,
    RegistryEntry,
)
from tests.id_registry.surfaces_base import _run_cli

_AI = AI_PACKAGE_TYPE
_DATASET = DATASET_PACKAGE_TYPE
_DATA = "data/t.txt"
_NPY = Path(__file__).parents[1] / "fixtures" / "aimodels" / "numpy"


@pytest.fixture(name="model_dir")
def _model_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixed_epoch: None
) -> Path:
    del fixed_epoch  # pins `created`: runs compare as bytes
    (tmp_path / "data").mkdir()
    (tmp_path / _DATA).write_bytes(b"rows\n")
    (tmp_path / "m.npy").write_bytes((_NPY / "example-model-v1.npy").read_bytes())
    (tmp_path / "README.md").write_bytes(b"---\ndatasets: [imdb]\n---\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _model_cli(monkeypatch: pytest.MonkeyPatch, out: str, *flags: str) -> bytes:
    assert _run_cli(monkeypatch, ["model", "m.npy", "-o", out, *flags]) == 0
    return Path(out).read_bytes()


def _ids(sbom: bytes | str, type_name: str) -> dict[str, str]:
    graph = json.loads(sbom)["@graph"]
    return {e["name"]: e["spdxId"] for e in graph if e["type"] == type_name}


def _all_ids(sbom: bytes | str) -> list[str]:
    return sorted(e.get("spdxId") or e["@id"] for e in json.loads(sbom)["@graph"])


@pytest.mark.parametrize(
    ("first_flags", "imdb_n"),
    [((), 2), (("--enrich",), 1)],
    ids=["pin-first", "card-imported"],
)
def test_model_card_dataset_never_takes_a_held_dataset_id(
    model_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_flags: tuple[str, ...],
    imdb_n: int,
) -> None:
    """The R5 repro: ``id import`` gives the registry the model document's
    namespace, ``-e`` pins ``data/t.txt`` there, then ``model --enrich``
    mints the model card's dataset: never the pin. When the first run
    already had it (``card-imported``), it keeps its imported id. CLI and
    library agree; an ``id import`` of the output changes no id."""
    first = _model_cli(monkeypatch, "p0.json", *first_flags)
    for argv in (["import", "p0.json"], ["generate", "-e", f"{_DATA}:{_DATASET}"]):
        assert _run_cli(monkeypatch, ["id", *argv, "-o", "reg.json"]) == 0
    pin = IdRegistry.load(model_dir / "reg.json").get(DATASET_PACKAGE_TYPE, _DATA)
    assert pin is not None

    out = _model_cli(monkeypatch, "out1.json", "--enrich", "--id-registry", "reg.json")
    library = generate_model_sbom("m.npy", enrich=True, id_registry="reg.json")
    assert _run_cli(monkeypatch, ["id", "import", "out1.json", "-o", "reg.json"]) == 0
    again = _model_cli(
        monkeypatch, "out2.json", "--enrich", "--id-registry", "reg.json"
    )

    assert out == again
    assert _all_ids(library) == _all_ids(out)  # the CLI adds a comment
    imdb = _ids(out, _DATASET)["imdb"]
    assert imdb.endswith(f"#DatasetPackage-{imdb_n}")
    assert imdb != pin.spdx_id
    assert imdb.split("#")[0] == pin.spdx_id.split("#")[0]  # one namespace
    assert _ids(out, _AI) == _ids(first, _AI)


def test_model_and_enrich_skip_a_model_id_held_for_other_content(
    model_dir: Path,
) -> None:
    """The model's path key holds the first run's id for other content (a
    retrained model): ``model`` and ``enrich`` both mint past it, so the
    fragment's references still name the document's model."""
    (held,) = _ids(generate_model_sbom("m.npy"), _AI).values()
    registry = IdRegistry.new("m", namespace=held.split("#")[0], project_root=model_dir)
    registry.elements[(AI_PACKAGE_TYPE, "m.npy")] = RegistryEntry(held, "0" * 64)
    registry.save(model_dir / "reg.json")

    sbom = generate_model_sbom("m.npy", enrich=True, id_registry="reg.json")
    fragment = enrich_model("m.npy", id_registry="reg.json")

    (model_id,) = _ids(sbom, _AI).values()
    assert model_id != held
    assert set(re.findall(r'"([^"]*#AIPackage-[^"]*)"', fragment)) == {model_id}
