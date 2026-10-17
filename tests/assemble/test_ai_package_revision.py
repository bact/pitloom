# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's ``releaseTime`` and a Hub model's commit hash as its version,
and what they do to the document's identity.

See also: tests/extract/remote/test_huggingface_revision.py (the reader).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import logging
import time
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelMetadata
from tests._author_routes import CREATED
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls

_SHA = "0123456789abcdef0123456789abcdef01234567"
_OTHER = "f" * 40


def _package(sbom: str) -> dict[str, Any]:
    graph = json.loads(sbom)["@graph"]
    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    return dict(package)


def _with_time(stamp: str | None) -> str:
    return build_model(AiModelMetadata(name="m", release_time=stamp), CREATED).to_json()


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("2024-01-02T03:04:05+00:00", "2024-01-02T03:04:05Z"),
        ("2024-01-02T03:04:05Z", "2024-01-02T03:04:05Z"),
        # Whole seconds, in UTC.
        ("2024-01-02T08:04:05.999999+05:00", "2024-01-02T03:04:05Z"),
        # No zone: UTC.
        ("2024-01-02T03:04:05", "2024-01-02T03:04:05Z"),
        (None, None),
        ("", None),
    ],
    ids=["offset-zero", "z", "offset-and-microseconds", "naive", "none", "empty"],
)
def test_release_time(stamp: str | None, expected: str | None) -> None:
    assert _package(_with_time(stamp)).get("releaseTime") == expected


@pytest.mark.parametrize("stamp", ["yesterday", "2024-13-45T00:00:00Z", "1704164645"])
def test_a_release_time_that_is_not_iso_8601_is_left_out_with_a_warning(
    stamp: str, caplog: pytest.LogCaptureFixture
) -> None:
    sbom = _with_time(stamp)
    assert "releaseTime" not in _package(sbom)
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert messages == ["FORMAT=unknown FILE=m: release time is not ISO 8601; left out"]


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset (POSIX)")
def test_a_naive_release_time_ignores_the_local_zone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = []
    for zone in ("UTC", "Asia/Bangkok", "America/Los_Angeles"):
        monkeypatch.setenv("TZ", zone)
        time.tzset()
        results.append(_with_time("2024-01-02T03:04:05"))
    monkeypatch.delenv("TZ")
    time.tzset()
    assert len(set(results)) == 1


def _hub(sha: str | None) -> str:
    info: dict[str, Any] = {"author": "acme", "last_modified": "2024-01-02T03:04:05Z"}
    if sha:
        info["sha"] = sha
    with _patch_hf_calls(hub_info=info):
        return generate_model_sbom("acme/model", creation_metadata=CREATED)


def test_hub_model_version_and_release_time() -> None:
    package = _package(_hub(_SHA))
    assert package["software_packageVersion"] == _SHA
    assert package["releaseTime"] == "2024-01-02T03:04:05Z"


def test_hub_model_without_a_commit_has_no_version() -> None:
    assert "software_packageVersion" not in _package(_hub(None))


def _namespace(doc: dict[str, Any]) -> str:
    return str(doc["@graph"][1]["spdxId"]).split("#", maxsplit=1)[0]


def test_the_same_revision_gives_the_same_bytes_and_another_a_new_document() -> None:
    assert _hub(_SHA) == _hub(_SHA)
    first, second = json.loads(_hub(_SHA)), json.loads(_hub(_OTHER))
    assert _namespace(first) != _namespace(second)
