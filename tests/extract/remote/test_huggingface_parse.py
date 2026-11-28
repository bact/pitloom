# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Hugging Face model ID parsing and source detection."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_model_sbom
from pitloom.core.dataset_names import is_hub_repo_id
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.extract.remote import is_git_url
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.huggingface import (
    is_huggingface_source,
    parse_hf_model_id,
    read_huggingface,
    require_hf_model_id,
    url_revision,
)
from pitloom.messages import CodedValueError
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls

_SPELLINGS = [
    "https://huggingface.co/org/mdl",
    "https://www.huggingface.co/org/mdl",
    "https://hf.co/org/mdl",
    "https://HuggingFace.co/org/mdl",
    "http://huggingface.co/org/mdl/tree/main",
]


@pytest.mark.parametrize(
    ("source", "expected_id"),
    [
        (
            "https://huggingface.co/mistralai/Mistral-7B-v0.1",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "https://huggingface.co/mistralai/Mistral-7B-v0.1/tree/main",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "https://huggingface.co/Qwen/Qwen3-235B-A22B",
            "Qwen/Qwen3-235B-A22B",
        ),
        (
            "https://huggingface.co/Qwen/Qwen3-235B-A22B/blob/main/config.json",
            "Qwen/Qwen3-235B-A22B",
        ),
        (
            "https://huggingface.co/openthaigpt/openthaigpt-r1-32b-instruct",
            "openthaigpt/openthaigpt-r1-32b-instruct",
        ),
        (
            "https://www.huggingface.co/mistralai/Mistral-7B-v0.1",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "https://hf.co/mistralai/Mistral-7B-v0.1/tree/main",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "HTTPS://HuggingFace.CO/mistralai/Mistral-7B-v0.1",
            "mistralai/Mistral-7B-v0.1",
        ),
        (
            "http://huggingface.co/mistralai/Mistral-7B-v0.1",
            "mistralai/Mistral-7B-v0.1",
        ),
        ("mistralai/Mistral-7B-v0.1", "mistralai/Mistral-7B-v0.1"),
        ("o/m", "o/m"),
        ("https://hf.co/o/m", "o/m"),
        ("Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-235B-A22B"),
        (
            "openthaigpt/openthaigpt-r1-32b-instruct",
            "openthaigpt/openthaigpt-r1-32b-instruct",
        ),
    ],
)
def test_parse_hf_model_id_valid(source: str, expected_id: str) -> None:
    assert parse_hf_model_id(source) == expected_id


#: A Space or a dataset is a Git repository, not a model.
_GIT_AREAS = [
    "https://huggingface.co/spaces/org/app",
    "https://huggingface.co/datasets/org/data",
    "https://hf.co/spaces/org/app/tree/main/src",
    "https://www.HuggingFace.co/Datasets/org/data",
    "http://huggingface.co/SPACES/org/app/blob/main/app.py",
]


