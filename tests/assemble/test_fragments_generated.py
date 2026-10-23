# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A fragment's value for a property Pitloom generated from the model file
(``Method: generated_from_labels``, ``Method: derived_from_format``) replaces
it, with one ``INFO:`` and the property's provenance dropped; a value read from
the file, and every other conflict, keeps the base's with today's
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

from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.fragments import merge_fragments
from pitloom.core.config import FragmentConfig
from pitloom.core.provenance import GENERATED_METHODS
from pitloom.export.spdx3_json import Spdx3JsonExporter
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
        element = {"type": "ai_AIPackage", "spdxId": _MODEL, "name": "m", **fields}
        path = f"f{n}.spdx3.json"
        write_fragment(tmp_path / path, fragment_graph([element]))
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
    assert "'description'" in records[0][1] and "'generated'" in records[0][1]
    # The generated value's provenance goes; the other field's stays.
    assert "description:" not in model["comment"]
    assert "framework:" in model["comment"]
    fields = json.loads(annotations[0]["statement"])["fields"]
    assert sorted(fields) == ["framework"]


@pytest.mark.parametrize(
    ("comment", "annotation"),
    [(True, False), (False, True)],
    ids=["comment-only", "annotation-only"],
)
def test_either_provenance_form_says_the_value_is_generated(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    comment: bool,
    annotation: bool,
) -> None:
    base = _base(
        {"description": "generated_from_labels"},
        comment=comment,
        annotation=annotation,
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
    base = _base({"domain": "derived_from_format"})
    model, records, _ = _merge(tmp_path, caplog, base, [{"ai_domain": ["curated"]}])
    assert model["ai_domain"] == ["curated"]
    assert _levels(records) == [logging.INFO]
    assert "domain:" not in model.get("comment", "")


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
        ({"outputs": "derived_from_format", "inputs": None}, False),
        ({"outputs": None, "inputs": "derived_from_format"}, False),
    ],
    ids=["outputs-generated", "inputs-read", "outputs-read"],
)
def test_a_property_two_fields_write_is_generated_only_when_both_are(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    methods: dict[str, str | None],
    replaced: bool,
) -> None:
    base = _base(methods)
    model, records, _ = _merge(
        tmp_path,
        caplog,
        base,
        [{"ai_informationAboutApplication": '{"outputs":["y"]}'}],
    )
    assert (model["ai_informationAboutApplication"] == '{"outputs":["y"]}') is replaced
    assert _levels(records) == ([logging.INFO] if replaced else [logging.WARNING])


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
