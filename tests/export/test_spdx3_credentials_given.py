# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.export._spdx3_credentials` on a given SBOM
(``embed-wheel --sbom``, every string read) and on an id whose credential
only a percent-decode shows: no line or error shows a secret at any decode
depth.

See also: test_spdx3_credentials.py and test_spdx3_credentials_references.py
in this folder, tests/core/url_masking/test_url_masking_decode.py (the
detector and masker at each depth).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest

from pitloom.assemble import ConfigOverrides, embed_wheel_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.credential_policy import CredentialPolicy
from pitloom.export._spdx3_credentials import (
    check_graph_credentials,
    find_graph_credentials,
)
from pitloom.messages import code_of
from tests._author_routes import CREATED, write_wheel

#: The ``refuse`` mode: these tests are about what is refused.
_REFUSE = CredentialPolicy(refuse=True)

_REFUSED = "credentials-unsafe/refused"
_SECRETS = ("S3CRET", "SE/CRET")
_URL = "https://u:S3CRET@h.example/x"
_CONTEXT = "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"
_PACKAGE = {"type": "software_Package", "spdxId": "https://ex.org/p", "name": "d"}
_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _shows_a_secret(text: str) -> bool:
    """Whether *text*, or a percent-decode of it however deep, shows a
    planted secret."""
    for _ in range(8):
        if any(secret in text for secret in _SECRETS):
            return True
        plain = unquote(text)
        if plain == text:
            return False
        text = plain
    return True


def _package(**fields: Any) -> dict[str, Any]:
    return {"@context": _CONTEXT, "@graph": [{**_PACKAGE, **fields}]}


#: A given SBOM's shapes a compact-key read misses: each holds ``_URL``.
_GIVEN: dict[str, str] = {
    "top-level": json.dumps({**_package(), "software_downloadLocation": _URL}),
    "context-url": json.dumps(
        {"@context": "https://u:S3CRET@h.example/c.jsonld", "@graph": [_PACKAGE]}
    ),
    "context-term": json.dumps(
        {"@context": [_CONTEXT, {"dl": {"@id": _URL}}], "@graph": [_PACKAGE]}
    ),
    "expanded-key": json.dumps(
        _package(**{"https://spdx.org/rdf/3.0.1/terms/Software/downloadLocation": _URL})
    ),
    "prefixed-key": json.dumps(_package(**{"spdx:Software/downloadLocation": _URL})),
    "value-object": json.dumps(_package(software_downloadLocation={"@value": _URL})),
    "escaped-key": json.dumps(_package()).replace(
        '"name": "d"', f'"name": "d", "software_download\\u004cocation": "{_URL}"'
    ),
}


@pytest.mark.platform
@pytest.mark.parametrize("name", sorted(_GIVEN))
def test_a_given_sbom_is_refused_wherever_a_url_stands(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``embed-wheel --sbom`` embeds the bytes as given, so every string of
    the document is read as a URL value, not only a compact field."""
    sbom = tmp_path / "given.json"
    sbom.write_bytes(_GIVEN[name].encode())
    assert "S3CRET" in sbom.read_text(encoding="utf-8")
    wheel = write_wheel(tmp_path, "Metadata-Version: 2.4\nName: d\nVersion: 1.0\n")
    before = wheel.read_bytes()
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        embed_wheel_sbom(
            wheel, sbom_path=sbom, overrides=ConfigOverrides(credentials=_REFUSE)
        )
    assert code_of(caught.value) == _REFUSED and wheel.read_bytes() == before
    assert not _shows_a_secret(caplog.text + str(caught.value))


@pytest.mark.parametrize(
    "path",
    [
        *sorted((_FIXTURES / "fragments").glob("*.json")),
        _FIXTURES / "sentimentdemo-handcrafted.spdx3.json",
    ],
    ids=lambda path: path.stem,
)
def test_a_fixture_sbom_read_whole_holds_no_credential(path: Path) -> None:
    """Every string read: no SBOM Pitloom's fixtures hold is refused or
    warned of (a false-positive guard)."""
    document = json.loads(path.read_bytes())
    graph = document.get("@graph", [document])
    rest = {key: value for key, value in document.items() if key != "@graph"}
    assert not find_graph_credentials([*graph, rest], every_string=True)


#: Ids whose credential a percent-decode shows, then a deeper one breaks
#: (``%252F``) or a format character hides (``%E2%80%8B``).
_DECODED: dict[str, list[dict[str, Any]]] = {
    "slash": [{"spdxId": "https://ex.org/P/https:%2F%2Fu:SE%252FCRET@h"}],
    "format": [{"spdxId": "https://ex.org/P/https%E2%80%8B:%2F%2Fu:S3CRET@h"}],
    "reference": [
        {"spdxId": "https://ex.org/r", "to": ["urn:x:https:%2F%2Fu:SE%252FCRET@h"]}
    ],
}


@pytest.mark.parametrize("name", sorted(_DECODED))
def test_an_id_a_decode_shows_a_credential_in_is_refused_and_masked(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as caught:
        check_graph_credentials(_DECODED[name], CredentialPolicy(refuse=True))
    assert code_of(caught.value) == _REFUSED and caplog.records
    assert not _shows_a_secret(caplog.text + str(caught.value))


def test_a_model_named_by_an_encoded_credential_shows_it_nowhere(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The model's id (``iri_segment`` of its name) and the element name a
    refusal line prints are both masked at every depth."""
    model = AiModelMetadata(name="https://u:SE%2FCRET@h/m")
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError) as caught:
        build_model(model, CREATED).to_json(credentials=_REFUSE)
    assert code_of(caught.value) == _REFUSED
    assert not _shows_a_secret(caplog.text + str(caught.value))


@pytest.mark.parametrize(
    "name",
    ["ssh://git@github.com/org/m", "git+ssh://git@github.com/org/m.git"],
    ids=["ssh", "git+ssh"],
)
def test_a_model_named_by_an_ssh_account_is_written_with_a_warning(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        text = build_model(AiModelMetadata(name=name), CREATED).to_json()
    assert f'"{name}"' in text
    assert caplog.records and all(r.levelno == logging.WARNING for r in caplog.records)
    with pytest.raises(ValueError):
        build_model(
            AiModelMetadata(name=name.replace("git@", "git:S3CRET@")), CREATED
        ).to_json(credentials=_REFUSE)