@pytest.mark.parametrize(
    "source",
    [
        *_GIT_AREAS,
        "/path/to/model.safetensors",
        "./models/my_model.gguf",
        "just-a-filename.onnx",
        "https://example.com/model",
        "https://github.com/owner/hf.co",
        "https://huggingface.co.evil.example/owner/name",
        "https://huggingface.co/owner",
        "",
    ],
)
def test_parse_hf_model_id_invalid(source: str) -> None:
    assert parse_hf_model_id(source) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://huggingface.co/gpt2/tree/main", "gpt2"),
        ("https://hf.co/gpt2/blob/main/README.md", "gpt2"),
        ("https://huggingface.co/gpt2/resolve/0123abc/config.json", "gpt2"),
        ("https://huggingface.co/gpt2/commits/main?p=1", "gpt2"),
        ("https://huggingface.co/gpt2/discussions/12", "gpt2"),
        ("https://huggingface.co/gpt2/commit/0123abc", "gpt2"),
        ("https://huggingface.co/gpt2/raw/main/README.md", "gpt2"),
        ("https://huggingface.co/gpt2/blame/main/README.md", "gpt2"),
        ("https://huggingface.co/gpt2/edit/main/README.md", "gpt2"),
        ("https://huggingface.co/gpt2/compare/main", "gpt2/compare"),
        ("https://huggingface.co/org/tree/settings", "org/tree"),
        ("https://huggingface.co/gpt2/settings", "gpt2/settings"),
        ("https://huggingface.co/org/name/tree/v1.0", "org/name"),
        ("https://huggingface.co/org/name/blob/main/README.md", "org/name"),
        ("https://huggingface.co/org/tree/tree/main", "org/tree"),
        ("https://huggingface.co/org/tree/blob/main/x", "org/tree"),
        ("https://huggingface.co/org/tree", "org/tree"),
        ("https://huggingface.co/org/discussions", "org/discussions"),
        ("https://huggingface.co/gpt2/Tree/main", "gpt2/Tree"),
    ],
    ids=[
        "legacy-tree",
        "legacy-blob",
        "legacy-resolve",
        "legacy-query",
        "legacy-discussion",
        "legacy-commit",
        "legacy-raw",
        "legacy-blame",
        "legacy-edit",
        "no-such-page",
        "model-named-tree-settings",
        "bare-page-two-parts",
        "two-part-tree",
        "two-part-blob",
        "model-named-tree",
        "model-named-tree-blob",
        "model-named-tree-bare",
        "model-named-discussions",
        "page-case",
    ],
)
def test_a_page_of_a_one_part_id_names_that_id(url: str, expected: str) -> None:
    """The Hub keeps a one-part id for a model it moved (``gpt2``, now
    ``openai-community/gpt2``): a page of it, ``<id>/<page>/<part>``, names
    that id, so the model is read, not refused as unknown (each page kind
    measured on the Hub, 2026-11-27; ``compare`` is none). A model named
    like a page (``org/tree``) is read as two parts: the part after a page
    is never a page itself, and a page needs a part after it. The Hub's
    paths are case-sensitive."""
    assert parse_hf_model_id(url) == expected


@pytest.mark.platform  # a symbolic link
def test_a_dangling_link_of_an_id_shape_is_not_hf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Something is at the path, a link to nothing: it is a local path, and
    a Hub refusal would wrongly say it is none."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    try:
        (tmp_path / "models" / "gone").symlink_to(tmp_path / "nowhere")
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"cannot make a symbolic link: {exc}")
    assert parse_hf_model_id("models/gone") is None


def test_parse_hf_model_id_owner_name_shape_with_local_dir_is_not_hf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A string that has the ``owner/name`` shape is rejected when a local
    directory of that relative path actually exists -- it's treated as a
    relative project path, not a Hugging Face model ID."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models" / "my-model").mkdir(parents=True)
    assert parse_hf_model_id("models/my-model") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://hf.co/o/m",
        "https://huggingface.co/a/b/tree/main",
        "https://huggingface.co/owner/n?x=1",
    ],
    ids=["one-char-name", "one-char-both", "query"],
)
def test_the_id_read_from_a_url_is_itself_a_model_source(url: str) -> None:
    """A two-part id read from a URL is a model source again, as typed: a
    caller that passes it on, and the generator, agree."""
    model_id = parse_hf_model_id(url)
    assert model_id is not None
    assert is_huggingface_source(model_id)


def test_is_huggingface_source_url() -> None:
    assert is_huggingface_source("https://huggingface.co/mistralai/Mistral-7B-v0.1")


def test_is_huggingface_source_model_id() -> None:
    assert is_huggingface_source("Qwen/Qwen3-235B-A22B")


def test_is_huggingface_source_local_path() -> None:
    assert not is_huggingface_source("/path/to/model.onnx")


def test_is_huggingface_source_plain_filename() -> None:
    assert not is_huggingface_source("model.safetensors")


@pytest.mark.parametrize(
    "url", [*_SPELLINGS, *_GIT_AREAS, "https://github.com/org/hf.co"]
)
def test_a_url_is_a_model_or_a_git_repository_never_both_or_neither(url: str) -> None:
    """Drift guard: the Git route and the Hub route decide on one host list."""
    assert (parse_hf_model_id(url) is not None) != is_git_url(url)


