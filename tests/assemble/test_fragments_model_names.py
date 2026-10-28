# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment's ``ai_AIPackage`` folding into the base document's model:
the name the fragments agree on wins with one ``INFO:``, and the base's
provenance for its own name goes; fragments that disagree keep the base's
name with today's ``Merge: conflicting`` warnings, whatever their order.

See also: tests/test_loom_model_name_surfaces.py (the
surfaces, with a real ``loom.run``), tests/assemble/test_fragments_count_note.py.
"""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3 import _fragments_model_names as names_module
from pitloom.assemble.spdx3._fragments_model_names import drop_comment_provenance
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.model_parameters import PARAMETER_COUNT_NOTE
from pitloom.export.spdx3_json import Spdx3JsonExporter, sha256_hash
from tests._license_graph import fragment_graph, write_fragment

_NS = "https://spdx.org/spdxdocs/base"
_MODEL = f"{_NS}#M"
_DIGEST = "ab" * 32
_PROV = (
    "Metadata provenance: name: Source: Pitloom generator | Method: file_name_stem"
    "; inputs: Source: m.safetensors"
)
_NAME_ONLY = '{"fields":{"name":{"method":"file_name_stem"}},"kind":"fields",'
_FIELDS_SCHEMA = '"schema":"https://pitloom.dev/provenance/fields/1"}'


def _base(name: str, *, with_model: bool = True) -> Spdx3JsonExporter:
    """The base document: a model *name* with a count note, provenance in
    its comment and two Annotations (one of its name alone)."""
    ci = spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=[f"{_NS}#A"],
    )
    exporter = Spdx3JsonExporter()
    exporter.add_document(spdx3.SpdxDocument(spdxId=_NS, creationInfo=ci))
    exporter.add_agent(spdx3.Agent(spdxId=f"{_NS}#A", name="A", creationInfo=ci))
    if not with_model:
        return exporter
    model = spdx3.ai_AIPackage(
        spdxId=_MODEL,
        name=name,
        creationInfo=ci,
        comment=f"{PARAMETER_COUNT_NOTE}\n{_PROV}",
    )
    model.verifiedUsing = [sha256_hash(_DIGEST)]
    model.ai_hyperparameter = [spdx3.DictionaryEntry(key="parameters", value="1")]
    exporter.add_package(model)
    for n, statement in enumerate(
        (
            _NAME_ONLY + _FIELDS_SCHEMA,
            '{"fields":{"inputs":{"source":"m"},"name":{"method":"file_name_stem"}},'
            '"kind":"fields",' + _FIELDS_SCHEMA,
        )
    ):
        exporter.add_annotation(
            spdx3.Annotation(
                spdxId=f"{_NS}#Annotation-{n}",
                creationInfo=ci,
                annotationType=spdx3.AnnotationType.other,
                contentType="application/json",
                subject=_MODEL,
                statement=statement,
            )
        )
    return exporter


def _merge(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    names: list[str],
    base: Spdx3JsonExporter | None = None,
    model: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[tuple[int, str]], str]:
    """Merge into *base* (a model ``m``) one fragment per name, in order,
    re-declaring the model with the *model* fields (``None`` drops one);
    return the merged model, the ``Merge:`` records (level, message) and the
    merged document."""
    exporter = _base("m") if base is None else base
    configs = []
    for n, name in enumerate(names):
        fields = {
            "type": "ai_AIPackage",
            "spdxId": _MODEL,
            "name": name,
            "comment": f"from {name}",
            "verifiedUsing": [
                {"type": "Hash", "algorithm": "sha256", "hashValue": _DIGEST}
            ],
            **(model or {}),
        }
        path = f"f{n}.spdx3.json"
        element = {k: v for k, v in fields.items() if v is not None}
        write_fragment(tmp_path / path, fragment_graph([element]))
        configs.append(FragmentConfig(path=path))
    caplog.clear()
    with caplog.at_level(logging.INFO):
        merge_fragments(tmp_path, configs, exporter)
    merged = exporter.to_json()
    graph = json.loads(merged)["@graph"]
    models = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert len(models) == 1
    records = [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if "Merge:" in r.getMessage()
    ]
    return {**models[0], "@annotations": _annotations(graph)}, records, merged


def _annotations(graph: list[dict[str, Any]]) -> list[str]:
    return sorted(e["statement"] for e in graph if e["type"] == "Annotation")


def _info(kept: str, dropped: str) -> tuple[int, str]:
    return (
        logging.INFO,
        f"Merge: 'name' on ai_AIPackage {_MODEL}: keeping the fragment's "
        f"{kept!r}, dropping the project's {dropped!r}.",
    )


def _warning(kept: str, dropped: str) -> tuple[int, str]:
    return (
        logging.WARNING,
        f"Merge: conflicting 'name' on ai_AIPackage {_MODEL} {kept!r}: "
        f"keeping {kept!r}, dropping {dropped!r}.",
    )


@pytest.mark.parametrize(
    ("names", "kept", "records"),
    [
        (["loomed"], "loomed", [_info("loomed", "m")]),
        (["m"], "m", []),
        (["loomed", "loomed"], "loomed", [_info("loomed", "m")]),
        (["x", "y"], "m", [_warning("m", "x"), _warning("m", "y")]),
        (["y", "x"], "m", [_warning("m", "x"), _warning("m", "y")]),
        (["m", "x"], "m", [_warning("m", "x")]),
    ],
    ids=[
        "renamed",
        "equal",
        "fragments-agree",
        "disagree",
        "disagree-rev",
        "one-agrees",
    ],
)
def test_the_name_kept(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    names: list[str],
    kept: str,
    records: list[tuple[int, str]],
) -> None:
    model, got, _ = _merge(tmp_path, caplog, names)
    assert model["name"] == kept
    assert got == records
    comment = model["comment"].split("\n")
    assert comment[0] == PARAMETER_COUNT_NOTE
    renamed = kept != "m"
    # The base's provenance of its own name goes with it: the comment entry
    # and the Annotation field (an Annotation of it alone too).
    assert ("name: Source: Pitloom generator" in model["comment"]) is not renamed
    assert sum('"name":' in a for a in model["@annotations"]) == (0 if renamed else 2)
    assert len(model["@annotations"]) == (1 if renamed else 2)
    assert "inputs: Source: m.safetensors" in comment[1]
    assert any('"inputs":' in a for a in model["@annotations"])
    for name in dict.fromkeys(names):
        assert f"from {name}" in model["comment"]


@pytest.mark.parametrize(
    "names", [["m", "x", "y"], ["m", "x"]], ids=["disagree", "one-agrees"]
)
def test_fragment_order_gives_the_same_bytes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, names: list[str]
) -> None:
    """Commentless fragments: the fragments' comments join in fold order,
    as on any element."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    bare = {"comment": None}
    forward = _merge(tmp_path / "a", caplog, names, model=bare)
    backward = _merge(tmp_path / "b", caplog, names[::-1], model=bare)
    assert forward[1:] == backward[1:]
    assert forward[1]


