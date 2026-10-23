# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment's value for a property Pitloom generated from the model file
(``Method: generated_from_labels``, ``Method: derived_from_format``) replaces
it, with one ``INFO:`` and the property's provenance dropped; a value read from
the file, and every other conflict, keeps the base's with plain field merge's
``Merge: conflicting`` warning.

See also: tests/assemble/test_fragments_model_names.py (the same for a name).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_generated import generated_properties
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.provenance import (
    GENERATED_METHODS,
    PROVENANCE_PROPERTY_FIELDS,
    parse_provenance_value,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.ai_model import read_ai_model
from tests._license_graph import fragment_graph, write_fragment

_NS = "https://spdx.org/spdxdocs/base"
_MODEL = f"{_NS}#M"
_GEN = "Source: m.crfsuite | Field: labels CQDB | Method: generated_from_labels"
_DERIVED = "Source: m.crfsuite | Field: args.model | Method: derived_from_format"
_READ = "Source: m.crfsuite | Field: doc_string"


def _statement(fields: dict[str, str | None]) -> str:
    entries = {
        name: ({"method": method} if method else {"source": "m"})
        for name, method in fields.items()
    }
    return json.dumps(
        {"fields": entries, "kind": "fields", "schema": PitloomV1Encoder.schema_url}
    )


def _creation_info() -> spdx3.CreationInfo:
    return spdx3.CreationInfo(
        specVersion="3.0.1",
        created=datetime(2026, 1, 1, tzinfo=timezone.utc),
        createdBy=[f"{_NS}#A"],
    )


def _base(
    methods: dict[str, str | None],
    *,
    comment: bool = True,
    annotation: bool = True,
    description: str = "generated",
) -> Spdx3JsonExporter:
    """A base document with model ``M``: *description*, domain ``d0``, an
    ``outputs`` text, and provenance of the fields in *methods* in its comment
    and in one Annotation (each when asked for)."""
    ci = _creation_info()
    exporter = Spdx3JsonExporter()
    exporter.add_document(spdx3.SpdxDocument(spdxId=_NS, creationInfo=ci))
    exporter.add_agent(spdx3.Agent(spdxId=f"{_NS}#A", name="A", creationInfo=ci))
    model = spdx3.ai_AIPackage(
        spdxId=_MODEL,
        name="m",
        creationInfo=ci,
        description=description,
        ai_domain=["d0"],
        ai_informationAboutApplication='{"outputs":["x"]}',
    )
    if comment:
        parts = [
            f"{name}: {_provenance(name, method)}" for name, method in methods.items()
        ]
        model.comment = "Metadata provenance: " + "; ".join(parts)
    exporter.add_package(model)
    if annotation:
        exporter.add_annotation(
            spdx3.Annotation(
                spdxId=f"{_NS}#Annotation-0",
                creationInfo=ci,
                annotationType=spdx3.AnnotationType.other,
                contentType="application/json",
                subject=_MODEL,
                statement=_statement(methods),
            )
        )
    return exporter


def _provenance(name: str, method: str | None) -> str:
    return f"Source: m | Method: {method}" if method else f"Source: m | Field: {name}"


def _merge(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    base: Spdx3JsonExporter,
    fragments: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[tuple[int, str]], list[dict[str, Any]]]:
    """Merge one fragment per field set in *fragments* into *base*; return the
    model, the ``Merge:`` records (level, message) and the Annotations."""
    configs = []
    for n, fields in enumerate(fragments):
        fields = dict(fields)
        provenance = fields.pop("_provenance", None)
        element = {"type": "ai_AIPackage", "spdxId": _MODEL, "name": "m", **fields}
        elements = [element]
        if provenance is not None:  # the fragment's own provenance Annotation
            elements.append(
                {
                    "type": "Annotation",
                    "spdxId": f"{_NS}#FA-{n}",
                    "annotationType": "other",
                    "contentType": "application/json",
                    "subject": _MODEL,
                    "statement": _statement(provenance),
                }
            )
        path = f"f{n}.spdx3.json"
        write_fragment(tmp_path / path, fragment_graph(elements))
        configs.append(FragmentConfig(path=path))
    caplog.clear()
    with caplog.at_level(logging.INFO):
        merge_fragments(tmp_path, configs, base)
    graph = json.loads(base.to_json())["@graph"]
    model = next(e for e in graph if e["type"] == "ai_AIPackage")
    records = [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if "Merge:" in r.getMessage()
    ]
    return model, records, [e for e in graph if e["type"] == "Annotation"]


def _provenance_fields(
    model: dict[str, Any], annotations: list[dict[str, Any]]
) -> set[str]:
    """The fields the model's comment and ``fields`` Annotations give
    provenance for."""
    comment = model.get("comment", "")
    found = {
        part.split(": ", 1)[0]
        for line in comment.split("\n")
        for part in line.removeprefix("Metadata provenance: ").split("; ")
        if ": " in part
    }
    for annotation in annotations:
        found |= set(json.loads(annotation["statement"]).get("fields", {}))
    return found


def _levels(records: list[tuple[int, str]]) -> list[int]:
    return [level for level, _ in records]


def test_a_fragment_description_replaces_a_generated_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _base({"description": "generated_from_labels", "framework": None})
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"description": "curated"}]
    )
    assert model["description"] == "curated"
    assert _levels(records) == [logging.INFO]
    assert "replacing the value generated from the model file" in records[0][1]
    assert "'description'" in records[0][1]
    # The generated value's provenance goes; the other field's stays.
    assert "description:" not in model["comment"]
    assert "framework:" in model["comment"]
    fields = json.loads(annotations[0]["statement"])["fields"]
    assert sorted(fields) == ["framework"]