@pytest.mark.parametrize(
    ("source", "said"),
    [
        (_SPELLINGS[0], False),
        ("https://huggingface.co/org/mdl/tree/main", False),
        ("org/mdl", False),
        (_SPELLINGS[1], True),
        (_SPELLINGS[2], True),
        (_SPELLINGS[3], True),
        (_SPELLINGS[4], True),
    ],
    ids=["canonical", "canonical-page", "bare-id", "www", "hf-co", "case", "http"],
)
def test_a_url_read_in_another_spelling_is_said_once(
    caplog: pytest.LogCaptureFixture, source: str, said: bool
) -> None:
    """One INFO names the spelling given and the URL it is read as; none for
    the canonical form, a page under it or a bare model id."""
    with _patch_hf_calls(), caplog.at_level(logging.INFO, logger="pitloom"):
        meta = read_huggingface(source)
    assert meta.name == "mdl"
    infos = [
        r.getMessage()
        for r in caplog.records
        if getattr(r, "pitloom_code", None) == "target-ambiguous/hf-url"
    ]
    assert infos == (
        [f"URL={source}: read as Hugging Face model https://huggingface.co/org/mdl"]
        if said
        else []
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/o/m?private_token=SECRET",
        "https://huggingface.co/o/m#frag",
        "https://huggingface.co/o/m/tree/main?x=1",
    ],
)
def test_a_query_or_fragment_is_no_part_of_the_model_id(url: str) -> None:
    """A model id holds no ``?`` or ``#``: a token in the query must not end up
    in the id, and so in a message or a request."""
    assert parse_hf_model_id(url) == "o/m"


#: Ids at each edge of the Hub's rule, and whether ``huggingface_hub`` takes
#: each.
_IDS = [
    pytest.param("a/b--c", False, id="dashes"),
    pytest.param("a/b..c", False, id="dots"),
    pytest.param("a/b.git", False, id="git"),
    pytest.param("a/b-", False, id="dash-end"),
    pytest.param("a/b.", False, id="dot-end"),
    pytest.param("-a/b", False, id="dash-start"),
    pytest.param("a/" + "x" * 97, False, id="long"),
    pytest.param("a/b_", True, id="underscore-end"),
    pytest.param("_a/b", True, id="underscore-owner"),
    pytest.param("a/_b", True, id="underscore-name"),
    pytest.param("a/b.c", True, id="dot-inside"),
    pytest.param("a-b/c", True, id="dash-inside"),
    pytest.param("a/" + "x" * 96, True, id="longest"),
]


@pytest.mark.parametrize(("model_id", "valid"), _IDS)
def test_a_url_names_a_model_only_by_an_id_the_hub_can_hold(
    model_id: str, valid: bool
) -> None:
    """A Hub URL whose id the Hub itself refuses names no model:
    ``hf-url-invalid`` before any request, not "not found" advice; a bare
    one is a path, not a model."""
    url = f"https://huggingface.co/{model_id}"
    assert parse_hf_model_id(url) == (model_id if valid else None)
    assert parse_hf_model_id(model_id) == (model_id if valid else None)
    if not valid:
        with pytest.raises(CodedValueError) as raised:
            require_hf_model_id(url)
        assert raised.value.pitloom_code == "hf-url-invalid"


@pytest.mark.parametrize(
    "repo_id", [*(p.values[0] for p in _IDS), "gpt2", "_", "a/b/c", "a b/c"]
)
def test_the_id_rule_agrees_with_huggingface_hub(repo_id: str) -> None:
    """Drift guard: Pitloom refuses exactly the ids ``huggingface_hub``
    refuses, so no model the Hub can hold is refused."""
    hub_utils = pytest.importorskip("huggingface_hub.utils")
    try:
        hub_utils.validate_repo_id(repo_id)
    except hub_utils.HFValidationError:
        hub_takes = False
    else:
        hub_takes = True
    assert is_hub_repo_id(repo_id) is hub_takes


_HF = "https://huggingface.co"


