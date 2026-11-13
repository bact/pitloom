# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The cap and the deadline of each Hugging Face metadata file
(:mod:`pitloom.extract.remote._hub_files`): a JSON file, the model card, a
licence file and a dataset card are each downloaded under the smaller of
their own cap and ``max-download-bytes``, in the metadata deadline; a file
over its cap is left out with one ``over-cap`` ``WARNING:`` naming it and
the cap. The name a file is saved under stays a plain name in its folder.

The Hub is a local server (``loopback``, tests/_fake_hub.py).

See also: tests/extract/remote/test_hub_files.py (the downloads) and
tests/extract/remote/test_hub_files_endpoint.py (``HF_ENDPOINT``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.core.internal_error import InternalError
from pitloom.enrich.readme import MODEL_CARD_MAX_BYTES
from pitloom.extract._license_detect import LICENSE_FILE_MAX_BYTES
from pitloom.extract.remote import _hub_files
from pitloom.extract.remote._http_fetch import JSON_DEADLINE_SECONDS
from pitloom.extract.remote._hub_files import (
    HUB_JSON_CAP,
    HUB_JSON_MAX_BYTES,
    METADATA_DEADLINE_SECONDS,
    HubFiles,
    file_cap,
    hub_files,
)
from pitloom.extract.remote.huggingface_dataset import _load_dataset_card
from pitloom.extract.remote.huggingface_fetch import (
    _detect_license_from_hf_files,
    _load_model_card,
    _safe_load_json,
)
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.files import (
    OVER_CAP,
    Cap,
)
from pitloom.messages.network import (
    DOWNLOAD_TIMEOUT,
)
from tests._fake_hub import FakeHub, hub_and_cdn, point_hub_at, serve_in_git
from tests._fake_pypi_server import Route

pytestmark = pytest.mark.loopback

_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(name="fake")
def _fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeHub]:
    with hub_and_cdn() as fake:
        point_hub_at(monkeypatch, fake)
        yield fake


def _json(size: int) -> bytes:
    """A JSON object of exactly *size* bytes."""
    return b'{"a": "' + b"x" * (size - 9) + b'"}'


def _card(size: int) -> bytes:
    """A card of exactly *size* bytes stating ``license: mit``."""
    head = b"---\nlicense: mit\n---\n"
    return head + b"x" * (size - len(head))


def _read_json(hub: HubFiles) -> object:
    return _safe_load_json(hub, "o/m", "config.json", revision=_SHA)


def _read_model_card(hub: HubFiles) -> object:
    return _load_model_card(hub, "o/m", _SHA)[1] or None


def _read_licence(hub: HubFiles) -> object:
    with (
        patch(
            "pitloom.extract.remote.huggingface_fetch._list_license_files_in_repo",
            return_value=["LICENSE"],
        ),
        patch(
            "pitloom.extract._license_text_match.detect_license_from_text",
            side_effect=lambda text: "MIT" if text else None,
        ),
    ):
        return _detect_license_from_hf_files(hub, "o/m", revision=_SHA)[0]


def _read_dataset_card(hub: HubFiles) -> object:
    return _load_dataset_card(hub, "o/d", _SHA)[1] or None


@dataclass(frozen=True)
class _Kind:
    """A kind of metadata file: the repository and file served, its reader,
    its cap, a body of a given size, what the reader gives for a file it
    reads, and the end of the warning for one over the cap."""

    repo: str
    filename: str
    read: Callable[[HubFiles], object]
    cap: int
    body: Callable[[int], bytes]
    got: object
    ending: str


_KINDS = [
    _Kind(
        "o/m",
        "config.json",
        _read_json,
        HUB_JSON_MAX_BYTES,
        _json,
        {"a": "x" * (HUB_JSON_MAX_BYTES - 9)},
        "Hub-JSON cap; config.json not read",
    ),
    _Kind(
        "o/m",
        "README.md",
        _read_model_card,
        MODEL_CARD_MAX_BYTES,
        _card,
        {"license": "mit"},
        "model-card cap; model card not read",
    ),
    _Kind(
        "o/m",
        "LICENSE",
        _read_licence,
        LICENSE_FILE_MAX_BYTES,
        lambda size: b"x" * size,
        "MIT",
        "license-detection cap; license file not read",
    ),
    _Kind(
        "datasets/o/d",
        "README.md",
        _read_dataset_card,
        MODEL_CARD_MAX_BYTES,
        _card,
        {"license": "mit"},
        "dataset-card cap; dataset card not read",
    ),
]


