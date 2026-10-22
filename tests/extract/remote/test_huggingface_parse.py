# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for Hugging Face model ID parsing and source detection."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.remote import is_git_url
from pitloom.extract.remote.huggingface import (
    is_huggingface_source,
    parse_hf_model_id,
    read_huggingface,
)
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
        ("Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-235B-A22B"),
        (
            "openthaigpt/openthaigpt-r1-32b-instruct",
            "openthaigpt/openthaigpt-r1-32b-instruct",
        ),
    ],
)
def test_parse_hf_model_id_valid(source: str, expected_id: str) -> None:
    assert parse_hf_model_id(source) == expected_id


@pytest.mark.parametrize(
    "source",
    [
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


def test_parse_hf_model_id_owner_name_shape_with_local_dir_is_not_hf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A string that has the ``owner/name`` shape is rejected when a local
    directory of that relative path actually exists -- it's treated as a
    relative project path, not a Hugging Face model ID."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models" / "my-model").mkdir(parents=True)
    assert parse_hf_model_id("models/my-model") is None


def test_is_huggingface_source_url() -> None:
    assert is_huggingface_source("https://huggingface.co/mistralai/Mistral-7B-v0.1")


def test_is_huggingface_source_model_id() -> None:
    assert is_huggingface_source("Qwen/Qwen3-235B-A22B")


def test_is_huggingface_source_local_path() -> None:
    assert not is_huggingface_source("/path/to/model.onnx")


def test_is_huggingface_source_plain_filename() -> None:
    assert not is_huggingface_source("model.safetensors")


@pytest.mark.parametrize("url", [*_SPELLINGS, "https://github.com/org/hf.co"])
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
    infos = [m for m in caplog.messages if m.startswith("Hugging Face URL ")]
    assert infos == (
        [f"Hugging Face URL {source} is read as https://huggingface.co/org/mdl"]
        if said
        else []
    )