@pytest.mark.parametrize("form", ["comment", "annotation"])
def test_either_provenance_form_says_the_value_is_generated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, form: str
) -> None:
    base = _base(
        {"description": "generated_from_labels"},
        comment=form == "comment",
        annotation=form == "annotation",
    )
    model, records, _ = _merge(tmp_path, caplog, base, [{"description": "curated"}])
    assert (model["description"], _levels(records)) == ("curated", [logging.INFO])


@pytest.mark.parametrize(
    ("methods", "fragment", "levels", "kept"),
    [
        # Read from the file, not generated: the base's value stays.
        ({"description": None}, "curated", [logging.WARNING], "generated"),
        ({"description": "semver_bit_packed"}, "c", [logging.WARNING], "generated"),
        # A generated value the fragment does not state, or states alike.
        ({"description": "generated_from_labels"}, None, [], "generated"),
        ({"description": "generated_from_labels"}, "generated", [], "generated"),
        # No provenance for it at all.
        ({"framework": None}, "curated", [logging.WARNING], "generated"),
        # The one case that replaces it.
        ({"description": "generated_from_labels"}, "c", [logging.INFO], "c"),
    ],
    ids=["read", "other-method", "silent", "equal", "no-provenance", "replaced"],
)
def test_only_a_differing_value_for_a_generated_one_replaces_it(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    methods: dict[str, str | None],
    fragment: str | None,
    levels: list[int],
    kept: str,
) -> None:
    fields = {} if fragment is None else {"description": fragment}
    model, records, _ = _merge(tmp_path, caplog, _base(methods), [fields])
    assert (model["description"], _levels(records)) == (kept, levels)


@pytest.mark.parametrize(
    "statement",
    ["not json", "[1, 2]", '{"fields": [1], "schema": "x"}', '{"fields": {}}'],
    ids=["malformed", "not-an-object", "fields-not-an-object", "no-schema"],
)
def test_an_annotation_that_is_no_provenance_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, statement: str
) -> None:
    """Another Annotation of the model, or a damaged one, neither stops nor
    fakes the generated mark the comment gives."""
    base = _base({"description": "generated_from_labels"})
    base.add_annotation(
        spdx3.Annotation(
            spdxId=f"{_NS}#Annotation-1",
            creationInfo=_creation_info(),
            annotationType=spdx3.AnnotationType.other,
            contentType="application/json",
            subject=_MODEL,
            statement=statement,
        )
    )
    model, records, _ = _merge(tmp_path, caplog, base, [{"description": "curated"}])
    assert (model["description"], _levels(records)) == ("curated", [logging.INFO])


def test_a_stray_part_and_another_models_annotation_are_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A comment part with no ``field: source`` shape is skipped, and the
    Annotation of another element does not mark this model's value."""
    base = _base({"description": None})
    model = next(
        o for o in base.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    )
    model.comment = (
        "Metadata provenance: stray; " + str(model.comment).split(": ", 1)[1]
    )
    base.add_annotation(
        spdx3.Annotation(
            spdxId=f"{_NS}#Annotation-9",
            creationInfo=_creation_info(),
            annotationType=spdx3.AnnotationType.other,
            contentType="application/json",
            subject=f"{_NS}#A",
            statement=_statement({"description": "generated_from_labels"}),
        )
    )
    model_json, records, _ = _merge(tmp_path, caplog, base, [{"description": "x"}])
    assert (model_json["description"], _levels(records)) == (
        "generated",
        [logging.WARNING],
    )


