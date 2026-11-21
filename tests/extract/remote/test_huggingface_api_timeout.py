# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0
"""The ``model_info()`` and ``dataset_info()`` requests carry a timeout: a Hub
that accepts the connection and never answers ends in the one ``WARNING:`` of a
failed request, not in a run that waits for ever (``huggingface_hub`` sets none
of its own).

See also: tests/extract/remote/test_huggingface_fetch.py (what the readers
return) and tests/extract/remote/test_huggingface_dataset.py.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub import constants as hf_constants
from huggingface_hub import hf_api

from pitloom.extract.remote._http_fetch import SOCKET_TIMEOUT_SECONDS
from pitloom.extract.remote.huggingface_dataset import _load_dataset_info
from pitloom.extract.remote.huggingface_fetch import _load_model_info

pytestmark = [pytest.mark.platform, pytest.mark.loopback]  # sockets, threads

#: How long a call may take with the timeout cut to a fraction of a second.
_BOUND_SECONDS = 30.0


@pytest.fixture(name="silent_hub")
def _silent_hub(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[socket.socket]]:
    """A loopback server that accepts connections and never answers, as the
    Hub endpoint ``huggingface_hub`` talks to. Yields the accepted
    connections, so a test can tell the request reached it."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)
    server.settimeout(0.1)
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        while not stop.is_set():
            try:
                held.append(server.accept()[0])
            except TimeoutError:
                continue
            except OSError:
                return

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.getsockname()[1]}"
    monkeypatch.setattr(hf_api.api, "endpoint", url)
    # An offline environment fails before any socket is opened.
    monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False)
    try:
        yield held
    finally:
        stop.set()
        thread.join(5)
        server.close()
        for conn in held:
            conn.close()


def _finishes(call: Callable[[], Any], timeout: float) -> bool:
    """Whether *call* returns within *timeout* seconds (a daemon thread: one
    that never does is left behind, not waited for)."""
    done = threading.Event()

    def run() -> None:
        call()
        done.set()

    threading.Thread(target=run, daemon=True).start()
    return done.wait(timeout)


@pytest.mark.parametrize(
    ("loader", "patched"),
    [
        (_load_model_info, "model_info"),
        (_load_dataset_info, "dataset_info"),
    ],
    ids=["model-info", "dataset-info"],
)
def test_the_request_is_given_the_socket_timeout(
    loader: Callable[[str], Any], patched: str
) -> None:
    """The value is the one every other Pitloom request uses."""
    with patch(f"huggingface_hub.{patched}", return_value=MagicMock()) as request:
        loader("org/x")
    assert request.call_args.kwargs["timeout"] == SOCKET_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("module", "loader", "failed"),
    [
        ("huggingface_fetch", _load_model_info, {}),
        ("huggingface_dataset", _load_dataset_info, None),
    ],
    ids=["model-info", "dataset-info"],
)
def test_a_hub_that_never_answers_is_one_failed_request(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    silent_hub: list[socket.socket],
    module: str,
    loader: Callable[[str], Any],
    failed: object,
) -> None:
    monkeypatch.setattr(f"pitloom.extract.remote.{module}.SOCKET_TIMEOUT_SECONDS", 0.5)
    result: list[object] = []
    assert _finishes(lambda: result.append(loader("org/x")), _BOUND_SECONDS)
    assert result == [failed]
    assert silent_hub, "the request never reached the silent server"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "Failed to load" in warnings[0].getMessage()
