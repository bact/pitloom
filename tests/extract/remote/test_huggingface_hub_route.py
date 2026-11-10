# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hugging Face model read end to end against a local Hub: its
``config.json``, model card, licence file and each listed dataset's card are
downloaded at the revision ``model_info()`` states, through the capped
client, into a temporary directory removed afterwards; the library's
``check_url`` sees each request and ``max_download_bytes`` caps each file.

The Hub API requests (``model_info()``, the file listing,
``dataset_info()``) are ``huggingface_hub``'s and are patched here.

See also: tests/extract/remote/test_hub_files.py (the downloads) and
tests/_fake_hub.py.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from pitloom.assemble import generate, generate_model_sbom
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from pitloom.extract.remote import huggingface_fetch, read_huggingface
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import OVER_CAP
from tests._fake_hub import TOKEN, FakeHub, hub_and_cdn, point_hub_at, serve_in_git
from tests._fake_pypi_server import Route, redirect
from tests.conformance.g7ai_shared import without_licence_database

pytestmark = pytest.mark.loopback

_SHA = "0123456789abcdef0123456789abcdef01234567"
_DATA_SHA = "89abcdef0123456789abcdef0123456789abcdef"
_CARD = b"---\nlicense: other\ndatasets:\n- o/d\n---\n\n# M\n\nA model.\n"
_DATA_CARD = b"---\nlicense: mit\n---\n\n# D\n\nA dataset.\n"


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FakeHub]:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with hub_and_cdn() as fake, without_licence_database():
        point_hub_at(monkeypatch, fake)
        serve_in_git(
            fake, "acme/m", "config.json", b'{"model_type": "bert"}', revision=_SHA
        )
        serve_in_git(fake, "acme/m", "README.md", _CARD, revision=_SHA)
        serve_in_git(fake, "acme/m", "LICENSE", b"MIT License", revision=_SHA)
        cache = f"/api/resolve-cache/datasets/o/d/{_DATA_SHA}/README.md"
        fake.hub.routes[f"/datasets/o/d/resolve/{_DATA_SHA}/README.md"] = redirect(
            cache, status=307
        )
        fake.hub.routes[cache] = Route(body=_DATA_CARD)
        with (
            patch.object(
                huggingface_fetch,
                "_load_model_info",
                return_value={"author": "acme", "sha": _SHA},
            ),
            patch.object(
                huggingface_fetch,
                "_list_license_files_in_repo",
                return_value=["LICENSE"],
            ),
            patch.object(
                hub_dataset,
                "_load_dataset_info",
                return_value={"author": "o", "sha": _DATA_SHA},
            ),
        ):
            yield fake


def test_every_file_comes_from_the_hub_at_its_revision(
    fake: FakeHub, tmp_path: Path
) -> None:
    meta = read_huggingface("acme/m")
    assert meta.type_of_model == "bert"
    assert meta.description == "A model."
    (dataset,) = meta.datasets
    assert (dataset.metadata.name, dataset.metadata.license) == ("o/d", "mit")
    resolved = [p for p in fake.hub.seen if "/resolve/" in p]
    assert all(_SHA in p or _DATA_SHA in p for p in resolved)
    assert {h.get("authorization") for h in fake.hub.headers} == {f"Bearer {TOKEN}"}
    assert not list(tmp_path.glob("pitloom-hf-*"))


def test_check_url_sees_each_file_and_redirect(fake: FakeHub) -> None:
    seen: list[str] = []
    read_huggingface("acme/m", policy=RemoteFetchPolicy(check_url=seen.append))
    assert [u.removeprefix(fake.hub.base) for u in seen] == fake.hub.seen


def test_generate_passes_its_check_to_the_hub(fake: FakeHub) -> None:
    seen: list[str] = []
    generate("acme/m", check_url=seen.append, output_path=Path("o.json"))
    assert seen and [u.removeprefix(fake.hub.base) for u in seen] == fake.hub.seen


def test_the_cap_leaves_a_file_out_and_the_sbom_is_written(
    fake: FakeHub, caplog: pytest.LogCaptureFixture
) -> None:
    """The card (55 bytes) is over 50 bytes: one ``over-cap``
    ``WARNING:``; the rest (``config.json``, the licence file) is read and
    the SBOM written."""
    del fake
    with caplog.at_level(logging.WARNING):
        sbom = json.loads(generate_model_sbom("acme/m", max_download_bytes=50))
    codes = [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert codes == [OVER_CAP.code]
    assert "model card not read" in caplog.text
    assert any(e.get("type") == "ai_AIPackage" for e in sbom["@graph"])
