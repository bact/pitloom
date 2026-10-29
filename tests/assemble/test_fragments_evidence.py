# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``not_measured`` provenance entry goes when a merge gives its element
the value (from every Annotation and the comment, one ``INFO:`` each), stays
when no value arrives, and the result does not depend on the fold order or
the surface.

See also: tests/assemble/test_fragments_model_names.py (the drop helpers'
first user) and tests/assemble/test_fragments_count_note.py (comment merges).
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble import generate_project_sbom
from pitloom.assemble.spdx3 import _fragments_props as props
from pitloom.assemble.spdx3._fragments_evidence import drop_superseded_absences
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.assemble.spdx3.provenance import build_provenance_comment
from pitloom.core.config import FragmentConfig
from pitloom.core.evidence import NOT_MEASURED, evidence_segment
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from pitloom.export.spdx3_json import Spdx3JsonExporter
from tests._license_graph import fragment_graph, write_fragment
from tests.assemble.embed_surfaces_shared import demo_project, demo_wheel, run_cli
from tests.extract.conftest import make_hook

_NS = "https://spdx.org/spdxdocs/base"
_D = "https://spdx.org/spdxdocs/data#D"
_DIGEST = "ab" * 32
_ABSENT = f"Source: d | {evidence_segment(NOT_MEASURED, 'over-cap')}"
#: The base's provenance: the hash and the size not measured, the name read.
_PROVENANCE = {
    "name": "Source: d | Method: x",
    "verified_using": _ABSENT,
    "byte_size": _ABSENT,
}
_HASH = [{"type": "Hash", "algorithm": "sha256", "hashValue": _DIGEST}]


def _annotation(spdx_id: str, provenance: dict[str, str]) -> dict[str, Any]:
    """A ``fields`` provenance Annotation of the dataset, as written."""
    return {
        "type": "Annotation",
        "spdxId": spdx_id,
        "annotationType": "other",
        "contentType": "application/json",
        "subject": _D,
        "statement": PitloomV1Encoder().encode(provenance),
    }


def _dataset(name: str = "d", **fields: Any) -> dict[str, Any]:
    return {
        "type": "dataset_DatasetPackage",
        "spdxId": _D,
        "name": name,
        "dataset_datasetType": ["text"],
        **fields,
    }


def _absent(name: str = "d", **fields: Any) -> list[dict[str, Any]]:
    """The dataset with no hash or size, its provenance in comment and
    Annotation."""
    comment = build_provenance_comment(_PROVENANCE)
    return [
        _dataset(name, comment=comment, **fields),
        _annotation(f"{_NS}#Annotation-1", _PROVENANCE),
    ]


def _creation_info() -> spdx3.CreationInfo:
    return spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=[f"{_NS}#A"],
    )


def _envelope() -> Spdx3JsonExporter:
    """A document with no dataset (``loom merge``'s starting point)."""
    ci = _creation_info()
    exporter = Spdx3JsonExporter()
    exporter.add_document(spdx3.SpdxDocument(spdxId=_NS, creationInfo=ci))
    exporter.add_agent(spdx3.Agent(spdxId=f"{_NS}#A", name="A", creationInfo=ci))
    return exporter


