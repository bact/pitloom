# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the vendored SPDX 3.0.1 model snapshot used for offline validation.

See also: tests/fixtures/spdx-model/README.md.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).parent / "fixtures" / "spdx-model" / "v3.0.1"
FILES = ("spdx-context.jsonld", "spdx-json-schema.json", "spdx-model.ttl")


def _sums() -> dict[str, str]:
    lines = (SNAPSHOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (ln.split(None, 1) for ln in lines)}


def test_sums_list_exactly_the_snapshot_files() -> None:
    assert set(_sums()) == set(FILES)


@pytest.mark.parametrize("name", FILES)
def test_file_matches_recorded_checksum(name: str) -> None:
    # Bytes, not text: a CRLF rewrite by git or an editor must fail here.
    digest = hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest()
    assert digest == _sums()[name]


@pytest.mark.parametrize("name", ("spdx-context.jsonld", "spdx-json-schema.json"))
def test_json_files_parse(name: str) -> None:
    assert isinstance(json.loads((SNAPSHOT / name).read_bytes()), dict)


def test_licence_is_community_spec() -> None:
    text = (SNAPSHOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("Community Specification License 1.0")
    readme = (SNAPSHOT.parent / "README.md").read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: Community-Spec-1.0" in readme
