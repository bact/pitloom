# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hub that answers the API with an error or with nonsense, as
``huggingface_hub`` itself meets it (a loopback server behind
``hf_api.api.endpoint``): a 404, a 401, a 500, a body that is not JSON and
JSON that is no model: each is one coded ``WARNING:`` from
``model_info()`` and from ``dataset_info()``, the reader goes on with the
empty result, and the server's own words (control characters, a token, a
fake code) reach the line on one masked line.

See also: tests/extract/remote/test_hub_api.py (the classifier, from
exceptions), tests/extract/remote/test_huggingface_api_timeout.py (a Hub that
never answers) and tests/messages/test_hub.py (the entries).
"""

from __future__ import annotations

import http.server
import importlib
import json
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from huggingface_hub import constants as hf_constants
from huggingface_hub import hf_api

from pitloom.extract.remote import read_huggingface
from pitloom.extract.remote._hub_api import repo_page_url
from pitloom.extract.remote.huggingface_dataset import (
    DATASET_INFO_OUTCOME,
    _load_dataset_info,
)
from pitloom.extract.remote.huggingface_fetch import (
    MODEL_INFO_OUTCOME,
    _fetch_all_hf_data,
    _load_model_info,
)
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import trusted_message
from pitloom.messages.network import (
    DOWNLOAD_FAILED,
    HUB_RESPONSE_INVALID,
    HUB_REVISION_UNPINNED,
)
from tests.conformance.g7ai_shared import without_licence_database
from tests.extract.remote.hf_patches._hf_patches_base import fake_hub, patch_hub_fetch

pytestmark = [pytest.mark.platform, pytest.mark.loopback]  # sockets, threads

_TOKEN = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEfGh"  # 34 letters
_JSON = {"Content-Type": "application/json"}


@dataclass
class _Hub:
    """The loopback Hub: what it answers next, and what reached it."""

    status: int = 200
    body: bytes = b"{}"
    headers: dict[str, str] = field(default_factory=lambda: dict(_JSON))
    requests: list[str] = field(default_factory=list)

    def answer(self, status: int, body: bytes, headers: dict[str, str]) -> None:
        self.status, self.body, self.headers = status, body, headers


@pytest.fixture(name="hub")
def _hub(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Hub]:
    """A loopback server as the Hub endpoint ``huggingface_hub`` talks to,
    answering with what the test sets. Stopped by the server's own
    ``shutdown()`` (its poll loop), never by closing a listening socket."""
    hub = _Hub()

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answers every GET with what the test set."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name
            hub.requests.append(self.path)
            self.send_response(hub.status)
            for key, value in hub.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(hub.body)))
            self.end_headers()
            self.wfile.write(hub.body)

        # pylint: disable-next=redefined-builtin
        def log_message(self, format: str, *args: Any) -> None:
            """No access log on stderr."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    monkeypatch.setattr(
        hf_api.api, "endpoint", f"http://127.0.0.1:{server.server_port}"
    )
    # An offline environment fails before any socket is opened.
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False)
    # huggingface_hub fetches its agent registry from the endpoint on the
    # first request of a process and leaves an error response unclosed (a
    # ResourceWarning in whichever test runs first on an xdist worker).
    try:
        detect = importlib.import_module("huggingface_hub.utils._detect_agent")
    except ImportError:  # an older huggingface_hub has no registry fetch
        detect = None
    if detect is not None:
        monkeypatch.setattr(detect, "_fetch_registry", lambda: None, raising=False)
    try:
        yield hub
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


@pytest.fixture(autouse=True)
def _no_licence_database() -> Iterator[None]:
    with without_licence_database():
        yield