def _merge(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fragments: list[list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[str], str]:
    """Merge *fragments* (``f0``, ``f1``, ...) into :func:`_envelope`;
    return the dataset with its Annotations' ``fields``, the ``Merge:``
    messages and the merged document."""
    for n, elements in enumerate(fragments):
        write_fragment(tmp_path / f"f{n}.json", fragment_graph(elements))
    exporter = _envelope()
    caplog.clear()
    with caplog.at_level(logging.INFO):
        merge_fragments(
            tmp_path,
            [FragmentConfig(path=f"f{n}.json") for n in range(len(fragments))],
            exporter,
        )
    merged = exporter.to_json()
    graph = json.loads(merged)["@graph"]
    (dataset,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    dataset["@fields"] = sorted(
        field
        for e in graph
        if e["type"] == "Annotation"
        for field in json.loads(e["statement"])["fields"]
    )
    messages = [r.getMessage() for r in caplog.records if "Merge:" in r.getMessage()]
    return dataset, messages, merged


def _info(prop: str, field: str, name: str = "'d'") -> str:
    return (
        f"Merge: {prop!r} on dataset_DatasetPackage {_D} {name}: keeping the "
        f"merged value, dropping the not_measured provenance of {field!r}."
    )


_SIZE: dict[str, Any] = {"dataset_datasetSize": 42}
_BOTH: dict[str, Any] = {"verifiedUsing": _HASH, **_SIZE}


@pytest.mark.parametrize(
    ("supplied", "dropped"),
    [
        ({"verifiedUsing": _HASH}, ["verified_using"]),
        (_SIZE, ["byte_size"]),
        (_BOTH, ["verified_using", "byte_size"]),
        ({"description": "another field"}, []),
    ],
    ids=["hash", "size", "both", "no-value"],
)
@pytest.mark.parametrize("absent_first", [True, False], ids=["absent-first", "rev"])
def test_a_merged_value_drops_its_entry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    supplied: dict[str, Any],
    dropped: list[str],
    absent_first: bool,
) -> None:
    fragments = [_absent(), [_dataset(**supplied)]]
    dataset, messages, _ = _merge(
        tmp_path, caplog, fragments if absent_first else fragments[::-1]
    )
    props_of = {"verified_using": "verifiedUsing", "byte_size": "dataset_datasetSize"}
    assert messages == [_info(props_of[f], f) for f in dropped]
    for field in ("name", "verified_using", "byte_size"):
        kept = field not in dropped
        assert (field in dataset["@fields"]) is kept, field
        assert (f"{field}: Source: d" in dataset["comment"]) is kept, field
    lines = dataset["comment"].split("\n")
    assert any(
        line.startswith("Metadata provenance: name: Source: d") for line in lines
    )
    for prop in supplied:
        assert dataset[prop] == supplied[prop]


def test_the_fold_order_gives_the_same_bytes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``loom merge``: two listing orders of the same fragments."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    fragments = [_absent(), [_dataset(**_BOTH)]]
    forward = _merge(tmp_path / "a", caplog, fragments)
    backward = _merge(tmp_path / "b", caplog, fragments[::-1])
    assert forward[1:] == backward[1:]
    assert len(forward[1]) == 2
    assert forward[0]["@fields"] == ["name"]


@pytest.mark.parametrize("note", ["note", None], ids=["note", "provenance-only"])
def test_an_entry_alone_takes_its_annotation_and_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, note: str | None
) -> None:
    """A comment that was only the provenance line goes as a whole."""
    alone = {"verified_using": _ABSENT}
    line = build_provenance_comment(alone)
    absent = [
        _dataset(comment=line if note is None else f"{note}\n{line}"),
        _annotation(f"{_NS}#Annotation-1", alone),
    ]
    dataset, messages, merged = _merge(
        tmp_path, caplog, [absent, [_dataset(verifiedUsing=_HASH)]]
    )
    assert dataset.get("comment") == note
    assert not dataset["@fields"]
    assert f"{_NS}#Annotation-1" not in merged
    assert messages == [_info("verifiedUsing", "verified_using")]


