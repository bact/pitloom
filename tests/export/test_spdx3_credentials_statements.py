# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_credentials` on the JSON
statements Pitloom writes (artifact metadata, conflicts, enrichments,
unifications, field provenance): every string in one is read as a whole
value, wherever it is nested; a statement of another schema is not. Also
the ``identifier`` of every ``externalIdentifierType``.

See also: tests/export/test_spdx3_credentials.py (every other field read)
and tests/export/test_spdx3_credentials_comment.py (the provenance comment).
"""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3 import provenance as assemble_provenance
from pitloom.assemble.spdx3._provenance_encoders import PitloomV1Encoder
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.export._spdx3_credentials import (
    PITLOOM_SCHEMA_PREFIX,
    check_graph_credentials,
    find_graph_credentials,
)
from pitloom.messages import code_of

_SECRET = "S3CRET"
_URL = f"https://u:{_SECRET}@h.example/x"
_A = assemble_provenance
_SCHEMAS = {
    "artifact-metadata": _A.ARTIFACT_METADATA_SCHEMA_URL,
    "conflict": _A.CONFLICT_SCHEMA_URL,
    "enrichment": _A.ENRICHMENT_SCHEMA_URL,
    "unification": _A.UNIFICATION_SCHEMA_URL,
    "fields": PitloomV1Encoder.schema_url,
}


def _element(statement: dict[str, Any]) -> dict[str, Any]:
    return {
        "spdxId": "urn:a",
        "type": "Annotation",
        "contentType": "application/json",
        "statement": json.dumps(statement),
    }


def test_every_schema_pitloom_writes_is_under_the_prefix_read() -> None:
    """A drift guard: a statement schema outside the prefix is never read."""
    assert all(url.startswith(PITLOOM_SCHEMA_PREFIX) for url in _SCHEMAS.values())


#: Each statement kind and leaf shape: the statement, the pointer refused.
_STATEMENTS: dict[str, tuple[dict[str, Any], str]] = {
    "artifact-metadata-scalar": (
        {"schema": _SCHEMAS["artifact-metadata"], "metadata": {"source_url": _URL}},
        "/statement/metadata/source_url",
    ),
    "artifact-metadata-list": (
        {"schema": _SCHEMAS["artifact-metadata"], "metadata": {"urls": ["a", _URL]}},
        "/statement/metadata/urls/1",
    ),
    "artifact-metadata-nested": (
        {
            "schema": _SCHEMAS["artifact-metadata"],
            "metadata": {"a/b~c": [{"deep": {"url": _URL}}]},
        },
        "/statement/metadata/a~1b~0c/0/deep/url",
    ),
    "conflict-candidate": (
        {
            "schema": _SCHEMAS["conflict"],
            "field": "homepage",
            "candidates": [
                {"source": "pyproject.toml", "value": "https://h.example/"},
                {"source": "PKG-INFO", "value": _URL},
            ],
        },
        "/statement/candidates/1/value",
    ),
    "enrichment-before": (
        {
            "schema": _SCHEMAS["enrichment"],
            "changes": [{"field": "homepage", "before": _URL, "after": "x"}],
        },
        "/statement/changes/0/before",
    ),
    "unification-fragment": (
        {"schema": _SCHEMAS["unification"], "fragments": [_URL]},
        "/statement/fragments/0",
    ),
    "fields-value-segment": (
        {"schema": _SCHEMAS["fields"], "fields": {"f": {"value": _URL}}},
        "/statement/fields/f/value",
    ),
}


@pytest.mark.parametrize("name", sorted(_STATEMENTS))
def test_each_string_of_a_pitloom_statement_is_refused_with_its_place(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    statement, pointer = _STATEMENTS[name]
    (found,) = find_graph_credentials([_element(statement)])
    assert (found.element, found.pointer, found.value) == ("urn:a", pointer, _URL)
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        check_graph_credentials([_element(statement)], CredentialPolicy())
    assert code_of(caught.value) == "credentials-unsafe/refused"
    assert _SECRET not in caplog.text


@pytest.mark.parametrize(
    "statement",
    [
        {"schema": _SCHEMAS["artifact-metadata"], "metadata": {"d": f"See {_URL}"}},
        {"schema": _SCHEMAS["artifact-metadata"], "metadata": {_URL: "key only"}},
        {"schema": "https://example.com/other/1", "metadata": {"u": _URL}},
        {"schema": f"x{PITLOOM_SCHEMA_PREFIX}", "metadata": {"u": _URL}},
        {"schema": 1, "metadata": {"u": _URL}},
        {"metadata": {"u": _URL}},
    ],
    ids=["prose", "key", "other-schema", "prefix-mid", "schema-not-text", "none"],
)
def test_prose_a_key_or_another_schema_is_never_read(
    statement: dict[str, Any],
) -> None:
    assert not find_graph_credentials([_element(statement)])


def test_a_json_text_statement_that_is_not_an_object_is_not_read() -> None:
    element = _element({})
    element["statement"] = json.dumps([_URL])
    assert not find_graph_credentials([element])


#: A realistic value of each ``externalIdentifierType`` but ``urlScheme``.
_IDENTIFIERS = [
    ("cpe22", "cpe:/a:apache:http_server:2.4.1"),
    ("cpe23", "cpe:2.3:a:mail\\@x:prod:1.0:*:*:*:*:*:*:*"),
    ("email", "Alice Smith <alice@example.com>"),
    ("email", "git@github.com"),
    ("gitoid", "gitoid:blob:sha1:261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"),
    ("other", "10.57967/hf/1234"),
    ("other", "https://doi.org/10.1/x"),
    ("packageUrl", "pkg:pypi/foo@1.0"),
    ("securityOther", "GHSA-xxxx-yyyy-zzzz"),
    ("swhid", "swh:1:cnt:94a9ed024d3859793618152ea559a168bbcbb5e2;origin=x"),
    ("swid", "swid:2df9de35-0aff-4a86-ace6-f7dddd1ade4c"),
]


@pytest.mark.parametrize(("kind", "value"), _IDENTIFIERS, ids=lambda x: x[:12])
def test_an_identifier_of_any_type_with_no_credential_has_no_finding(
    kind: str, value: str
) -> None:
    """Every ``identifier`` is read (a model's DOI is ``other``): no
    realistic identifier of any type is a finding."""
    element = {
        "spdxId": "urn:a",
        "externalIdentifier": [{"externalIdentifierType": kind, "identifier": value}],
    }
    assert not find_graph_credentials([element])


def _safetensors(path: Path, metadata: dict[str, str]) -> Path:
    header = json.dumps(
        {
            "__metadata__": metadata,
            "w": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
        }
    ).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\0\0\0\0")
    return path


@pytest.mark.platform
def test_a_model_metadata_url_is_refused_end_to_end(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A model's metadata is copied into its artifact-metadata statement:
    a credential there refuses the SBOM, a prose one does not."""
    model = _safetensors(
        tmp_path / "m.safetensors",
        {"source_url": _URL, "description": f"Trained on {_URL} data"},
    )
    out = tmp_path / "o.json"
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        generate_model_sbom(model, output_path=out)
    assert code_of(caught.value) == "credentials-unsafe/refused"
    assert not out.exists() and _SECRET not in caplog.text
    assert caplog.text.count("holds a credential") == 1
    assert "/statement/metadata/source_url" in caplog.text
