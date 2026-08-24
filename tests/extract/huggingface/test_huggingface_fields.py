# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Direct unit tests for pitloom.extract._huggingface_fields helpers.

Exercises branches that the higher-level ``read_huggingface()`` pipeline
(covered by the sibling ``test_huggingface_*.py`` modules) doesn't reach on
its own: an empty extracted card description, a ``base_model:`` tag with an
unrecognised relation, empty ``arxiv:``/``dataset:`` tag values, and a
tokenizer config with no ``tokenizer_class``.

See also: the topic-grouped hf_patches/_hf_patches_*.py submodules for the
shared mock-HF-API helpers used by the higher-level tests.
"""

from __future__ import annotations

from unittest.mock import patch

from pitloom.extract._huggingface_fields import (
    _extract_description,
    _parse_info_tags,
    _populate_tokenizer_info,
)

# ---------------------------------------------------------------------------
# _extract_description
# ---------------------------------------------------------------------------


def test_extract_description_empty_result_sets_no_provenance() -> None:
    # card_text is present, but _extract_card_description() finds no prose
    # paragraph (e.g. YAML frontmatter with nothing after it) -> desc is
    # None/falsy, so no "description" provenance entry is recorded.
    hf_data = {"card_text": "---\nlicense: mit\n---\n"}
    with patch(
        "pitloom.extract._huggingface_fields._extract_card_description",
        return_value=None,
    ):
        provenance: dict[str, str] = {}
        desc = _extract_description(hf_data, provenance)

    assert desc is None
    assert "description" not in provenance


# ---------------------------------------------------------------------------
# _parse_info_tags
# ---------------------------------------------------------------------------


def test_parse_info_tags_unrecognised_base_model_relation_ignored() -> None:
    # "base_model:xyz:some/model" has the "base_model:{relation}:{id}"
    # shape, but "xyz" isn't a recognised relation keyword, so it's skipped
    # and base_model_relation stays None.
    result = _parse_info_tags(["base_model:xyz:some/model"])
    assert result.base_model_relation is None


def test_parse_info_tags_empty_arxiv_value_skipped() -> None:
    # "arxiv:" with only whitespace after the prefix strips to "" -- falsy,
    # so it's not appended to arxiv_ids.
    result = _parse_info_tags(["arxiv:   "])
    assert result.arxiv_ids == []


def test_parse_info_tags_empty_dataset_value_skipped() -> None:
    # "dataset:" with only whitespace after the prefix strips to "" --
    # falsy, so it's not appended to info_dataset_ids.
    result = _parse_info_tags(["dataset:   "])
    assert result.info_dataset_ids == []


def test_parse_info_tags_mixed_valid_and_invalid_tags() -> None:
    # A realistic mix: valid arxiv/dataset entries alongside the
    # empty/unrecognised ones above, all in a single tag list.
    result = _parse_info_tags(
        [
            "base_model:xyz:some/model",
            "arxiv:   ",
            "arxiv:2301.00001",
            "dataset:   ",
            "dataset:squad",
        ]
    )
    assert result.base_model_relation is None
    assert result.arxiv_ids == ["2301.00001"]
    assert result.info_dataset_ids == ["squad"]


# ---------------------------------------------------------------------------
# _populate_tokenizer_info
# ---------------------------------------------------------------------------


def test_populate_tokenizer_info_no_tokenizer_class() -> None:
    # tokenizer_config present but without "tokenizer_class" -> that key is
    # omitted, while model_max_length is still read independently.
    extra_data: dict[str, object] = {}
    _populate_tokenizer_info(extra_data, {"model_max_length": 512})
    assert "hf.tokenizer_class" not in extra_data
    assert extra_data["hf.tokenizer_max_length"] == 512
