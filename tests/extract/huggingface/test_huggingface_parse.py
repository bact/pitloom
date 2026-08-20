# ruff: noqa: F403, F405
from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract._huggingface import (
    parse_hf_model_id,
)


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
