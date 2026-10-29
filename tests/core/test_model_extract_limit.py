# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared byte-ceiling validator and its argparse type."""

from __future__ import annotations

import argparse

import numpy as np
import pytest

from pitloom.cli.options import positive_byte_ceiling
from pitloom.core.model_extract_limit import (
    require_max_dataset_hash_bytes,
    require_max_model_extract_bytes,
    require_positive_ceiling,
)


@pytest.mark.parametrize("value", [1, 512, np.int64(7), np.uint8(3)], ids=repr)
def test_ceiling_accepts_any_index_integer_as_int(value: object) -> None:
    result = require_positive_ceiling(value, "k")
    assert result == value
    assert result.__class__ is int


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (True, "must be an integer, got bool"),
        (False, "must be an integer, got bool"),
        (1.5, "must be an integer, got float"),
        ("abc", "must be an integer, got str"),
        (None, "must be an integer, got NoneType"),
        (0, "must be a positive integer, got 0"),
        (-1, "must be a positive integer, got -1"),
        (np.int64(0), "must be a positive integer, got 0"),
    ],
    ids=repr,
)
@pytest.mark.parametrize(
    ("label", "prefix"), [("[t] 'k'", "[t] 'k' must be"), ("", "must be")]
)
def test_ceiling_rejects_and_labels(
    value: object, message: str, label: str, prefix: str
) -> None:
    with pytest.raises(ValueError, match=message) as exc:
        require_positive_ceiling(value, label)
    assert str(exc.value).startswith(prefix)


@pytest.mark.parametrize(
    ("require", "key"),
    [
        (require_max_model_extract_bytes, "max-model-extract-bytes"),
        (require_max_dataset_hash_bytes, "max-dataset-hash-bytes"),
    ],
    ids=["model", "dataset"],
)
def test_named_wrappers_label_table_and_key(require: object, key: str) -> None:
    assert require(np.int64(5)) == 5  # type: ignore[operator]
    with pytest.raises(ValueError, match=rf"^pc '{key}' must be") as exc:
        require(0, "pc")  # type: ignore[operator]
    assert "\n" not in str(exc.value)


@pytest.mark.parametrize("text", ["8", "1", "004"])
def test_argparse_type_accepts_plain_integers(text: str) -> None:
    assert positive_byte_ceiling(text) == int(text)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("0", "must be a positive integer, got 0"),
        ("-1", "must be a positive integer, got -1"),
        ("abc", "invalid int value: 'abc'"),
        ("1.5", "invalid int value: '1.5'"),
        ("4GiB", "invalid int value: '4GiB'"),
    ],
)
def test_argparse_type_rejects_with_unprefixed_message(text: str, message: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        positive_byte_ceiling(text)
    assert message in str(exc.value)
    assert not str(exc.value).startswith(" ")
