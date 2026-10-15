# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment element whose id an element of another type already holds is
never folded into it: both are kept, the fragment's one gets a new id in
the main document's namespace with one ``WARNING:``, and the fragment's
references to it follow (D11). A same-type id still folds.

See also: tests/core/test_fragments_merge_ids.py (re-declared ids of the
same type) and tests/assemble/test_fragments_unify.py (the helpers).
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_merged_sbom, generate_project_sbom
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._license_graph import fragment_graph, write_fragment
from tests.assemble.embed_surfaces_shared import demo_project, run_cli

_MAIN = "https://spdx.org/spdxdocs/main"
_FRAG = "https://spdx.org/spdxdocs/frag"
# A foreign (pre-v3) id that both documents happen to use.
_SHARED = "https://spdx.org/spdxdocs/shared#data"
_CLASH = "shares spdxId"
_FILE = "software_File"
_DATASET = "dataset_DatasetPackage"
_SHA = "a" * 64


def _element(type_name: str, spdx_id: str, **extra: Any) -> dict[str, Any]:
    """A serialised element: a dataset carries dataset-only fields."""
    element: dict[str, Any] = {"type": type_name, "spdxId": spdx_id, "name": "data"}
    if type_name == _DATASET:
        element["dataset_datasetType"] = ["text"]
        element["dataset_dataPreprocessing"] = ["lowercased"]
    return {**element, **extra}


def _trained_on(target: str) -> list[dict[str, Any]]:
    """A fragment model and its ``trainedOn`` *target*."""
    return [
        {"type": "ai_AIPackage", "spdxId": f"{_FRAG}#M", "name": "m"},
        {
            "type": "Relationship",
            "spdxId": f"{_FRAG}#R",
            "from": f"{_FRAG}#M",
            "to": [target],
            "relationshipType": "trainedOn",
        },
    ]


def _base(elements: list[dict[str, Any]]) -> Spdx3JsonExporter:
    """A base document in the ``_MAIN`` namespace holding *elements*."""
    document = {"type": "SpdxDocument", "spdxId": _MAIN, "name": "main"}
    data = json.dumps(fragment_graph([document, *elements], ns=_MAIN))
    objects = spdx3.SHACLObjectSet()
    spdx3.JSONLDDeserializer().read(io.BytesIO(data.encode()), objects)
    exporter = Spdx3JsonExporter()
    for obj in objects.objects:
        exporter.object_set.add(obj)
    return exporter


