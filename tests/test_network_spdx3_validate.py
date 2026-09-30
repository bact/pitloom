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