@pytest.mark.parametrize("form", ["comment", "annotation", "both"])
def test_a_renamed_model_loses_its_generated_provenance_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, form: str
) -> None:
    """A fragment that renames the model and gives a description: the rename
    rebuilds the model's comment, and must not bring the dropped entry back."""
    base = _base(
        {"description": "generated_from_labels", "name": "file_name_stem"},
        comment=form != "annotation",
        annotation=form != "comment",
    )
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"name": "renamed", "description": "curated"}]
    )
    assert (model["name"], model["description"]) == ("renamed", "curated")
    assert _levels(records) == [logging.INFO, logging.INFO]
    assert not _provenance_fields(model, annotations) & {"description", "name"}


@pytest.mark.parametrize(
    "fields",
    [
        {"ai_domain": ["b", "a"]},
        {"ai_informationAboutApplication": '{ "inputs": [1], "outputs": ["x"] }'},
    ],
    ids=["list-order", "json-spelling"],
)
def test_the_same_value_in_another_spelling_replaces_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fields: dict[str, Any],
) -> None:
    base = _base({"domain": "derived_from_format", "outputs": "derived_from_format"})
    model = next(
        o for o in base.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    )
    model.ai_domain = ["a", "b"]
    model.ai_informationAboutApplication = '{"outputs":["x"],"inputs":[1]}'
    merged, records, annotations = _merge(tmp_path, caplog, base, [fields])
    # No replacement; the plain field merge says what it always did.
    assert logging.INFO not in _levels(records)
    assert merged["ai_domain"] == ["a", "b"]
    assert merged["ai_informationAboutApplication"] == '{"outputs":["x"],"inputs":[1]}'
    assert _provenance_fields(merged, annotations) >= {"domain", "outputs"}


