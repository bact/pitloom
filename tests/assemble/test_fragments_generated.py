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

from pitloom.assemble.spdx3._fragments_generated import (
    _agreed,
    _equivalent,
    generated_properties,
)
from pitloom.assemble.spdx3._fragments_model_names import ModelNames
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
    name: str | None = "m",
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
        creationInfo=ci,
        description=description,
        ai_domain=["d0"],
        ai_informationAboutApplication='{"outputs":["x"]}',
    )
    if name is not None:
        model.name = name
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
    [
        "not json",
        "[1, 2]",
        '{"fields": [1], "schema": "x"}',
        '{"fields": {}}',
        # A disagreeing method that would end "generated" if the schema
        # (Pitloom's own) were not required.
        '{"fields": {"description": {"method": "other"}}}',
        '{"fields": {"description": {"method": "other"}}, "schema": "x"}',
    ],
    ids=[
        "malformed",
        "not-an-object",
        "fields-not-an-object",
        "no-schema",
        "no-schema-with-fields",
        "foreign-schema",
    ],
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


def test_a_base_model_with_no_name_loses_its_generated_provenance_too(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The name is no condition: the fragment's name fills the empty one, as
    before, and the generated value is replaced like any other."""
    base = _base({"description": "generated_from_labels"}, name=None)
    model, records, annotations = _merge(
        tmp_path,
        caplog,
        base,
        [{"name": "n", "description": "curated", "comment": "FRAGMENT NOTE"}],
    )
    assert (model["name"], model["description"]) == ("n", "curated")
    assert "FRAGMENT NOTE" in model["comment"]  # the fragment's text survives
    assert _levels(records) == [logging.INFO]
    assert "description" not in _provenance_fields(model, annotations)


@pytest.mark.parametrize(
    ("sources", "agreed"),
    [
        ([{"a": "generated_from_labels"}, {"a": "derived_from_format"}], True),
        ([{"a": "generated_from_labels"}, {"a": None}], False),
        ([{"a": None}, {"a": "generated_from_labels"}], False),
        ([{"a": "generated_from_labels"}, {"b": None}], True),
        ([{"a": "other"}, {"a": "generated_from_labels"}], False),
    ],
    ids=["both-generated", "read-after", "read-before", "other-field", "other-method"],
)
def test_sources_that_disagree_read_a_field_as_not_generated_in_any_order(
    sources: list[dict[str, str | None]], agreed: bool
) -> None:
    """The Annotations come from a set: a field they disagree on must not
    depend on which is read last."""
    for order in (sources, sources[::-1]):
        assert (_agreed(order).get("a") in GENERATED_METHODS) is agreed


def test_two_annotations_that_disagree_give_the_same_result_every_time(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    results = set()
    for n in range(12):
        base = _base({"description": "generated_from_labels"})
        base.add_annotation(
            spdx3.Annotation(
                spdxId=f"{_NS}#Annotation-x{n}",
                creationInfo=_creation_info(),
                annotationType=spdx3.AnnotationType.other,
                contentType="application/json",
                subject=_MODEL,
                statement=_statement({"description": None}),
            )
        )
        model, records, _ = _merge(
            tmp_path / str(n), caplog, base, [{"description": "curated"}]
        )
        results.add((model["description"], tuple(_levels(records))))
    assert results == {("generated", (logging.WARNING,))}


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
    if model_file.startswith("fasttext"):
        pytest.importorskip("fasttext")  # the optional ``fasttext`` extra
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


@pytest.mark.parametrize(
    ("old", "new", "same"),
    [
        ('{"a":1,"b":2}', '{"b": 2, "a": 1}', True),  # JSON, another spelling
        ("{not json", "{other", False),  # neither parses: text differs
        ('{"a":1}', "{other", False),  # only one parses
        (["a", "b"], ["b", "a"], True),
        (["a"], ["a", "b"], False),
        (1, 2, False),  # neither a list nor text
        ('{"n":1}', '{"n":1.0}', False),  # another number is another value
        ('{"n":1}', '{"n":true}', False),  # and a boolean is no number
        ('{"a":1,"b":[1,2]}', '{"b":[1,2],"a":1}', True),  # key order
        ('{"a":1}', '{"a":1,"b":2}', False),  # a key more ...
        ('{"a":1,"b":2}', '{"a":1}', False),  # ... or less
        ("[" * 64 + "1" + "]" * 64, "[" * 64 + " 1" + "]" * 64, True),  # at the cap
        ("[" * 65 + "1" + "]" * 65, "[" * 65 + " 1" + "]" * 65, False),  # over it
        (
            '["\\"' + "[" * 80 + '"]',
            '["\\"' + "[" * 80 + '" ]',
            True,
        ),  # brackets after an escaped quote are still in the string
        ("[1e400]", "[2e999]", False),  # both overflow a float, to the same inf
        ("[0.1]", "[0.10000000000000000001]", False),  # float precision
        ('{"a":1}', '{"a":2,"a":1}', False),  # a repeated key: the last wins
        ("[" * 200_000 + "]" * 200_000, "[" * 200_000 + "] " + "]" * 199_999, False),
        ("x", "x", True),
    ],
    ids=[
        "json",
        "both-invalid",
        "one-invalid",
        "reordered",
        "subset",
        "number",
        "float",
        "boolean",
        "key-order",
        "key-more",
        "key-less",
        "depth-at-cap",
        "depth-over-cap",
        "brackets-in-string",
        "float-overflow",
        "float-precision",
        "repeated-key",
        "too-deep",
        "same",
    ],
)
def test_equivalent_values_say_the_same_thing(
    old: object, new: object, same: bool
) -> None:
    """Only a reordered list or the same JSON in another spelling is the same;
    text that is not JSON, or another type, is compared as different."""
    assert _equivalent(old, new) is same


@pytest.mark.parametrize("fragment_name", ["m.onnx", ""], ids=["depth", "empty"])
def test_a_fragment_name_that_renames_nothing_loses_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, fragment_name: str
) -> None:
    """The same file path at another depth, or an empty name, is no rename:
    with no generated provenance to drop, the base name stays and nothing is
    lost."""
    base = _base({}, comment=False, annotation=False, name="models/m.onnx")
    merged, records, annotations = _merge(
        tmp_path, caplog, base, [{"name": fragment_name}]
    )
    assert merged["name"] == "models/m.onnx"
    assert logging.WARNING not in _levels(records)
    assert not annotations


def test_provenance_of_a_model_the_base_lacks_is_not_dropped() -> None:
    """Only a base model has base provenance to drop: a model a fragment
    introduced is left alone, and nothing is queued for it."""
    ci = _creation_info()
    stranger = spdx3.ai_AIPackage(spdxId=f"{_NS}#Stranger", creationInfo=ci, name="s")
    names = ModelNames(Spdx3JsonExporter(), [])
    names.drop_provenance(stranger, "domain")
    names.finish()  # nothing registered, nothing to settle
    assert stranger.name == "s" and not stranger.comment


@pytest.mark.parametrize("order", ["RC", "CR"])
@pytest.mark.parametrize(
    ("restated", "curated", "key"),
    [
        ("generated", "curated", "description"),
        (["d1", "d0"], ["curated"], "ai_domain"),
        (["d0", "d1"], ["curated"], "ai_domain"),  # the same list, another order
        ('{"outputs": ["x"]}', '{"outputs":["y"]}', "ai_informationAboutApplication"),
    ],
    ids=["text", "list", "list-reordered", "json-respelt"],
)
def test_a_fragment_restating_a_generated_value_changes_nothing_in_any_order(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    order: str,
    restated: Any,
    curated: Any,
    key: str,
) -> None:
    """A fragment that says again what Pitloom generated (a ``loom model``
    fragment of the same file), in the same spelling or another, neither
    brings the replaced items back into a union nor earns a ``conflicting``
    warning, before or after the fragment that replaced it."""
    base = _base(
        {
            "domain": "derived_from_format",
            "description": "generated_from_labels",
            "outputs": "derived_from_format",
        }
    )
    base_model = next(
        o for o in base.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    )
    base_model.ai_domain = ["d1", "d0"]
    if key == "ai_informationAboutApplication":
        base_model.ai_informationAboutApplication = '{"outputs":["x"]}'
    fragments = {"R": {key: restated}, "C": {key: curated}}
    model, records, _ = _merge(tmp_path, caplog, base, [fragments[c] for c in order])
    assert model[key] == curated
    assert _levels(records) == [logging.INFO]


def _second_model(base: Spdx3JsonExporter, statement: dict[str, str | None]) -> str:
    """Add a base model ``M2`` with its own provenance Annotation; return its id."""
    ci = _creation_info()
    m2 = f"{_NS}#M2"
    base.add_package(spdx3.ai_AIPackage(spdxId=m2, creationInfo=ci, name="m2"))
    base.add_annotation(
        spdx3.Annotation(
            spdxId=f"{_NS}#Annotation-M2",
            creationInfo=ci,
            annotationType=spdx3.AnnotationType.other,
            contentType="application/json",
            subject=m2,
            statement=_statement(statement),
        )
    )
    return m2


@pytest.mark.parametrize(
    "other", [None, "generated_from_labels"], ids=["read", "generated"]
)
def test_another_base_models_provenance_neither_counts_nor_goes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, other: str | None
) -> None:
    """Only the Annotations whose subject is the model count towards its
    value being generated, and only those lose the replaced field: a second
    model with its own provenance is judged and kept by that."""
    base = _base({"description": "generated_from_labels"})
    m2 = _second_model(base, {"description": other})
    model, records, annotations = _merge(
        tmp_path, caplog, base, [{"description": "curated"}]
    )
    assert (model["description"], _levels(records)) == ("curated", [logging.INFO])
    own = [a for a in annotations if a["subject"] == m2]
    assert [list(json.loads(a["statement"])["fields"]) for a in own] == [
        ["description"]
    ]


@pytest.mark.parametrize(
    ("annotation", "comment"),
    [
        # An entry that is no object says nothing: the generated comment stands
        # (read as a method, "other" would make the field not generated).
        (
            '{"description": "other"}',
            "description: Source: m | Method: generated_from_labels",
        ),
        (None, "description: Source: m | Method: generated_from_labels; description"),
    ],
    ids=["entry-not-an-object", "stray-part-named-like-a-field"],
)
def test_a_provenance_entry_of_an_unexpected_shape_says_nothing(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    annotation: str | None,
    comment: str,
) -> None:
    """A malformed entry is skipped, not read as a method or as a vote against
    the value being generated: the value stays generated, and is replaced."""
    base = _base({}, annotation=False)
    model = next(
        o for o in base.object_set.objects if isinstance(o, spdx3.ai_AIPackage)
    )
    model.comment = "Metadata provenance: " + comment
    if annotation is not None:
        statement = {
            "schema": PitloomV1Encoder.schema_url,
            "kind": "fields",
            "fields": json.loads(annotation),
        }
        base.add_annotation(
            spdx3.Annotation(
                spdxId=f"{_NS}#Annotation-X",
                creationInfo=_creation_info(),
                annotationType=spdx3.AnnotationType.other,
                contentType="application/json",
                subject=_MODEL,
                statement=json.dumps(statement),
            )
        )
    merged, records, _ = _merge(tmp_path, caplog, base, [{"description": "curated"}])
    assert (merged["description"], _levels(records)) == ("curated", [logging.INFO])