def _merge(
    tmp: Path,
    base: list[dict[str, Any]],
    fragment: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> tuple[str, list[str]]:
    """The merged document's JSON and its ``WARNING:`` messages."""
    exporter = _base(base)
    write_fragment(tmp / "f.spdx3.json", fragment_graph(fragment))
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        merge_fragments(tmp, [FragmentConfig(path="f.spdx3.json")], exporter)
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    return exporter.to_json(pretty=True), warnings


def _by_id(merged: str) -> dict[str, dict[str, Any]]:
    graph: list[dict[str, Any]] = json.loads(merged)["@graph"]
    return {e["spdxId"]: e for e in graph if "spdxId" in e}


def _sha(element: dict[str, Any]) -> dict[str, Any]:
    return {
        **element,
        "verifiedUsing": [{"type": "Hash", "algorithm": "sha256", "hashValue": _SHA}],
    }


@pytest.mark.parametrize(
    ("base_type", "frag_type"),
    [(_FILE, _DATASET), (_DATASET, _FILE)],
    ids=["base-file", "base-dataset"],
)
def test_id_held_by_another_type_keeps_both(
    base_type: str, frag_type: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = [_element(base_type, _SHARED)]
    fragment = [_element(frag_type, _SHARED), *_trained_on(_SHARED)]
    assert base[0]["spdxId"] == fragment[0]["spdxId"]
    assert base[0]["type"] != fragment[0]["type"]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    new_id = f"{_MAIN}#{frag_type.partition('_')[2]}-1"
    by_id = _by_id(merged)
    assert by_id[_SHARED]["type"] == base_type
    assert by_id[new_id]["type"] == frag_type
    dataset = by_id[_SHARED if base_type == _DATASET else new_id]
    assert dataset["dataset_datasetType"] == ["text"]
    assert dataset["dataset_dataPreprocessing"] == ["lowercased"]
    assert by_id[f"{_FRAG}#R"]["to"] == [new_id]
    assert warnings == [
        f"Merge: {frag_type} 'data' shares spdxId {_SHARED} with a {base_type}; "
        f"keeping both, it gets new id {new_id}."
    ]


def test_without_a_main_document_the_new_id_takes_the_ids_namespace(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    exporter = _base([_element(_FILE, _SHARED)])
    (document,) = [
        o for o in exporter.object_set.objects if isinstance(o, spdx3.SpdxDocument)
    ]
    exporter.object_set.objects.remove(document)
    write_fragment(
        tmp_path / "f.spdx3.json", fragment_graph([_element(_DATASET, _SHARED)])
    )
    with caplog.at_level(logging.WARNING):
        merge_fragments(tmp_path, [FragmentConfig(path="f.spdx3.json")], exporter)
    by_id = _by_id(exporter.to_json())
    new_id = f"{_SHARED.partition('#')[0]}#DatasetPackage-1"
    assert (by_id[_SHARED]["type"], by_id[new_id]["type"]) == (_FILE, _DATASET)


def test_same_type_id_still_folds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = [_element(_FILE, _SHARED)]
    fragment = [_element(_FILE, _SHARED, comment="from the fragment")]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    (file,) = [e for e in _by_id(merged).values() if e["type"] == _FILE]
    assert (file["spdxId"], file["comment"]) == (_SHARED, "from the fragment")
    assert not warnings


def test_type_clash_then_hash_folds_into_the_same_type(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A clash is resolved by the next criteria first: a hash match folds
    the element into its own type's survivor and needs no new id."""
    survivor = f"{_MAIN}#D"
    base = [_element(_FILE, _SHARED), _sha(_element(_DATASET, survivor))]
    fragment = [_sha(_element(_DATASET, _SHARED)), *_trained_on(_SHARED)]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    by_id = _by_id(merged)
    assert by_id[_SHARED]["type"] == _FILE
    assert [i for i, e in by_id.items() if e["type"] == _DATASET] == [survivor]
    assert by_id[f"{_FRAG}#R"]["to"] == [survivor]
    assert not [w for w in warnings if _CLASH in w]


@pytest.mark.parametrize(
    ("base_extra", "frag_extra", "expected"),
    [
        ([_element(_FILE, f"{_MAIN}#DatasetPackage-1")], [], 2),
        ([], [_element(_FILE, f"{_MAIN}#DatasetPackage-1")], 2),
        (
            [_element(_FILE, f"{_MAIN}#DatasetPackage-1")],
            [_element(_FILE, f"{_MAIN}#DatasetPackage-2")],
            3,
        ),
    ],
    ids=["base-holds-1", "fragment-holds-1", "both"],
)
def test_new_id_avoids_taken_ids(
    base_extra: list[dict[str, Any]],
    frag_extra: list[dict[str, Any]],
    expected: int,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    base = [_element(_FILE, _SHARED), *base_extra]
    fragment = [_element(_DATASET, _SHARED), *frag_extra]
    merged, warnings = _merge(tmp_path, base, fragment, caplog)
    by_id = _by_id(merged)
    assert by_id[f"{_MAIN}#DatasetPackage-{expected}"]["type"] == _DATASET
    assert len([w for w in warnings if _CLASH in w]) == 1
    ids = [e["spdxId"] for e in json.loads(merged)["@graph"] if "spdxId" in e]
    assert len(ids) == len(set(ids))


def test_two_clashes_in_one_fragment_get_distinct_ids(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Both renamed in the canonical order, so the elements' order in the
    fragment does not change the output."""
    ids = [f"{_SHARED}-1", f"{_SHARED}-2"]
    base = [_element(_FILE, i) for i in ids]
    fragment = [_element(_DATASET, i, name=i[-1]) for i in ids]
    outputs = []
    for n, elements in enumerate((fragment, fragment[::-1])):
        (tmp_path / str(n)).mkdir()
        outputs.append(_merge(tmp_path / str(n), base, elements, caplog))
    assert outputs[0] == outputs[1]
    merged, warnings = outputs[0]
    by_id = _by_id(merged)
    assert [by_id[f"{_MAIN}#DatasetPackage-{n}"]["name"] for n in (1, 2)] == [
        "1",
        "2",
    ]
    assert len([w for w in warnings if _CLASH in w]) == 2


def _lib_merge(tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_merged_sbom(tmp / "frags")


def _cli_merge(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "out.spdx3.json"
    run_cli(["merge", str(tmp / "frags"), "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


def _project_fragment(tmp: Path) -> Path:
    """The demo project with a fragment whose dataset takes the id of one of
    the project's files."""
    earlier = json.loads(generate_project_sbom(demo_project(tmp / "a"), offline=True))
    file_id = next(e["spdxId"] for e in earlier["@graph"] if e["type"] == _FILE)
    toml = '\n[tool.pitloom.fragment]\nfiles = ["frag.spdx3.json"]\n'
    project = demo_project(tmp / "b", toml)
    write_fragment(
        project / "frag.spdx3.json",
        fragment_graph([_element(_DATASET, file_id), *_trained_on(file_id)]),
    )
    return project


def _lib_project(tmp: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(_project_fragment(tmp), offline=True)


def _cli_project(tmp: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "out.spdx3.json"
    run_cli(["project", str(_project_fragment(tmp)), "--offline", "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


_SURFACES: dict[str, Callable[[Path, pytest.MonkeyPatch], str]] = {
    "lib-merge": _lib_merge,
    "cli-merge": _cli_merge,
    "lib-project": _lib_project,
    "cli-project": _cli_project,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_every_merge_surface_keeps_both(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``loom merge`` (a file fragment, then a dataset fragment) and a
    project's configured fragment, through the CLI and the library."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    file_frag = fragment_graph([_element(_FILE, _SHARED)], ns=f"{_FRAG}-a")
    write_fragment(tmp_path / "frags" / "a.spdx3.json", file_frag)
    write_fragment(
        tmp_path / "frags" / "b.spdx3.json",
        fragment_graph([_element(_DATASET, _SHARED), *_trained_on(_SHARED)]),
    )
    with caplog.at_level(logging.WARNING):
        merged = json.loads(_SURFACES[surface](tmp_path, monkeypatch))
    (clash,) = [r.getMessage() for r in caplog.records if _CLASH in r.getMessage()]
    assert clash.startswith(f"Merge: {_DATASET} 'data' shares spdxId ")
    (document,) = [e for e in merged["@graph"] if e["type"] == "SpdxDocument"]
    by_id = {e["spdxId"]: e for e in merged["@graph"] if "spdxId" in e}
    (dataset_id,) = [i for i, e in by_id.items() if e["type"] == _DATASET]
    assert dataset_id == f"{document['spdxId']}#DatasetPackage-1"
    assert by_id[dataset_id]["dataset_datasetType"] == ["text"]
    assert by_id[f"{_FRAG}#R"]["to"] == [dataset_id]
    shared = clash.split(" shares spdxId ")[1].split(" ")[0]
    assert by_id[shared]["type"] == _FILE
