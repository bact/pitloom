# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``pkg:huggingface`` and ``pkg:generic`` PURL builders.

See also: tests/assemble/test_ai_package_purl.py (where they are used) and
tests/export/test_spdx3_credentials.py (the check of a credential).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from spdx_python_model.bindings.v3_0_1 import model as spdx_model

from pitloom.core.credential_policy import CredentialPolicy
from pitloom.core.purl import build_generic_purl, build_huggingface_purl
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.messages import code_of

_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    ("model_id", "revision", "expected"),
    [
        ("acme/model", None, "pkg:huggingface/acme/model"),
        ("acme/model", _SHA, f"pkg:huggingface/acme/model@{_SHA}"),
        ("acme/model", _SHA.upper(), f"pkg:huggingface/acme/model@{_SHA}"),
        # Only a Git commit hash is a revision: a branch or short hash is not.
        ("acme/model", "main", "pkg:huggingface/acme/model"),
        ("acme/model", "deadbeef", "pkg:huggingface/acme/model"),
        ("acme/model", _SHA + "0", "pkg:huggingface/acme/model"),
        ("acme/model", "", "pkg:huggingface/acme/model"),
        # Case is kept: owner and name are case sensitive.
        ("Acme/My-Model.v2", None, "pkg:huggingface/Acme/My-Model.v2"),
        ("acme/mo del@1", None, "pkg:huggingface/acme/mo%20del%401"),
        # The type needs an owner and a name.
        ("gpt2", None, None),
        ("", None, None),
        ("/model", None, None),
        ("acme/", None, None),
        ("a/b/c", None, None),
    ],
    ids=[
        "plain", "revision", "upper-revision", "branch", "short-hash", "long-hash",
        "empty-revision", "case-kept", "encoded", "no-owner", "empty",
        "no-owner-slash", "no-name", "three-parts",
    ],
)  # fmt: skip
def test_huggingface_purl(
    model_id: str, revision: str | None, expected: str | None
) -> None:
    assert build_huggingface_purl(model_id, revision) == expected


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, "pkg:generic/m.gguf"),
        ({"version": "1.0"}, "pkg:generic/m.gguf@1.0"),
        ({"checksum": "sha256:ab"}, "pkg:generic/m.gguf?checksum=sha256:ab"),
        (
            {"download_url": "https://e.org/a b.tar?x=1&y=2"},
            "pkg:generic/m.gguf?download_url=https://e.org/a%20b.tar%3Fx%3D1%26y%3D2",
        ),
        # Qualifiers are in key order whatever the call order.
        (
            {"download_url": "https://e.org/d", "checksum": "sha256:ab"},
            "pkg:generic/m.gguf?checksum=sha256:ab&download_url=https://e.org/d",
        ),
        ({"version": "1+cpu", "checksum": ""}, "pkg:generic/m.gguf@1%2Bcpu"),
    ],
    ids=["name", "version", "checksum", "download-url", "key-order", "empty-qualifier"],
)
def test_generic_purl(kwargs: dict[str, str], expected: str) -> None:
    assert build_generic_purl("m.gguf", **kwargs) == expected


def test_generic_purl_encodes_the_name() -> None:
    assert build_generic_purl("a/b c@d") == "pkg:generic/a%2Fb%20c%40d"


def test_a_credential_in_the_download_url_is_kept_and_refusable() -> None:
    """The builder never rewrites *download_url*: the PURL states it as
    given (encoded), and the SBOM exporter refuses it in the refuse mode."""
    url = "https://u:S3CRET@h.example/d.csv?token=T0KEN"
    purl = build_generic_purl("d.csv", download_url=url)
    assert purl == (
        "pkg:generic/d.csv?download_url="
        "https://u:S3CRET%40h.example/d.csv%3Ftoken%3DT0KEN"
    )
    exporter = Spdx3JsonExporter()
    exporter.add_package(
        spdx_model.software_Package(
            spdxId="urn:a#P",
            name="d",
            software_packageUrl=purl,
            creationInfo=spdx_model.CreationInfo(
                specVersion="3.0.1",
                created=datetime(2026, 1, 1, tzinfo=timezone.utc),
                createdBy=["urn:agent"],
            ),
        )
    )
    with pytest.raises(ValueError) as caught:
        exporter.to_json(credentials=CredentialPolicy(refuse=True))
    assert code_of(caught.value) == "credentials-unsafe/refused"
    assert "S3CRET" not in str(caught.value) and "T0KEN" not in str(caught.value)
