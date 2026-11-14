# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hugging Face URL given where a project is read: ``loom project`` and
the library's project entry points refuse it alike, through
:func:`pitloom.extract.remote.huggingface.refuse_hub_model_target`
(``target-wrong-format`` for a model, ``hf-url-invalid`` for a Hub URL that
names none); the other entry points name it as given.

See also: tests/messages/test_input_wrong_kind.py (``loom model`` and
``loom generate`` on a malformed Hub URL).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom import __main__
from pitloom.assemble import (
    generate,
    generate_git_project_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.extract.remote import refuse_hub_model_target
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import CodedValueError

#: A URL that is no Hub model reaches a path check, read as Windows reads it.
pytestmark = pytest.mark.platform

_MODEL = "https://huggingface.co/owner/model"
_WRONG = "target-wrong-format"
_INVALID = "hf-url-invalid"
_NOT_PROJECT = ": a Hugging Face model, not a project; use 'loom model'"
_NOT_HUB = ": not a valid Hugging Face URL or model ID"

#: A URL, the code a project route refuses it with (``None``: not refused as
#: a Hugging Face URL) and the URL its line names.
_CORPUS = [
    (_MODEL, _WRONG, _MODEL),
    ("https://huggingface.co/owner", _INVALID, "https://huggingface.co/owner"),
    ("https://huggingface.co/", _INVALID, "https://huggingface.co/"),
    ("https://huggingface.co:8443/o/m", _INVALID, "https://huggingface.co:8443/o/m"),
    (
        "https://user:SECRET@huggingface.co/o/m",
        _INVALID,
        "https://***:***@huggingface.co/o/m",
    ),
    (f"  {_MODEL}\t", _WRONG, _MODEL),
    (f"{_MODEL}?token=SECRET", _WRONG, f"{_MODEL}?token=***"),
    ("https://huggingface.co/spaces/o/s", None, None),
    ("https://huggingface.co/datasets/o/d", None, None),
    ("git+https://huggingface.co/o/m", None, None),
]
_IDS = [
    "model",
    "one-segment",
    "bare-host",
    "port",
    "userinfo",
    "padded",
    "query-token",
    "space",
    "dataset",
    "git-plus",
]


def _hub_refusal(code: object, text: str) -> tuple[str, str] | None:
    """``(code, line)`` when *code* is a Hugging Face refusal, else ``None``."""
    return (str(code), text) if code in (_WRONG, _INVALID) else None


def _cli(
    url: str, monkeypatch: pytest.MonkeyPatch, err: pytest.CaptureFixture[str]
) -> tuple[str, str] | None:
    """``loom project <url> --offline``: what its last ``ERROR:`` line says."""
    monkeypatch.setattr(sys, "argv", ["loom", "project", url, "--offline"])
    status = __main__.main()
    lines = err.readouterr().err.splitlines()
    errors = [line for line in lines if line.startswith("ERROR: ")]
    if status == 0 or not errors:
        return None
    body, _, code = errors[-1].removeprefix("ERROR: loom project: ").rpartition(" [")
    return _hub_refusal(code.rstrip("]"), body)


def _library(call: Callable[..., Any], url: str) -> tuple[str, str] | None:
    """*call* of *url*, offline: the refusal it raises."""
    try:
        call(url, offline=True)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # any other failure is no Hub refusal
        return _hub_refusal(getattr(exc, CODE_ATTR, None), str(exc))
    return None  # pragma: no cover -- every corpus URL fails offline


@pytest.mark.parametrize(("url", "code", "named"), _CORPUS, ids=_IDS)
def test_the_command_line_and_the_library_classify_alike(
    url: str,
    code: str | None,
    named: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``loom project``, ``generate_project_sbom`` and
    ``generate_git_project_sbom`` refuse the same URLs with the same line,
    credentials masked; a Space, a dataset and a ``git+`` URL are no model
    to any of them."""
    monkeypatch.chdir(tmp_path)
    expected = None
    if code is not None:
        expected = (code, f"URL={named}{_NOT_PROJECT if code == _WRONG else _NOT_HUB}")
    said = {
        "cli": _cli(url, monkeypatch, capsys),
        "project": _library(generate_project_sbom, url),
        "git-project": _library(generate_git_project_sbom, url),
    }
    assert said == dict.fromkeys(said, expected)
    assert "SECRET" not in str(said)


@pytest.mark.parametrize(
    ("url", "code"),
    [(_MODEL, _WRONG), ("https://hf.co/owner", _INVALID)],
    ids=["model", "malformed"],
)
@pytest.mark.parametrize(
    "call", [generate_project_sbom, generate_git_project_sbom], ids=["dir", "git"]
)
def test_a_project_entry_point_raises_the_coded_value_error(
    call: Callable[..., str], url: str, code: str
) -> None:
    """A ``ValueError`` carrying the code, not a project path not found."""
    with pytest.raises(CodedValueError) as caught:
        call(url, offline=True)
    assert isinstance(caught.value, ValueError)
    assert not isinstance(caught.value, FileNotFoundError)
    assert getattr(caught.value, CODE_ATTR) == code
    assert str(caught.value).startswith(f"URL={url}: ")


@pytest.mark.parametrize(
    "target",
    [Path("owner/model"), "owner/model", "https://example.org/o/m", Path(_MODEL)],
    ids=["path", "bare-id", "other-host", "path-of-url"],
)
def test_anything_but_a_hub_url_string_passes(target: object) -> None:
    """A bare id may name a local directory, and a path object is local."""
    refuse_hub_model_target(target)


def test_generate_reads_a_malformed_hub_url_as_hf_url_invalid() -> None:
    with pytest.raises(ValueError) as caught:
        generate("https://huggingface.co/owner", offline=True)
    assert getattr(caught.value, CODE_ATTR) == _INVALID


@pytest.mark.parametrize(
    ("url", "named"),
    [
        (_MODEL, _MODEL),
        ("ftp://user:SECRET@h/x", "ftp://***:***@h/x"),
        ("https://h/x?token=SECRET", "https://h/x?token=***"),
    ],
    ids=["hub", "userinfo", "query-token"],
)
def test_generate_wheel_sbom_names_a_url_as_given_and_masked(
    url: str, named: str
) -> None:
    with pytest.raises(ValueError) as caught:
        generate_wheel_sbom(url)
    assert getattr(caught.value, CODE_ATTR) == _WRONG
    assert str(caught.value) == f"FILE={named}: not a .whl file"


_OFF = "--offline"


@pytest.mark.parametrize(
    ("argv", "call", "code"),
    [
        (["wheel", "https://h/x.whl?token=SECRET"], generate_wheel_sbom, _WRONG),
        (
            ["project", "https://github.com/o/r?access_token=SECRET", _OFF],
            generate_git_project_sbom,
            "offline-unusable",
        ),
        (
            [
                "generate",
                "https://github.com/o/r.git?X-Amz-Signature=SECRET",
                _OFF,
                "-o",
                "o",
            ],
            generate,
            "offline-unusable",
        ),
        (
            ["model", "https://u:SECRET@huggingface.co/o/n?token=SECRET", _OFF],
            generate_model_sbom,
            _INVALID,
        ),
    ],
    ids=["wheel-token", "git-access-token", "amz-signature", "userinfo"],
)
def test_a_masked_url_keeps_the_condition_on_every_surface(
    argv: list[str],
    call: Callable[..., Any],
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A secret value is masked to its end, not to the next ``;``: the
    ``ERROR:`` line says the library's text, condition and all."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 1
    (line,) = [
        text
        for text in capsys.readouterr().err.splitlines()
        if text.startswith("ERROR: ")
    ]
    with pytest.raises(Exception) as caught:
        call(argv[1], **({"offline": True} if _OFF in argv else {}))
    assert getattr(caught.value, CODE_ATTR) == code
    assert line == f"ERROR: loom {argv[0]}: {caught.value} [{code}]"
    assert "SECRET" not in line
    assert "***: " in line
