# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The provenance a base model carries and a fragment's value for it: what
the readers write, equivalent values, a restated value, and provenance of an
unexpected shape.

See also: tests/assemble/test_fragments_generated.py (the replacement itself).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom.assemble.spdx3._fragments_generated import (
    _equivalent,
    generated_properties,
)
from pitloom.assemble.spdx3._fragments_model_names import ModelNames
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.assemble.spdx3.provenance import (
    build_provenance_comment,
    provenance_comment_line,
    provenance_comment_parts,
)
from pitloom.core.provenance import (
    GENERATED_METHODS,
    PROVENANCE_PROPERTY_FIELDS,
    parse_provenance_value,
)
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.ai_model import read_ai_model
from tests.assemble.test_fragments_generated import (
    _MODEL,
    _NS,
    _base,
    _creation_info,
    _levels,
    _merge,
    _statement,
)


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
        # Both spellings: a literal segment, and provenance_segment(x, "Method", "m").
        for m in re.findall(
            r'Method(?:: |",\s*")(\w+)', path.read_text(encoding="utf-8")
        )
    }
    says_generated = {m for m in written if "generated" in m or "derived" in m}
    assert says_generated == GENERATED_METHODS


@pytest.mark.parametrize(
    ("old", "new", "same"),
    [
        pytest.param(["a", "b"], ["b", "a"], True, id="reordered"),
        pytest.param(["a"], ["a", "b"], False, id="subset"),
        pytest.param(1, 2, False, id="number"),  # neither a list nor text
        pytest.param('{"a":1,"b":2}', '{"b": 2, "a": 1}', True, id="json"),
        pytest.param("{not json", "{other", False, id="both-invalid"),
        pytest.param("x", "x", True, id="same"),
    ],
)
def test_equivalent_values_say_the_same_thing(
    old: object, new: object, same: bool
) -> None:
    """A reordered list or the same JSON in another spelling is the same;
    text that is not JSON, or another type, is compared as different (the
    JSON rules are tested in ``test_fragments_equal.py``)."""
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


def test_a_replaced_generated_value_says_which_was_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The ``INFO:`` names the fragment's value as kept and the generated
    one as dropped, not the other way round."""
    base = _base({"description": "generated_from_labels"})
    _, records, _ = _merge(tmp_path, caplog, base, [{"description": "curated"}])
    assert records[0][1].endswith("kept 'curated', dropped 'generated'")


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
    ("annotation", "comment", "replaced"),
    [
        # An entry that is no object says nothing: the generated comment stands
        # (read as a method, "other" would make the field not generated).
        (
            '{"description": "other"}',
            "description: Source: m | Method: generated_from_labels",
            True,
        ),
        (
            None,
            "description: Source: m | Method: generated_from_labels; description",
            True,
        ),
        # An object whose method is no text is a method nobody knows: not
        # generated, kept; it must not crash the merge (a list is unhashable).
        (
            '{"description": {"method": ["x"]}}',
            "description: Source: m | Method: generated_from_labels",
            False,
        ),
        (
            '{"description": {"method": {"a": 1}}}',
            "description: Source: m | Method: generated_from_labels",
            False,
        ),
    ],
    ids=["entry-not-an-object", "stray-part-named-like-a-field", "list", "object"],
)
def test_a_provenance_entry_of_an_unexpected_shape_is_read_with_care(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    annotation: str | None,
    comment: str,
    replaced: bool,
) -> None:
    """An entry that is no object, or a part with no source, says nothing and
    the value stays generated; a method that is no text counts as not
    generated, whatever its type."""
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
    assert (merged["description"], _levels(records)) == (
        ("curated", [logging.INFO]) if replaced else ("generated", [logging.WARNING])
    )


def test_the_comment_reader_and_writer_agree_on_the_format() -> None:
    """The line :func:`build_provenance_comment` writes is read back part by
    part, and another line is no provenance (one reader, one writer)."""
    line = build_provenance_comment(
        {"description": "Source: m | Method: x", "we;ird": "a; b"}
    )
    assert line is not None
    parts = provenance_comment_parts(line)
    assert parts is not None and len(parts) >= 2
    assert provenance_comment_line(parts) == line
    assert provenance_comment_parts("Other: description: x") is None