def test_an_empty_generated_value_is_filled_without_a_replacement_notice(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing was generated for an empty value: the fragment's is taken like
    any fragment value for an empty field, and the mark of it goes."""
    base = _base({"description": "generated_from_labels"}, description="")
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"description": "curated"}]
    )
    assert model["description"] == "curated"
    assert records == []
    assert "description" not in _provenance_fields(model, annotations)


@pytest.mark.parametrize(
    "extra",
    [{}, {"name": "renamed"}],
    ids=["no-rename", "rename"],
)
@pytest.mark.parametrize("form", ["comment", "both"])
def test_the_fragments_own_comment_text_is_never_taken_for_provenance(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, form: str, extra: dict[str, str]
) -> None:
    """A fragment comment is glued onto the base's provenance line; a part of
    it that reads ``domain: ...`` is the fragment's text, not an entry to drop."""
    base = _base(
        {"domain": "derived_from_format", "framework": None},
        annotation=form == "both",
    )
    fragment = {"ai_domain": ["curated"], "comment": "domain: sports; note", **extra}
    model, records, annotations = _merge(tmp_path, caplog, base, [fragment])
    assert model["ai_domain"] == ["curated"]
    assert "derived_from_format" not in model["comment"]
    assert "domain: sports; note" in model["comment"]
    assert "framework: " in model["comment"]
    assert _provenance_fields(model, annotations) >= {"framework"}
    assert "domain" not in {
        f for a in annotations for f in json.loads(a["statement"]).get("fields", {})
    }
    assert logging.INFO in _levels(records)


@pytest.mark.parametrize(
    ("fragment", "provenance"),
    [
        ({"name": "renamed"}, {"name": None}),
        ({"description": "curated"}, {"description": "generated_from_labels"}),
        (
            {"name": "renamed", "description": "curated"},
            {"description": None, "name": None},
        ),
    ],
    ids=["rename-only", "replace-only", "both"],
)
def test_a_fragments_own_provenance_annotation_is_kept(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fragment: dict[str, Any],
    provenance: dict[str, str | None],
) -> None:
    """Only the base's provenance of a replaced or renamed field goes: the
    fragment says where its own value came from, and that stands."""
    base = _base({"description": "generated_from_labels", "name": "file_name_stem"})
    _, _, annotations = _merge(
        tmp_path, caplog, base, [{**fragment, "_provenance": provenance}]
    )
    own = [a for a in annotations if a["spdxId"].startswith(f"{_NS}#FA-")]
    assert len(own) == 1
    assert sorted(json.loads(own[0]["statement"])["fields"]) == sorted(provenance)


def test_a_second_fragment_conflicts_with_the_first(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Once a fragment's value stands, the base's value is no longer generated."""
    base = _base({"description": "generated_from_labels"})
    model, records, _ = _merge(
        tmp_path, caplog, base, [{"description": "one"}, {"description": "two"}]
    )
    assert model["description"] == "one"
    assert _levels(records) == [logging.INFO, logging.WARNING]
    assert "keeping 'one', dropping 'two'" in records[1][1]


def test_a_generated_domain_is_replaced_not_unioned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _base({"domain": "derived_from_format", "framework": None})
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"ai_domain": ["curated"]}]
    )
    assert model["ai_domain"] == ["curated"]
    assert _levels(records) == [logging.INFO]
    assert "domain" not in _provenance_fields(model, annotations)


def test_a_read_domain_is_unioned_as_before(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _base({"domain": None})
    model, records, _ = _merge(tmp_path, caplog, base, [{"ai_domain": ["curated"]}])
    assert sorted(model["ai_domain"]) == ["curated", "d0"]
    assert records == []


@pytest.mark.parametrize(
    ("methods", "replaced"),
    [
        ({"outputs": "derived_from_format"}, True),
        ({"outputs": "derived_from_format", "inputs": "derived_from_format"}, True),
        ({"outputs": "derived_from_format", "inputs": None}, False),
        ({"outputs": None, "inputs": "derived_from_format"}, False),
    ],
    ids=["outputs-generated", "both-generated", "inputs-read", "outputs-read"],
)
def test_a_property_two_fields_write_is_generated_only_when_both_are(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    methods: dict[str, str | None],
    replaced: bool,
) -> None:
    base = _base({**methods, "framework": None})
    model, records, annotations = _merge(
        tmp_path,
        caplog,
        base,
        [{"ai_informationAboutApplication": '{"outputs":["y"]}'}],
    )
    assert (model["ai_informationAboutApplication"] == '{"outputs":["y"]}') is replaced
    assert _levels(records) == ([logging.INFO] if replaced else [logging.WARNING])
    # Replaced, every field that wrote it loses its provenance, in both forms.
    gone = set() if not replaced else set(methods)
    assert _provenance_fields(model, annotations) == (
        {"framework"} | (set(methods) - gone)
    )


@pytest.mark.parametrize(
    ("fields", "levels"),
    [
        ({"description": ""}, []),
        ({"ai_domain": []}, []),
        ({"description": "", "ai_domain": ["curated"]}, [logging.INFO]),
    ],
    ids=["empty-text", "empty-list", "empty-and-real"],
)
def test_an_empty_fragment_value_replaces_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fields: dict[str, Any],
    levels: list[int],
) -> None:
    base = _base(
        {"description": "generated_from_labels", "domain": "derived_from_format"}
    )
    model, records, _ = _merge(tmp_path, caplog, base, [fields])
    assert model["description"] == "generated"
    assert model["ai_domain"] == (["curated"] if levels else ["d0"])
    assert _levels(records) == levels


def test_two_properties_in_one_fold_give_one_info_each_in_a_fixed_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    base = _base(
        {"description": "generated_from_labels", "domain": "derived_from_format"}
    )
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"description": "c", "ai_domain": ["c"]}]
    )
    assert (model["description"], model["ai_domain"]) == ("c", ["c"])
    assert _levels(records) == [logging.INFO, logging.INFO]
    assert "'ai_domain'" in records[0][1] and "'description'" in records[1][1]
    assert not _provenance_fields(model, annotations) & {"description", "domain"}


@pytest.mark.parametrize(
    ("model_file", "expected"),
    [
        ("fasttext/sentimentdemo.bin", {"ai_domain", "ai_informationAboutApplication"}),
        (
            "crfsuite/complete.crfsuite",
            {"description", "ai_informationAboutApplication"},
        ),
    ],
    ids=["fasttext", "crfsuite"],
)
def test_the_readers_provenance_marks_the_properties_the_assembler_writes(
    model_file: str, expected: set[str]
) -> None:
    """What each reader writes as generated maps to the SPDX properties
    :data:`PROVENANCE_PROPERTY_FIELDS` names; a new generated field of a reader
    that is not in the map fails here (``type_of_model`` is read from the
    header, with its own method, and is not generated)."""
    path = Path(__file__).resolve().parents[1] / "fixtures" / "aimodels" / model_file
    provenance = read_ai_model(path).provenance
    methods = {
        k: parse_provenance_value(v).get("method") for k, v in provenance.items()
    }
    written = {name for name, method in methods.items() if method in GENERATED_METHODS}
    mapped = set().union(*PROVENANCE_PROPERTY_FIELDS.values())
    assert written <= mapped
    assert generated_properties(methods) == expected


def test_the_generated_methods_are_the_ones_the_readers_write() -> None:
    """Every ``Method:`` a reader writes that says a value was generated or
    derived is a generated one, and each generated one is still written."""
    root = Path(__file__).resolve().parents[2] / "src" / "pitloom" / "extract"
    written = {
        m
        for path in root.rglob("*.py")
        for m in re.findall(r"Method: (\w+)", path.read_text(encoding="utf-8"))
    }
    says_generated = {m for m in written if "generated" in m or "derived" in m}
    assert says_generated == GENERATED_METHODS