#: What the server answers: status, body, headers; the entry said.
_ANSWERS = [
    (404, b'{"error": "Repository not found"}', _JSON, DOWNLOAD_FAILED),
    (401, b'{"error": "Invalid credentials"}', _JSON, DOWNLOAD_FAILED),
    (500, b"oops", {}, DOWNLOAD_FAILED),
    (200, b"{not json", _JSON, HUB_RESPONSE_INVALID),
    (200, b"[1, 2]", _JSON, HUB_RESPONSE_INVALID),
]
_ANSWER_IDS = ["404", "401", "500", "malformed", "not-an-object"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("answer", _ANSWERS, ids=_ANSWER_IDS)
@pytest.mark.parametrize(
    "target",
    [
        (_load_model_info, "o/m", {}, MODEL_INFO_OUTCOME, repo_page_url("o/m")),
        (
            _load_dataset_info,
            "o/d",
            None,
            DATASET_INFO_OUTCOME,
            repo_page_url("o/d", "dataset"),
        ),
    ],
    ids=["model-info", "dataset-info"],
)
def test_a_hub_that_answers_wrongly_is_one_coded_warning(
    hub: _Hub,
    caplog: pytest.LogCaptureFixture,
    answer: tuple[int, bytes, dict[str, str], Any],
    target: tuple[Any, str, object, str, str],
) -> None:
    """*answer*: status, body, headers and the entry said; *target*: the
    loader, its repository, the empty result, the outcome and the page."""
    status, body, headers, entry = answer
    loader, repo, empty, outcome, page = target
    hub.answer(status, body, headers)
    assert loader(repo) == empty
    assert [p for p in hub.requests if f"/{repo}" in p], "the request never arrived"
    (warning,) = _warnings(caplog)
    assert getattr(warning, CODE_ATTR) == entry.code
    text = warning.getMessage()
    assert text.startswith(f"URL={page}: ") and text.endswith(f"; {outcome}")
    assert "\n" not in text


def test_the_reader_goes_on_without_the_hub_api(
    hub: _Hub, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The failed ``model_info()`` leaves the model with what its files give:
    the reader returns it, with the two lines of what was lost and of the
    revision not stated."""
    hub.answer(404, b'{"error": "Repository not found"}', _JSON)

    def serve(
        repo_id: str, filename: str, *, revision: str | None, repo_type: str
    ) -> Path | None:
        assert (repo_id, revision, repo_type) == ("o/m", None, "model")
        if filename != "config.json":
            return None
        path = tmp_path / filename
        path.write_bytes(b'{"model_type": "bert"}')
        return path

    with patch_hub_fetch(serve):
        model = read_huggingface("o/m")
    assert hub.requests, "the request never arrived"
    assert model.name == "m" and model.supplier is None
    assert model.type_of_model == "bert"  # read from config.json all the same
    assert [getattr(r, CODE_ATTR) for r in _warnings(caplog)] == [
        DOWNLOAD_FAILED.code,
        HUB_REVISION_UNPINNED.code,
    ]


def test_the_fetch_keeps_no_hub_info_after_a_failed_request(
    hub: _Hub, tmp_path: Path
) -> None:
    hub.answer(200, b"{not json", _JSON)
    json_file = tmp_path / "x.json"
    json_file.write_bytes(b"{}")
    data = _fetch_all_hf_data(fake_hub(json_file), "o/m")
    assert not data["hub_info"] and hub.requests


# -- what the server wrote is on one masked line -------------------------------

_HOSTILE = f"bad\nWARNING: forged\x1b[2J Bearer {_TOKEN}\t{_TOKEN} [over-cap]"


@pytest.mark.parametrize("status", [404, 401, 500])
def test_the_servers_words_reach_the_line_on_one_masked_line(
    hub: _Hub, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    """The error text of the server is the line's failure: a control
    character, a line break, a token and a fake code in it end on one tagged
    line."""
    hub.answer(status, json.dumps({"error": _HOSTILE}).encode(), _JSON)
    configure_logging()
    assert not _load_model_info("o/m")
    (line,) = capsys.readouterr().err.splitlines()
    assert line.startswith("WARNING: URL=")
    assert line.endswith(f" [{DOWNLOAD_FAILED.code}]")
    assert "hf_***" in line, "the server's text did not reach the line"
    assert _TOKEN not in line and "\x1b" not in line
    assert trusted_message(line) is DOWNLOAD_FAILED


@pytest.mark.parametrize("status", [404, 500])
def test_a_long_error_body_is_cut_to_a_trusted_line(
    hub: _Hub, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    """``huggingface_hub`` puts the server's body in the exception's text: a
    100 KB page is one line a reader still trusts, with what is lost at its
    end."""
    hub.answer(status, json.dumps({"error": "e " * 50_000}).encode(), _JSON)
    configure_logging()
    assert not _load_model_info("o/m")
    (line,) = capsys.readouterr().err.splitlines()
    assert len(line) < 1_500 and "..." in line
    assert line.endswith(f" [{DOWNLOAD_FAILED.code}]")
    assert MODEL_INFO_OUTCOME in line
    assert trusted_message(line) is DOWNLOAD_FAILED
