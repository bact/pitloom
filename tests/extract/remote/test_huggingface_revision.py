# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hub model's version is its commit hash and its release time the
revision's commit time; both are left out when the Hub gives neither.

See also: tests/assemble/test_ai_package_revision.py (the SBOM side).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from typing import Any

import pytest

from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote.huggingface_field import hub_revision
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls

_SHA = "0123456789abcdef0123456789abcdef01234567"
_TIME = "2024-01-02T03:04:05+00:00"


@pytest.mark.parametrize(
    ("hub_info", "version", "release_time"),
    [
        ({"sha": _SHA}, _SHA, None),
        ({"sha": _SHA.upper()}, _SHA, None),
        # Not a commit hash: no version, however the Hub came to say it.
        ({"sha": "main"}, None, None),
        ({"sha": "deadbeef"}, None, None),
        ({"sha": _SHA + "0"}, None, None),
        ({"sha": 123}, None, None),
        ({}, None, None),
        # The time is kept as stated; the assembler parses it.
        ({"last_modified": _TIME}, None, _TIME),
        ({"last_modified": " 2024-01-02T03:04:05Z "}, None, "2024-01-02T03:04:05Z"),
        ({"last_modified": "yesterday"}, None, "yesterday"),
        ({"last_modified": ""}, None, None),
        ({"last_modified": "  "}, None, None),
        ({"last_modified": 1704164645}, None, None),
    ],
    ids=[
        "sha", "upper-sha", "branch", "short-sha", "long-sha", "sha-not-text",
        "empty", "time", "time-trimmed", "time-text", "time-empty", "time-blank",
        "time-number",
    ],
)  # fmt: skip
def test_hub_revision(
    hub_info: dict[str, Any], version: str | None, release_time: str | None
) -> None:
    provenance: dict[str, str] = {}
    revision = hub_revision(hub_info, provenance)
    assert (revision.version, revision.release_time) == (version, release_time)
    # Provenance only for what was read.
    assert ("version" in provenance) is (version is not None)
    assert ("release_time" in provenance) is (release_time is not None)


def test_read_huggingface_sets_version_and_release_time() -> None:
    info = {"author": "acme", "sha": _SHA, "last_modified": "2024-01-02T03:04:05+00:00"}
    with _patch_hf_calls(hub_info=info):
        meta = read_huggingface("acme/model")
    assert meta.version == _SHA
    assert meta.release_time == "2024-01-02T03:04:05+00:00"
    assert meta.provenance["version"].startswith("Source: Hugging Face Hub")


def test_read_huggingface_without_revision_data_leaves_them_unset() -> None:
    with _patch_hf_calls(hub_info={"author": "acme"}):
        meta = read_huggingface("acme/model")
    assert (meta.version, meta.release_time) == (None, None)
    assert "version" not in meta.provenance
