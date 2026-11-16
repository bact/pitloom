# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_credentials` on what an id or a
written value can hide: a reference field naming an IRI no element defines,
an id built from a percent-encoded name, a format character Pitloom's
provenance writes as an escape, a key that is a URL in a pointer; and an
SBOM to embed that names one key twice.

See also: tests/export/test_spdx3_credentials.py (every other field read).
"""

from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from spdx_python_model.bindings.v3_0_1 import model as spdx_model

from pitloom import loom
from pitloom.assemble import ConfigOverrides, embed_wheel_sbom, generate_merged_sbom
from pitloom.assemble.spdx3 import provenance as assemble_provenance
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.provenance import provenance_note
from pitloom.export._spdx3_credentials import (
    REFERENCE_FIELDS,
    URL_FIELDS,
    GraphFinding,
    check_graph_credentials,
    find_graph_credentials,
)
from pitloom.messages import code_of
from tests._author_routes import write_wheel

_SECRET = "S3CRET"
_URL = f"https://u:{_SECRET}@h.example/x"
_REFUSED = "credentials-unsafe/refused"


def _one(graph: list[dict[str, Any]]) -> GraphFinding:
    """The one finding of *graph*."""
    found = find_graph_credentials(graph)
    assert len(found) == 1, found
    return found[0]


def _object_props() -> set[str]:
    """Every compact name of an ``ObjectProp`` (a reference or an object
    inline) of the SPDX 3.0.1 bindings."""
    names: set[str] = set()
    for cls in vars(spdx_model).values():
        props = vars(cls).get("_OBJ_COMPACT_PROPS") if inspect.isclass(cls) else None
        for compact, prop in (props or {}).items():
            kind = prop.prop if prop.prop is not None else prop.reg()
            inner = kind.prop if isinstance(kind, spdx_model.ListProp) else kind
            if isinstance(inner, spdx_model.ObjectProp):
                names.add(compact)
    return names


def test_every_reference_field_of_the_model_is_read_as_an_id() -> None:
    names = _object_props()
    assert {"createdBy", "to", "subject", "creationInfo"} <= names
    assert names == REFERENCE_FIELDS
    assert all(URL_FIELDS[name].embedded for name in names)


@pytest.mark.parametrize(
    ("element", "pointer"),
    [
        ({"type": "CreationInfo", "@id": "_:ci", "createdBy": [_URL]}, "/createdBy/0"),
        ({"spdxId": "urn:p", "suppliedBy": f"urn:x:{_URL}"}, "/suppliedBy"),
        ({"spdxId": "urn:p", "originatedBy": [_URL]}, "/originatedBy/0"),
        ({"spdxId": "urn:p", "creationInfo": _URL}, "/creationInfo"),
        ({"spdxId": "urn:r", "from": "urn:p", "to": ["urn:q", _URL]}, "/to/1"),
        ({"spdxId": "urn:a", "subject": _URL}, "/subject"),
        ({"spdxId": "urn:d", "rootElement": [_URL]}, "/rootElement/0"),
    ],
    ids=["createdBy", "suppliedBy", "originatedBy", "creationInfo", "to"]
    + ["subject", "rootElement"],
)
def test_a_reference_naming_a_credentialed_iri_is_refused(
    element: dict[str, Any], pointer: str
) -> None:
    found = _one([element])
    assert found.pointer == pointer and not found.finding.weak


def test_an_inline_object_of_a_reference_field_is_walked_not_read() -> None:
    """``creationInfo`` inline: its own fields are read as they are."""
    element = {"spdxId": "urn:p", "creationInfo": {"comment": _URL}}
    assert not find_graph_credentials([element])


#: A dataset named by a URL, the id ``loom`` builds from it.
_ENCODED_ID = "https://spdx.org/spdxdocs/https:%2F%2Fu:S3CRET@h.example%2Fd.csv-1#P"


def test_an_id_built_from_a_percent_encoded_name_is_refused_and_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    graph = [{"spdxId": _ENCODED_ID}, {"spdxId": "urn:r", "subject": _ENCODED_ID}]
    found = _one(graph)
    assert found.pointer == "/spdxId" and _SECRET not in found.element
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        check_graph_credentials(graph, CredentialPolicy(refuse=True))
    assert caplog.messages and _SECRET not in caplog.text


@pytest.mark.platform
def test_a_loom_dataset_named_by_a_credentialed_url_is_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    out = tmp_path / "f.json"
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        with loom.run(str(out), credentials=CredentialPolicy(refuse=True)):
            loom.set_model("m")
            loom.add_dataset(f"hf://datasets/o/r?token={_SECRET}")
    assert code_of(caught.value) == _REFUSED and not out.exists()
    assert _SECRET not in caplog.text


def _fragment(tmp_path: Path, graph: list[dict[str, Any]]) -> Path:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    info = {
        "@id": "_:ci",
        "type": "CreationInfo",
        "created": "2026-03-01T10:00:00Z",
        "createdBy": ["https://ex.org/doc/Person/p1"],
        "specVersion": "3.0.1",
    }
    person = {
        "type": "Person",
        "spdxId": "https://ex.org/doc/Person/p1",
        "creationInfo": "_:ci",
        "name": "P",
    }
    doc = {"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"}
    doc["@graph"] = [info, person, *graph]  # type: ignore[assignment]
    (fragments / "a.json").write_text(json.dumps(doc), encoding="utf-8")
    return fragments


@pytest.mark.platform
@pytest.mark.parametrize(
    "extra",
    [
        {"suppliedBy": _URL},
        {"originatedBy": [_URL]},
        {"spdxId": "https://ex.org/doc/https:%2F%2Fu:S3CRET@h.example%2Fp"},
    ],
    ids=["suppliedBy", "originatedBy", "encoded-id"],
)
def test_merge_refuses_a_reference_or_an_encoded_id(
    extra: dict[str, Any], tmp_path: Path
) -> None:
    package = {
        "type": "software_Package",
        "spdxId": "https://ex.org/doc/Package/a",
        "creationInfo": "_:ci",
        "name": "a",
        **extra,
    }
    fragments = _fragment(tmp_path, [package])
    with pytest.raises(ValueError) as caught:
        generate_merged_sbom(
            fragments,
            output_path=tmp_path / "m.json",
            credentials=CredentialPolicy(refuse=True),
        )
    assert code_of(caught.value) == _REFUSED and not (tmp_path / "m.json").exists()


def _demo_wheel(tmp_path: Path) -> Path:
    return write_wheel(tmp_path, "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\n")


@pytest.mark.platform
@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",'
            ' "@graph": [{"type": "software_Package", "spdxId": "https://ex.org/p",'
            f' "name": "demo", "software_downloadLocation": "{_URL}",'
            ' "software_downloadLocation": "https://h.example/x"}]}',
            "sbom-invalid",
        ),
        (
            '{"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",'
            ' "@graph": [{"type": "software_Package", "spdxId": "https://ex.org/p",'
            f' "name": "demo", "suppliedBy": "{_URL}"}}]}}',
            _REFUSED,
        ),
    ],
    ids=["duplicate-key", "reference"],
)
def test_embed_wheel_sbom_refuses_what_it_would_embed(
    text: str, code: str, tmp_path: Path
) -> None:
    """A key given twice is refused: the check reads the last value, another
    reader of the embedded bytes may read the first."""
    sbom = tmp_path / "given.json"
    sbom.write_bytes(text.encode())
    wheel = _demo_wheel(tmp_path)
    before = wheel.read_bytes()
    with pytest.raises(ValueError) as caught:
        embed_wheel_sbom(
            wheel,
            sbom_path=sbom,
            overrides=ConfigOverrides(credentials=CredentialPolicy(refuse=True)),
        )
    assert code_of(caught.value) == code and wheel.read_bytes() == before
    assert _SECRET not in str(caught.value)


#: A requirement whose parameter name a client reads without its zero-width
#: space: the provenance note writes the space as an escape.
_ZWSP_DEP = f"foo @ https://h.example/x.whl?to\u200bken={_SECRET}"


def test_a_format_character_escaped_in_a_note_hides_no_credential(
    caplog: pytest.LogCaptureFixture,
) -> None:
    note = provenance_note(_ZWSP_DEP)
    assert "\\u200b" in note and "\u200b" not in note
    statement = PitloomV1Encoder().encode({"declared_constraint": note})
    comment = assemble_provenance.build_provenance_comment(
        {"declared_constraint": note}
    )
    graph: list[dict[str, Any]] = [
        {"spdxId": "urn:a", "contentType": "application/json", "statement": statement},
        {"spdxId": "urn:b", "comment": comment},
    ]
    found = find_graph_credentials(graph)
    assert [f.pointer for f in found] == [
        "/statement/fields/declared_constraint/note",
    ]
    # The comment states the same value: one finding, refused in either.
    assert found[0].value == note.removeprefix("Note: ")
    in_comment = _one(graph[1:])
    assert in_comment.value == found[0].value
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        check_graph_credentials(graph, CredentialPolicy(refuse=True))
    assert _SECRET not in caplog.text and "?token=***" in caplog.text


def test_a_key_that_is_a_url_shows_no_credential_in_a_pointer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A key holding ``/`` is masked before RFC 6901 writes it ``~1``,
    which the masker of the line no longer reads as a URL."""
    key = "https://alice:KEYSECRET9@h.example/f"
    statement = json.dumps(
        {
            "schema": PitloomV1Encoder.schema_url,
            "fields": {key: {"note": f"https://h.example/x?token={_SECRET}"}},
        }
    )
    graph = [
        {"spdxId": "urn:a", "contentType": "application/json", "statement": statement}
    ]
    found = _one(graph)
    assert found.pointer == "/statement/fields/https:~1~1***:***@h.example~1f/note"
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        check_graph_credentials(graph, CredentialPolicy(refuse=True))
    assert "KEYSECRET9" not in caplog.text