def test_an_entry_at_another_level_stays(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The hash arrives with its own ``declared`` provenance; only the size
    was not measured, and no size arrives: nothing goes, nothing is said."""
    size_absent = {"byte_size": _ABSENT}
    declared = {"verified_using": "Source: pointer | Evidence: declared"}
    absent = [
        _dataset(comment=build_provenance_comment(size_absent)),
        _annotation(f"{_NS}#Annotation-1", size_absent),
    ]
    measured = [
        _dataset(verifiedUsing=_HASH, comment=build_provenance_comment(declared)),
        _annotation(f"{_NS}#Annotation-2", declared),
    ]
    dataset, messages, _ = _merge(tmp_path, caplog, [absent, measured])
    assert dataset["@fields"] == ["byte_size", "verified_using"]
    assert "verified_using: Source: pointer | Evidence: declared" in dataset["comment"]
    assert "byte_size: Source: d" in dataset["comment"]
    assert not messages


def test_a_newline_in_the_name_is_escaped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    name = "d\nINFO: forged"
    fragments = [_absent(name), [_dataset(name, verifiedUsing=_HASH)]]
    _, messages, _ = _merge(tmp_path, caplog, fragments)
    assert messages == [_info("verifiedUsing", "verified_using", repr(name))]
    assert "\n" not in messages[0]


def test_a_fragment_provenance_line_is_dropped_after_a_comment_merge(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The not-measuring fragment's comment, its provenance first, joins the
    other's comment on a line of its own, so the drop finds it."""
    measured = [_dataset(verifiedUsing=_HASH, comment="from f0")]
    dataset, messages, _ = _merge(tmp_path, caplog, [measured, _absent()])
    assert dataset["comment"].split("\n") == [
        "from f0",
        "Metadata provenance: name: Source: d | Method: x; byte_size: " + _ABSENT,
    ]
    assert messages == [_info("verifiedUsing", "verified_using")]


_LINE = build_provenance_comment({"a": "x"})


@pytest.mark.parametrize(
    ("canonical", "duplicate", "merged"),
    [
        ("note", _LINE, f"note\n{_LINE}"),
        (f"note\n{_LINE}", "from f", f"note\n{_LINE}\nfrom f"),
        (f"{_LINE}\nnote", "from f", f"{_LINE}\nnote; from f"),
        ("note", "from f", "note; from f"),
    ],
    ids=["provenance-second", "provenance-last", "provenance-earlier", "plain"],
)
def test_comment_separator(canonical: str, duplicate: str, merged: str) -> None:
    element = spdx3.software_Package(comment=canonical)
    props._merge_comment(element, canonical, duplicate)
    assert element.comment == merged


def _loom_merge(tmp: Path, fragments: Path, mp: pytest.MonkeyPatch) -> str:
    out = tmp / "out.spdx3.json"
    run_cli(["merge", str(fragments), "-o", str(out)], mp)
    return out.read_text(encoding="utf-8")


def _lib(_tmp: Path, project: Path, _mp: pytest.MonkeyPatch) -> str:
    return generate_project_sbom(project, offline=True)


def _hook(_tmp: Path, project: Path, _mp: pytest.MonkeyPatch) -> str:
    hook = make_hook(str(project), {})
    build_data: dict[str, Any] = {}
    hook.initialize("standard", build_data)
    try:
        return Path(build_data["sbom_files"][0]).read_text(encoding="utf-8")
    finally:
        hook.finalize("standard", build_data, "")


def _embed(tmp: Path, project: Path, _mp: pytest.MonkeyPatch) -> str:
    """``embed_wheel_sbom`` with the project (a Build SBOM): the JSON it
    embeds."""
    wheel = demo_wheel(tmp)
    overrides = ConfigOverrides(offline=True)
    return embed_wheel_sbom(wheel, project_dir=project, overrides=overrides)[2]


_SURFACES: dict[str, Callable[[Path, Path, pytest.MonkeyPatch], str]] = {
    "loom-merge": _loom_merge,
    "lib": _lib,
    "hook": _hook,
    "embed-wheel": _embed,
}


@pytest.mark.parametrize("surface", sorted(_SURFACES))
def test_every_surface_drops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str
) -> None:
    """The project build (library, hook) and ``loom merge`` share the drop;
    two runs give the same bytes."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    if surface == "loom-merge":
        target = tmp_path / "fragments"
    else:
        toml = '\n[tool.pitloom.fragment]\nfiles = ["f0.json", "f1.json"]\n'
        target = demo_project(tmp_path, toml)
    write_fragment(target / "f0.json", fragment_graph(_absent()))
    write_fragment(target / "f1.json", fragment_graph([_dataset(**_BOTH)]))
    runs = [_SURFACES[surface](tmp_path, target, monkeypatch) for _ in range(2)]
    assert runs[0] == runs[1]
    graph = json.loads(runs[0])["@graph"]
    (dataset,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert dataset["verifiedUsing"][0]["hashValue"] == _DIGEST
    assert dataset["dataset_datasetSize"] == 42
    assert NOT_MEASURED not in runs[0]
    assert "Source: d | Method: x" in dataset["comment"]


def test_the_merge_runs_the_drop_without_a_fragment_value(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Guard against a vacuous pass: the entry is there before the merge."""
    dataset, messages, merged = _merge(tmp_path, caplog, [_absent()])
    assert NOT_MEASURED in merged
    assert dataset["@fields"] == ["byte_size", "name", "verified_using"]
    assert not messages