@pytest.mark.parametrize(
    ("base_name", "fragment_id", "kept", "levels"),
    [
        ("m", "https://spdx.org/spdxdocs/frag#M", "loomed", [logging.INFO]),
        ("dir/loomed", _MODEL, "dir/loomed", []),
    ],
    ids=["sha256-fold", "same-path-deeper"],
)
def test_other_folds(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    base_name: str,
    fragment_id: str,
    kept: str,
    levels: list[int],
) -> None:
    model, records, _ = _merge(
        tmp_path, caplog, ["loomed"], _base(base_name), {"spdxId": fragment_id}
    )
    assert model["name"] == kept
    assert [level for level, _ in records] == levels


def test_no_base_model_keeps_the_field_merge(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``loom merge``: every model is a fragment's, the earlier one is kept."""
    no_model = _base("m", with_model=False)
    model, records, _ = _merge(tmp_path, caplog, ["m", "loomed"], no_model)
    assert model["name"] == "m"
    assert [level for level, _ in records] == [logging.WARNING]
    assert "conflicting 'name'" in records[0][1]


def test_a_fragment_only_model_is_kept_silently(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    exporter = _base("m")
    model = {"type": "ai_AIPackage", "spdxId": "urn:other", "name": "loomed"}
    write_fragment(tmp_path / "f.spdx3.json", fragment_graph([model]))
    with caplog.at_level(logging.INFO):
        merge_fragments(tmp_path, [FragmentConfig(path="f.spdx3.json")], exporter)
    graph = json.loads(exporter.to_json())["@graph"]
    names = sorted(e["name"] for e in graph if e["type"] == "ai_AIPackage")
    assert names == ["loomed", "m"]
    assert not [r for r in caplog.records if "Merge:" in r.getMessage()]


_LINE = "Metadata provenance: "


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        (f"{_LINE}a: x; name: y; b: z", f"{_LINE}a: x; b: z"),
        (f"note\n{_LINE}name: y", "note"),
        (f"{_LINE}name: y", None),
        (f"{_LINE}named: y; general.name: z", f"{_LINE}named: y; general.name: z"),
        ("name: y; plain text", "name: y; plain text"),
        (None, None),
    ],
    ids=["middle", "line-goes", "all-goes", "other-fields", "not-provenance", "none"],
)
def test_drop_comment_provenance(comment: str | None, expected: str | None) -> None:
    assert drop_comment_provenance(comment, "name") == expected


@pytest.mark.parametrize(
    "statement",
    [
        '{"fields":{"name":{}},"kind":"fields","schema":"https://example.org/x"}',
        '{"fields":["name"],' + _FIELDS_SCHEMA,
        "name: not JSON",
    ],
    ids=["other-schema", "fields-not-a-map", "not-json"],
)
def test_other_annotations_are_left_alone(statement: str) -> None:
    annotation = spdx3.Annotation(statement=statement)
    assert names_module._drop_annotation_field(annotation, "name") is annotation
    assert annotation.statement == statement


def test_a_nameless_fragment_model_renames_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model, records, _ = _merge(tmp_path, caplog, ["unused"], model={"name": None})
    assert model["name"] == "m"
    assert not records


def test_a_comment_of_the_old_name_alone_goes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _base("m")
    package = base.object_set.find_by_id(_MODEL)
    assert isinstance(package, spdx3.ai_AIPackage)
    package.comment = "Metadata provenance: name: Source: Pitloom generator"
    del package.ai_hyperparameter
    model, _, _ = _merge(tmp_path, caplog, ["loomed"], base, {"comment": None})
    assert model["name"] == "loomed"
    assert "comment" not in model
