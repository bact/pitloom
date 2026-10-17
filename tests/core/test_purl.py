# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ``pkg:huggingface`` and ``pkg:generic`` PURL builders.

See also: tests/assemble/test_ai_package_purl.py (where they are used).
"""

from __future__ import annotations

import pytest

from pitloom.core.purl import build_generic_purl, build_huggingface_purl

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