@pytest.mark.parametrize(
    ("url", "revision"),
    [
        pytest.param(f"{_HF}/o/m/tree/0123abc", "0123abc", id="tree"),
        pytest.param(f"{_HF}/o/m/blob/v1.0/README.md", "v1.0", id="blob"),
        pytest.param(f"{_HF}/o/m/commit/deadbeef", "deadbeef", id="commit"),
        pytest.param(f"{_HF}/o/m/resolve/dev/config.json", "dev", id="resolve"),
        pytest.param(f"{_HF}/o/m/tree/0123abc?x=1#y", "0123abc", id="query"),
        pytest.param(f"{_HF}/gpt2/tree/0123abc", "0123abc", id="one-part-id"),
        pytest.param(f"{_HF}/o/m/tree/refs/pr/1/sub", "refs/pr/1", id="hub-ref"),
        pytest.param(f"{_HF}/o/m/tree/refs%2Fpr%2F1", "refs%2Fpr%2F1", id="encoded"),
        pytest.param(f"{_HF}/o/m/tree/Main", "Main", id="case"),
        pytest.param(f"{_HF}/o/m/tree/refs/pr", "refs", id="refs-short"),
        pytest.param(f"{_HF}/o/m/tree/refs/heads/main", None, id="main-ref"),
        pytest.param(f"{_HF}/o/m/tree/refs%2Fheads%2Fmain", None, id="main-ref-enc"),
        pytest.param(f"{_HF}/o/m/tree/main", None, id="main"),
        pytest.param(f"{_HF}/o/m/tree/%6Dain", None, id="encoded-main"),
        pytest.param(f"{_HF}/o/m/tree/main/sub", None, id="main-folder"),
        pytest.param(f"{_HF}/o/m/discussions/3", None, id="discussions"),
        pytest.param(f"{_HF}/o/m/tree", None, id="page-only"),
        pytest.param(f"{_HF}/o/m?tab=files", None, id="tab"),
        pytest.param("o/m", None, id="bare-id"),
    ],
)
def test_the_revision_a_url_names(url: str, revision: str | None) -> None:
    assert url_revision(url) == revision


def _read_online(url: str) -> None:
    assert read_huggingface(url).name == "m"


def _read_offline(url: str) -> None:
    with pytest.raises(RemoteSourceError):
        read_huggingface(url, policy=RemoteFetchPolicy(offline=True))


def _model_sbom(url: str) -> None:
    with pytest.raises(RemoteSourceError):
        generate_model_sbom(url, offline=True)


def _generate(url: str) -> None:
    with pytest.raises(RemoteSourceError):
        generate(url, offline=True)


def _cli(url: str) -> None:
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(sys, "argv", ["loom", "model", url, "--offline"])
        assert __main__.main() == 1


@pytest.mark.parametrize(
    "read",
    [_read_online, _read_offline, _model_sbom, _generate, _cli],
    ids=["read", "read-offline", "generate_model_sbom", "generate", "cli"],
)
@pytest.mark.parametrize(
    ("url", "said"),
    [
        pytest.param(
            f"{_HF}/o/m/tree/0123abc",
            f"URL={_HF}/o/m/tree/0123abc: the URL names the revision 0123abc",
            id="revision",
        ),
        pytest.param(
            f"{_HF}/o/m/blob/v1/README.md?token=S3CRET",
            f"URL={_HF}/o/m/blob/v1/README.md?token=***: the URL names the revision v1",
            id="credential",
        ),
        pytest.param(f"{_HF}/o/m/tree/main", None, id="main"),
        pytest.param(f"{_HF}/o/m", None, id="no-revision"),
    ],
)
def test_a_revision_the_files_are_not_read_at_is_said_once(
    caplog: pytest.LogCaptureFixture,
    read: Callable[[str], None],
    url: str,
    said: str | None,
) -> None:
    """One WARNING names the URL, its revision and that the default branch is
    read, before anything is fetched (offline too), on every route;
    none for ``main`` or no revision."""
    with _patch_hf_calls(), caplog.at_level(logging.INFO, logger="pitloom"):
        read(url)
    warnings = [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if getattr(r, "pitloom_code", None) == "hub-revision-unpinned/url"
    ]
    tail = "; files are read at the default branch"
    assert warnings == ([(logging.WARNING, said + tail)] if said else [])
    assert "S3CRET" not in caplog.text