@pytest.mark.parametrize(
    "kind", _KINDS, ids=["json", "model-card", "licence", "dataset-card"]
)
@pytest.mark.parametrize("over", [0, 1], ids=["at-cap", "over-cap"])
def test_each_metadata_file_is_read_within_its_own_cap(
    fake: FakeHub, caplog: pytest.LogCaptureFixture, kind: _Kind, over: int
) -> None:
    """At its cap the file is read; one byte over it, it is left out with
    one ``over-cap`` ``WARNING:`` naming it and the cap, the
    ``max-download-bytes`` cap far larger."""
    served = kind.body(kind.cap + over)
    assert len(served) == kind.cap + over
    serve_in_git(fake, kind.repo, kind.filename, served, revision=_SHA, length=-1)
    with caplog.at_level(logging.WARNING), hub_files(RemoteFetchPolicy()) as hub:
        result = kind.read(hub)
    codes = [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]
    if not over:
        assert result == kind.got and not codes
        return
    assert result is None and codes == [OVER_CAP.code]
    shown = kind.repo.removeprefix("datasets/")
    assert caplog.records[-1].getMessage() == (
        f"FILE={shown}/{kind.filename}: larger than the {kind.cap}-byte {kind.ending}"
    )


@pytest.mark.parametrize(
    ("max_bytes", "named"),
    [(99, "max-download-bytes"), (100, "max-download-bytes"), (101, "own")],
)
def test_the_smaller_cap_binds_and_is_named(max_bytes: int, named: str) -> None:
    """The kind's own cap when it is the smaller; else the setting, named
    as the setting (a tie too: raising it is what would help)."""
    own = Cap(100, "byte", "own")
    cap = file_cap(own, RemoteFetchPolicy(max_bytes=max_bytes))
    assert (cap.limit, cap.purpose) == (min(max_bytes, 100), named)


def test_the_metadata_deadline_is_a_json_request_s() -> None:
    assert METADATA_DEADLINE_SECONDS == JSON_DEADLINE_SECONDS == 120.0
    assert HUB_JSON_CAP.limit == HUB_JSON_MAX_BYTES == 16 * 1024 * 1024


def test_a_trickling_file_stops_at_the_metadata_deadline(
    fake: FakeHub, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The metadata deadline, not a weights download's, stops a file that
    trickles in."""
    monkeypatch.setattr(_hub_files, "METADATA_DEADLINE_SECONDS", 0.3)
    cache = serve_in_git(fake, "o/m", "config.json", b"", revision=_SHA)
    fake.hub.routes[cache] = Route(body=b"{}" + b" " * 20, drip=0.1)
    with caplog.at_level(logging.WARNING), hub_files(RemoteFetchPolicy()) as hub:
        assert _read_json(hub) is None
    codes = [getattr(r, CODE_ATTR) for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert codes == [DOWNLOAD_TIMEOUT.code]


@pytest.mark.parametrize(
    ("filename", "saved"),
    [("config.json", "config.json"), ("sub/LICENSE", "LICENSE")],
)
def test_a_file_is_saved_under_its_plain_name(
    fake: FakeHub, filename: str, saved: str
) -> None:
    fake.hub.routes[f"/o/m/resolve/{_SHA}/{filename}"] = Route(body=b"{}")
    with hub_files(RemoteFetchPolicy()) as hub:
        path = hub.fetch("o/m", filename, revision=_SHA, cap=HUB_JSON_CAP)
        assert path is not None and path.name == saved
        assert path.parent.parent == hub.work_dir


@pytest.mark.parametrize(
    "filename", ["", "..", "a/..", ".", "a\\b", "..\\x", "c:x", "C:\\x"]
)
def test_a_name_that_is_no_plain_file_name_is_a_bug(
    fake: FakeHub, filename: str
) -> None:
    """The readers name fixed files: one that would not be a plain name in
    its folder on every platform is a programming error, nothing asked."""
    with hub_files(RemoteFetchPolicy()) as hub:
        with pytest.raises(InternalError, match="not a file name to save"):
            hub.fetch("o/m", filename, revision=_SHA, cap=HUB_JSON_CAP)
        assert not list(hub.work_dir.iterdir())
    assert not fake.hub.seen


def test_a_destination_outside_its_folder_is_a_bug(
    fake: FakeHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The destination is checked as well as the name."""
    monkeypatch.setattr(_hub_files, "_local_name", lambda _name: "../x")
    with hub_files(RemoteFetchPolicy()) as hub:
        with pytest.raises(InternalError, match="not a file name to save"):
            hub.fetch("o/m", "config.json", revision=_SHA, cap=HUB_JSON_CAP)
        assert not (hub.work_dir / "x").exists()
    assert not fake.hub.seen
