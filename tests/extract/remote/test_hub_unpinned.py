# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hugging Face model whose files are read at no revision is said once
(``hub-revision-unpinned``), where the revision is decided
(:func:`~pitloom.extract.remote.huggingface_fetch._fetch_all_hf_data`), not
once per file: a model with three JSON files, a card and a licence file gives
one line; none when the Hub stated a revision, when the Hub is refused
(``asks_hub`` false) or under ``HF_HUB_OFFLINE``, which reads no file; one per
read of a model (a second read of the same model says it again).

See also: tests/extract/remote/test_huggingface_fetch.py (the readers),
tests/extract/remote/test_hub_api.py (a failed ``model_info()``) and
tests/messages/test_hub.py (the entry).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub import constants as hf_constants

from pitloom.extract.remote import huggingface_fetch as hub_fetch
from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote.huggingface_fetch import _fetch_all_hf_data
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    HUB_REVISION_UNPINNED,
    OFFLINE_UNUSABLE,
)
from tests.conformance.g7ai_shared import without_licence_database
from tests.extract.remote.hf_patches._hf_patches_base import fake_hub, patch_hub_fetch

pytestmark = pytest.mark.platform  # downloaded files in a temporary directory

_SHA = "89abcdef0123456789abcdef0123456789abcdef"
_PAGE = "https://huggingface.co/o/m"
_CODE = HUB_REVISION_UNPINNED.code

#: The files of the model: three JSON files, a card that leaves the licence
#: to the licence file, and the licence file.
_FILES = {
    "config.json": b'{"model_type": "bert"}',
    "tokenizer_config.json": b"{}",
    "generation_config.json": b"{}",
    "README.md": b"---\nlicense: other\n---\nA model.\n",
    "LICENSE": b"Some licence text.\n",
}


@pytest.fixture(autouse=True)
def _online(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Online (an offline environment fails before any request), without a
    licence database (the detection of the text is not under test)."""
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False)
    with without_licence_database():
        yield


def _said(caplog: pytest.LogCaptureFixture, code: str = _CODE) -> list[str]:
    """The messages of the records that carry *code*."""
    return [
        r.getMessage() for r in caplog.records if getattr(r, CODE_ATTR, None) == code
    ]


def _model_info(sha: str | None) -> MagicMock:
    sibling = MagicMock()
    sibling.rfilename = "LICENSE"
    return MagicMock(
        author="o",
        sha=sha,
        created_at=None,
        last_modified=None,
        downloads=None,
        tags=[],
        siblings=[sibling],
        safetensors=None,
        gguf=None,
    )


def _read(tmp_path: Path, model_info: Any) -> list[tuple[str, str | None]]:
    """``read_huggingface("o/m")`` with the Hub serving :data:`_FILES`;
    ``(file, revision)`` of each file asked for."""
    asked: list[tuple[str, str | None]] = []

    def serve(
        repo_id: str, filename: str, *, revision: str | None, repo_type: str
    ) -> Path | None:
        assert (repo_id, repo_type) == ("o/m", "model")
        asked.append((filename, revision))
        body = _FILES.get(filename)
        if body is None:
            return None
        path = tmp_path / filename
        path.write_bytes(body)
        return path

    with (
        patch("huggingface_hub.model_info", **model_info),
        patch_hub_fetch(serve),
    ):
        read_huggingface("o/m")
    return asked


def test_a_model_without_a_revision_is_said_once_for_all_its_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked = _read(tmp_path, {"return_value": _model_info(None)})
    # Every file was read, at no revision: the one line covers them all.
    assert sorted(name for name, _ in asked) == sorted(_FILES)
    assert {revision for _, revision in asked} == {None}
    assert _said(caplog) == [
        f"URL={_PAGE}: the Hub stated no revision; files are read at the default "
        "branch as it is now"
    ]
    assert not [r for r in caplog.records if "pinned revision" in r.getMessage()]
    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 1


def test_a_model_with_a_revision_is_not_said(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asked = _read(tmp_path, {"return_value": _model_info(_SHA)})
    assert sorted(name for name, _ in asked) == sorted(_FILES)
    assert {revision for _, revision in asked} == {_SHA}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_failed_model_info_says_the_failure_then_the_unpinned_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No ``model_info()`` answer, no revision: two lines, each of its own
    entry, in the order of the facts."""
    asked = _read(tmp_path, {"side_effect": OSError("down")})
    assert {revision for _, revision in asked} == {None}
    codes = [
        getattr(r, CODE_ATTR) for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert codes == [DOWNLOAD_FAILED.code, _CODE]


# -- each side of ``revision is None and not hub_offline()`` and ``asks_hub`` --


@pytest.mark.parametrize(
    ("info", "offline", "said"),
    [
        ({}, False, 1),
        ({"sha": _SHA}, False, 0),
        ({}, True, 0),
        ({"sha": _SHA}, True, 0),
    ],
    ids=["no-sha-online", "sha-online", "no-sha-offline", "sha-offline"],
)
def test_the_line_needs_no_revision_and_no_offline_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    info: dict[str, Any],
    offline: bool,
    said: int,
) -> None:
    """Only ``A`` fails, or only ``B``: the line follows each."""
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", offline)
    json_file = tmp_path / "x.json"
    json_file.write_bytes(b"{}")
    with patch.object(hub_fetch, "_load_model_info", return_value=info):
        _fetch_all_hf_data(fake_hub(json_file), "o/m")
    assert len(_said(caplog)) == said


def test_a_hub_that_is_not_asked_says_nothing_of_a_revision(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    hub = fake_hub(tmp_path / "x.json")
    hub.asks_hub = False
    with patch.object(hub_fetch, "_load_model_info") as info:
        data = _fetch_all_hf_data(hub, "o/m")
    info.assert_not_called()
    assert not data["hub_info"] and data["config"] is None
    assert not caplog.records


def test_under_hf_hub_offline_the_failed_request_is_the_one_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``model_info()`` itself refuses to ask: the offline line says what is
    lost, and no file is read at no revision, so no unpinned line."""
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", True)
    json_file = tmp_path / "x.json"
    json_file.write_bytes(b"{}")
    _fetch_all_hf_data(fake_hub(json_file), "o/m")
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [getattr(r, CODE_ATTR) for r in warnings] == [OFFLINE_UNUSABLE.code]
    assert not _said(caplog)


def test_the_line_is_said_once_per_read_of_a_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    json_file = tmp_path / "x.json"
    json_file.write_bytes(b"{}")
    with patch.object(hub_fetch, "_load_model_info", return_value={}):
        for model in ("o/m", "o/m", "o/n"):
            _fetch_all_hf_data(fake_hub(json_file), model)
    lines = _said(caplog)
    assert [line.split(": ", 1)[0] for line in lines] == [
        f"URL={_PAGE}",
        f"URL={_PAGE}",
        "URL=https://huggingface.co/o/n",
    ]
