# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hugging Face target the Hub knows no model for is an error
(``input-not-found/hub``): no file of it is fetched, no SBOM is written,
``loom generate`` and ``loom model`` exit 1 and ``generate()`` and
``generate_model_sbom()`` raise, whether it is spelt as an id (which is no
local path either, and the line says so) or as a URL. The Hub answers a
private model asked for without a token as it answers a missing one (a
401), so the line says how to send a token. A gated model, and every other
failure of ``model_info()``, keep their ``WARNING:``.

The answers are ``huggingface_hub``'s own exceptions, raised by its
``hf_raise_for_status`` from the responses the Hub was measured to send
(working-docs/implementation/pre-release-review-0.25.0.md, "CLI-7").

See also: tests/extract/remote/test_hub_api.py (the other failures),
tests/extract/remote/test_hub_repository_not_found_live.py (the real Hub)
and tests/extract/remote/test_huggingface_parse.py (what is an id).
"""

from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import huggingface_hub
import pytest
from huggingface_hub import hf_raise_for_status
from huggingface_hub.errors import HfHubHTTPError

from pitloom import __main__
from pitloom.assemble import generate, generate_model_sbom
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import _hub_api, _hub_files
from pitloom.extract.remote._hub_api import (
    REPOSITORY_NOT_FOUND,
    is_repository_not_found,
    repo_page_url,
)
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.huggingface import read_huggingface
from pitloom.extract.remote.huggingface_dataset import _load_dataset_info
from pitloom.extract.remote.huggingface_fetch import _load_model_info
from pitloom.logging_config import configure_logging
from pitloom.messages import Line
from pitloom.messages.network import DOWNLOAD_FAILED
from pitloom.messages.targets import (
    HUB_ID_NOT_FOUND_LINE,
    HUB_URL_NOT_FOUND_LINE,
    INPUT_NOT_FOUND_HUB,
)
from tests._message_drift import raised_as

pytestmark = pytest.mark.platform  # the CLI's exit code, cwd and -o paths

#: What an anonymous request for a missing (or private) model is answered.
_ANONYMOUS = (401, {"X-Error-Message": "Invalid username or password."})


def _text(line: Line, model_id: str = "h/nope") -> str:
    """*line* as it is said of *model_id*, at its page on the Hub asked."""
    values = {"path": model_id, "url": repo_page_url(model_id)}
    return line.render({k: v for k, v in values.items() if f"%({k})s" in line.template})


def _raised(model_id: str, status: int, headers: dict[str, str]) -> Exception:
    """What ``huggingface_hub`` raises for a *status* answer with *headers*
    to ``model_info(model_id)``, its response of the HTTP client the
    library uses (``httpx`` from 1.0, ``httpx2`` in 2.x)."""
    client = importlib.import_module(
        HfHubHTTPError.__mro__[1].__module__.split(".", 1)[0]
    )
    url = f"https://huggingface.co/api/models/{model_id}"
    request = client.Request("GET", url)
    response = client.Response(status, headers=headers, request=request)
    with pytest.raises(HfHubHTTPError) as raised:
        hf_raise_for_status(response)
    return raised.value


@pytest.mark.parametrize(
    ("status", "headers", "refused"),
    [
        (*_ANONYMOUS, True),
        (404, {"X-Error-Code": "RepoNotFound"}, True),
        (401, {"X-Error-Code": "GatedRepo"}, False),
        (
            401,
            {"X-Error-Message": "Invalid credentials in Authorization header"},
            False,
        ),
        (403, {"X-Error-Message": "Access to this resource is disabled."}, False),
        (403, {}, False),
        (500, {}, False),
    ],
    ids=["anonymous", "not-found", "gated", "bad-token", "disabled", "403", "500"],
)
def test_only_a_repository_not_found_is_refused(
    status: int, headers: dict[str, str], refused: bool
) -> None:
    """A gated repository is found (``GatedRepoError`` is a subclass of
    ``RepositoryNotFoundError``); a token the Hub calls invalid, a disabled
    repository and every server error are other failures."""
    assert is_repository_not_found(_raised("h/nope", status, headers)) is refused


def test_another_exception_is_not_refused() -> None:
    assert not is_repository_not_found(TimeoutError("t"))


def _fetched(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("a file was fetched")


@pytest.fixture(name="answer")
def _answer(monkeypatch: pytest.MonkeyPatch) -> Callable[[int, dict[str, str]], None]:
    """Make ``model_info()`` raise what the Hub's answer would raise, and
    fail any file download: a refusal fetches no file."""

    monkeypatch.setattr(_hub_files, "fetch_capped", _fetched)

    def set_answer(status: int, headers: dict[str, str]) -> None:
        def model_info(repo_id: str, **_kwargs: object) -> Any:
            raise _raised(repo_id, status, headers)

        monkeypatch.setattr(huggingface_hub, "model_info", model_info)

    return set_answer


@pytest.mark.parametrize("as_id", [True, False], ids=["id", "url"])
def test_model_info_raises_the_line_of_its_spelling(
    answer: Callable[[int, dict[str, str]], None], as_id: bool
) -> None:
    answer(*_ANONYMOUS)
    with pytest.raises(RemoteSourceError) as raised:
        _load_model_info("h/nope", as_id=as_id)
    line = HUB_ID_NOT_FOUND_LINE if as_id else HUB_URL_NOT_FOUND_LINE
    assert raised.value.code == REPOSITORY_NOT_FOUND
    assert raised_as(raised.value, INPUT_NOT_FOUND_HUB)
    assert str(raised.value) == _text(line)
    assert "HF_TOKEN" in str(raised.value)


def test_the_line_names_the_hub_asked(
    answer: Callable[[int, dict[str, str]], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``HF_ENDPOINT`` naming another Hub, that Hub is named."""
    monkeypatch.setattr(_hub_api, "hub_endpoint", lambda: "https://hub.example")
    answer(*_ANONYMOUS)
    with pytest.raises(RemoteSourceError) as raised:
        _load_model_info("h/nope", as_id=False)
    assert str(raised.value).startswith("URL=https://hub.example/h/nope: ")


