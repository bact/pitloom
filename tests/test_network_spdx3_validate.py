# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Real ``spdx3-validate`` runs (network): it accepts a valid document and
rejects a schema-invalid and a SHACL-invalid one.

Kept apart from ``test_network_helpers.py``, whose autouse fixture forces
lenient mode; here the ``PITLOOM_REQUIRE_NETWORK`` gate must stay in effect.

See also: tests/_network.py, tests/test_network_helpers.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.core.file_hash import HexDigests
from tests._network import assert_spdx3_validate_ok

_VALID_SBOM = {
    "@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld",
    "@graph": [
        {
            "@id": "_:ci",
            "created": "2026-03-01T11:00:00Z",
            "createdBy": ["https://example.org/Person/p1"],
            "specVersion": "3.0.1",
            "type": "CreationInfo",
        },
        {
            "creationInfo": "_:ci",
            "name": "Someone",
            "spdxId": "https://example.org/Person/p1",
            "type": "Person",
        },
    ],
}


def _mutated_sbom(index: int, key: str, value: object) -> dict[str, object]:
    sbom = json.loads(json.dumps(_VALID_SBOM))
    sbom["@graph"][index][key] = value
    return sbom  # type: ignore[no-any-return]


def _wrong_type_person() -> dict[str, object]:
    """Schema-valid, but SHACL rejects a ``software_Package`` as an Agent."""
    return _mutated_sbom(1, "type", "software_Package")


@pytest.mark.network
@pytest.mark.parametrize(
    "document",
    [
        pytest.param(_VALID_SBOM, id="valid"),
        pytest.param(_mutated_sbom(1, "name", 12345), id="schema-invalid"),
        pytest.param(_wrong_type_person(), id="shacl-invalid"),
    ],
)
def test_real_spdx3_validate_rejects_invalid_document(
    tmp_path: Path, document: dict[str, object]
) -> None:
    """The real run fails on an invalid document (``-m`` exits 0 on one)."""
    sbom = tmp_path / "sbom.json"
    sbom.write_text(json.dumps(document), encoding="utf-8")
    if document is _VALID_SBOM:
        assert_spdx3_validate_ok(sbom)
    else:
        with pytest.raises(AssertionError, match="spdx3-validate failed"):
            assert_spdx3_validate_ok(sbom)


@pytest.mark.network
def test_real_spdx3_validate_accepts_a_model_producer_and_count(
    tmp_path: Path,
) -> None:
    """A model's ``originatedBy`` generic Agent, the same Agent as its
    ``suppliedBy`` (the Hugging Face shape), its ``parameters``
    hyperparameter (with the package comment saying so) and its file's
    SHA-256 and SHA-512 as ``verifiedUsing`` are schema- and SHACL-valid."""
    model = AiModelMetadata(
        name="m",
        originators=["Alice"],
        supplier="Alice",
        parameter_count=7,
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
    )
    creation = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")
    sbom = tmp_path / "sbom.json"
    exporter = build_model(model, creation, digest=HexDigests("AB" * 32, "CD" * 64))
    sbom.write_text(exporter.to_json(), encoding="utf-8")
    graph = json.loads(sbom.read_text(encoding="utf-8"))["@graph"]
    assert [e["name"] for e in graph if e["type"] == "Agent"] == ["Alice"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    assert package["ai_hyperparameter"][0]["key"] == "parameters"
    assert package["originatedBy"] == [package["suppliedBy"]]
    assert "comment" in package
    assert package["verifiedUsing"] == [
        {"type": "Hash", "algorithm": "sha256", "hashValue": "ab" * 32},
        {"type": "Hash", "algorithm": "sha512", "hashValue": "cd" * 64},
    ]
    assert_spdx3_validate_ok(sbom)