def _base_with_value_and_entry(exporter: Spdx3JsonExporter) -> None:
    """Give *exporter* the dataset holding both its hash and the
    ``not_measured`` entry for it, in comment and Annotation (as a forged
    file name once made it)."""
    ci = _creation_info()
    alone = {"verified_using": _ABSENT}
    exporter.object_set.add(
        spdx3.dataset_DatasetPackage(
            spdxId=_D,
            name="d",
            creationInfo=ci,
            dataset_datasetType=[spdx3.dataset_DatasetType.text],
            comment=build_provenance_comment(alone),
            verifiedUsing=[
                spdx3.Hash(algorithm=spdx3.HashAlgorithm.sha256, hashValue=_DIGEST)
            ],
        )
    )
    exporter.object_set.add(
        spdx3.Annotation(
            spdxId=f"{_NS}#Annotation-1",
            creationInfo=ci,
            annotationType=spdx3.AnnotationType.other,
            subject=_D,
            statement=PitloomV1Encoder().encode(alone),
        )
    )
    exporter.object_set.create_index()


@pytest.mark.parametrize(
    "fragments",
    [[], [[{"type": "software_Package", "spdxId": f"{_NS}#P", "name": "p"}]]],
    ids=["no-fragment", "unrelated-fragment"],
)
def test_no_merge_into_the_element_leaves_its_entry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fragments: list[list[dict[str, Any]]],
) -> None:
    """Only a fragment merged into an element supersedes its entry: a
    base element no fragment merged with keeps both, and nothing is said."""
    for n, elements in enumerate(fragments):
        write_fragment(tmp_path / f"f{n}.json", fragment_graph(elements))
    exporter = _envelope()
    _base_with_value_and_entry(exporter)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        merged = merge_fragments(
            tmp_path,
            [FragmentConfig(path=f"f{n}.json") for n in range(len(fragments))],
            exporter,
        )
    assert merged == len(fragments)
    graph = json.loads(exporter.to_json())["@graph"]
    (dataset,) = [e for e in graph if e["type"] == "dataset_DatasetPackage"]
    assert dataset["comment"] == build_provenance_comment({"verified_using": _ABSENT})
    assert any(e.get("spdxId") == f"{_NS}#Annotation-1" for e in graph)
    assert not [r for r in caplog.records if "Merge:" in r.getMessage()]


def test_the_drop_pass_reindexes_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Many emptied Annotations among many objects: one reindex for the
    pass, not one per Annotation (which made 200 drops take 33 s)."""
    exporter = _envelope()
    ci = _creation_info()
    objects = exporter.object_set.objects
    datasets = []
    for i in range(100):
        spdx_id = f"{_NS}#D{i}"
        datasets.append(
            spdx3.dataset_DatasetPackage(
                spdxId=spdx_id,
                name=f"d{i}",
                creationInfo=ci,
                verifiedUsing=[
                    spdx3.Hash(
                        algorithm=spdx3.HashAlgorithm.sha256, hashValue=f"{i:064x}"
                    )
                ],
            )
        )
        objects.add(datasets[-1])
        objects.add(
            spdx3.Annotation(
                spdxId=f"{_NS}#Annotation-{i}",
                creationInfo=ci,
                annotationType=spdx3.AnnotationType.other,
                subject=spdx_id,
                statement=PitloomV1Encoder().encode({"verified_using": _ABSENT}),
            )
        )
    for i in range(300):
        objects.add(spdx3.software_File(spdxId=f"{_NS}#F{i}", creationInfo=ci))
    exporter.object_set.create_index()
    calls: list[None] = []
    reindex = exporter.object_set.create_index

    def counted() -> None:
        calls.append(None)
        reindex()

    monkeypatch.setattr(exporter.object_set, "create_index", counted)
    with caplog.at_level(logging.INFO):
        drop_superseded_absences(exporter, datasets)
    assert len(calls) == 1
    assert not [o for o in objects if isinstance(o, spdx3.Annotation)]
    assert exporter.object_set.find_by_id(f"{_NS}#Annotation-0") is None
    assert len([r for r in caplog.records if "Merge:" in r.getMessage()]) == 100