def test_a_gated_answer_keeps_its_warning(
    answer: Callable[[int, dict[str, str]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    answer(401, {"X-Error-Code": "GatedRepo"})
    assert not _load_model_info("h/gated", as_id=True)
    assert f"[{DOWNLOAD_FAILED.code}]" in capsys.readouterr().err


@pytest.fixture(name="refusing_hub")
def _refusing_hub(
    answer: Callable[[int, dict[str, str]], None],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[Path]:
    """The Hub answers every model "not found"; the working directory is
    empty, so no target is a local path."""
    monkeypatch.chdir(tmp_path)
    answer(*_ANONYMOUS)
    yield tmp_path / "out.json"


def _cli(monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["loom", *args])
    return __main__.main()


_ID_TEXT = "target not found: 'h/nope' is no local path, and the Hugging Face Hub"
_URL_TEXT = "URL=https://huggingface.co/h/nope: the Hugging Face Hub knows no such"


@pytest.mark.parametrize("command", ["generate", "model"])
@pytest.mark.parametrize(
    ("target", "text"),
    [("h/nope", _ID_TEXT), ("https://hf.co/h/nope", _URL_TEXT)],
    ids=["id", "url"],
)
def test_the_cli_exits_1_and_writes_nothing(
    refusing_hub: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    target: str,
    text: str,
) -> None:
    out = refusing_hub
    assert _cli(monkeypatch, command, target, "-o", str(out)) == 1
    err = capsys.readouterr().err
    assert f"ERROR: loom {command}: {text}" in err
    assert f"[{INPUT_NOT_FOUND_HUB.code}]" in err
    # Nothing more is said of the model: no file, no revision warning.
    assert "WARNING" not in err
    assert not out.exists()


@pytest.mark.parametrize(
    "call", [generate, generate_model_sbom], ids=["generate", "generate-model"]
)
@pytest.mark.parametrize(
    ("target", "line"),
    [
        ("h/nope", HUB_ID_NOT_FOUND_LINE),
        (" h/nope ", HUB_ID_NOT_FOUND_LINE),
        ("https://hf.co/h/nope", HUB_URL_NOT_FOUND_LINE),
        ("http://huggingface.co/h/nope", HUB_URL_NOT_FOUND_LINE),
        (" HTTPS://huggingface.co/h/nope/tree/main ", HUB_URL_NOT_FOUND_LINE),
    ],
    ids=["id", "padded-id", "url", "http-url", "padded-upper-url"],
)
def test_the_library_raises_and_writes_nothing(
    refusing_hub: Path,
    caplog: pytest.LogCaptureFixture,
    call: Callable[..., str],
    target: str,
    line: Line,
) -> None:
    out = refusing_hub
    with caplog.at_level(logging.WARNING), pytest.raises(RemoteSourceError) as raised:
        call(target, output_path=out)
    assert raised.value.code == REPOSITORY_NOT_FOUND
    assert str(raised.value) == _text(line)
    assert not [r for r in caplog.records if r.name.startswith("pitloom")]
    assert not out.exists()


def test_loom_model_reads_a_url_as_a_url(
    refusing_hub: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom model`` gives the library the URL as typed, as ``loom
    generate`` does: the page of a model with a one-part id names that id,
    and a refusal names no local path."""
    out = refusing_hub
    url = "https://huggingface.co/gpt2/tree/main"
    assert _cli(monkeypatch, "model", url, "-o", str(out)) == 1
    err = capsys.readouterr().err
    assert "URL=https://huggingface.co/gpt2: the Hugging Face Hub knows" in err
    assert "model file not found" not in err and "local path" not in err


def test_read_huggingface_reads_a_padded_url_as_a_url(refusing_hub: Path) -> None:
    """``read_huggingface()`` is public and takes white space around a URL
    (``parse_hf_model_id``): the refusal names the URL, no local path."""
    del refusing_hub
    with pytest.raises(RemoteSourceError) as raised:
        read_huggingface("  https://huggingface.co/h/nope\n")
    assert str(raised.value) == _text(HUB_URL_NOT_FOUND_LINE)


def test_an_id_no_model_can_have_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``huggingface_hub`` refuses ``a/b--c`` before any request (the real
    ``model_info()``; no socket is opened): no model has that id, and it is
    no local path either."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_hub_files, "fetch_capped", _fetched)
    with pytest.raises(RemoteSourceError) as raised:
        generate_model_sbom("a/b--c")
    assert str(raised.value) == _text(HUB_ID_NOT_FOUND_LINE, "a/b--c")


@pytest.mark.parametrize(
    ("found", "read"),
    [({"gpt2"}, "gpt2"), (set(), None)],
    ids=["one-part-found", "neither-found"],
)
def test_a_bare_page_url_is_read_as_its_one_part_id(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    found: set[str],
    read: str | None,
) -> None:
    """``https://huggingface.co/gpt2/settings`` is no model ``gpt2/settings``:
    when the Hub knows none, its owner is read, with one ``INFO:``; when it
    knows neither, the refusal names the one-part id it asked last."""
    asked: list[str] = []

    def model_info(repo_id: str, **_kwargs: object) -> Any:
        asked.append(repo_id)
        if repo_id in found:
            raise TimeoutError("stands in for an answer: the read goes on")
        raise _raised(repo_id, *_ANONYMOUS)

    monkeypatch.setattr(huggingface_hub, "model_info", model_info)
    monkeypatch.setattr(_hub_files, "fetch_capped", _fetched)
    url = "https://huggingface.co/gpt2/settings"
    with caplog.at_level(logging.INFO, logger="pitloom"):
        if read is None:
            with pytest.raises(RemoteSourceError) as raised:
                read_huggingface(url)
            assert str(raised.value) == _text(HUB_URL_NOT_FOUND_LINE, "gpt2")
        else:
            with pytest.raises(AssertionError, match="a file was fetched"):
                read_huggingface(url)
    assert asked == ["gpt2/settings", "gpt2"]
    said = [r.getMessage() for r in caplog.records if r.name.startswith("pitloom")]
    assert (
        said[0] == f"URL={url}: read as Hugging Face model https://huggingface.co/gpt2"
    )


def test_an_id_spelt_as_such_is_not_read_again(
    monkeypatch: pytest.MonkeyPatch, refusing_hub: Path
) -> None:
    """``gpt2/settings`` typed as an id is that id: no second request."""
    del refusing_hub
    asked: list[str] = []

    def model_info(repo_id: str, **_kwargs: object) -> Any:
        asked.append(repo_id)
        raise _raised(repo_id, *_ANONYMOUS)

    monkeypatch.setattr(huggingface_hub, "model_info", model_info)
    with pytest.raises(RemoteSourceError):
        read_huggingface("gpt2/settings")
    assert asked == ["gpt2/settings"]


def test_a_dataset_the_hub_does_not_know_still_warns(
    answer: Callable[[int, dict[str, str]], None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the model a run reads is refused: a dataset its card lists that
    the Hub does not know is left out with a ``WARNING:``."""
    configure_logging()
    answer(*_ANONYMOUS)

    def dataset_info(repo_id: str, **_kwargs: object) -> Any:
        raise _raised(repo_id, *_ANONYMOUS)

    with patch("huggingface_hub.dataset_info", dataset_info):
        assert _load_dataset_info("o/d") is None
    assert f"[{DOWNLOAD_FAILED.code}]" in capsys.readouterr().err


def test_only_not_found_reads_a_bare_page_url_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Any other error reading ``org/settings`` (here a caller's
    ``check_url`` refusing its card) stands: the owner is not read
    instead."""
    monkeypatch.chdir(tmp_path)
    asked: list[str] = []

    def model_info(repo_id: str, **_kwargs: object) -> Any:
        asked.append(repo_id)
        raise TimeoutError("no answer: warned, and the files are read")

    def refuse(url: str) -> None:
        raise RemoteSourceError("caller.refused", f"refused {url}")

    monkeypatch.setattr(huggingface_hub, "model_info", model_info)
    policy = RemoteFetchPolicy(check_url=refuse)
    with pytest.raises(RemoteSourceError) as raised:
        read_huggingface("https://huggingface.co/org/settings", policy=policy)
    assert raised.value.code == "caller.refused"
    assert asked == ["org/settings"]
