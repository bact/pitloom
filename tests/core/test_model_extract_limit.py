# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared byte-ceiling validator and its argparse type."""

from __future__ import annotations

import argparse
from collections.abc import Callable

import numpy as np
import pytest

from pitloom.cli.options import positive_byte_ceiling
from pitloom.core.model_extract_limit import (
    require_max_dataset_hash_bytes,
    require_max_download_bytes,
    require_max_model_extract_bytes,
    require_positive_ceiling,
)
from pitloom.messages import code_of
from pitloom.messages.config import ConfigPlace, Parameter
from tests.argument_errors import integer_refusal

_FILE = ConfigPlace("tool.pitloom").at("k")
_PARAM = Parameter("pc")


@pytest.mark.parametrize("value", [1, 512, np.int64(7), np.uint8(3)], ids=repr)
@pytest.mark.parametrize("where", [_FILE, _PARAM], ids=["file", "parameter"])
def test_ceiling_accepts_any_index_integer_as_int(
    value: object, where: ConfigPlace | Parameter
) -> None:
    result = require_positive_ceiling(value, where)
    assert result == value
    assert result.__class__ is int


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (True, "must be an integer, got a boolean true"),
        (False, "must be an integer, got a boolean false"),
        (1.5, "must be an integer, got a float 1.5"),
        ("abc", "must be an integer, got a string 'abc'"),
        (None, "must be an integer, got None"),
        (0, "must be an integer of at least 1, got an integer 0"),
        (-1, "must be an integer of at least 1, got an integer -1"),
        (np.int64(0), "must be an integer of at least 1, got an integer 0"),
    ],
    ids=repr,
)
@pytest.mark.parametrize(
    ("where", "prefix", "code"),
    [
        (_FILE, "[tool.pitloom] k: must be", "config-invalid"),
        (_PARAM, "pc: must be", "option-invalid"),
    ],
    ids=["file", "parameter"],
)
def test_ceiling_rejects_and_names_its_stage(
    value: object,
    message: str,
    where: ConfigPlace | Parameter,
    prefix: str,
    code: str,
) -> None:
    """The stage is the type of *where*: a file setting is ``config-invalid``,
    a library parameter ``option-invalid`` (never picked from the text), a
    ``TypeError`` for a value that is no integer."""
    error = ValueError if code == "config-invalid" else integer_refusal(value)
    with pytest.raises(error, match=message) as exc:
        require_positive_ceiling(value, where)
    assert str(exc.value).startswith(prefix)
    assert code_of(exc.value) == code


@pytest.mark.parametrize(
    ("require", "key"),
    [
        (require_max_model_extract_bytes, "max-model-extract-bytes"),
        (require_max_dataset_hash_bytes, "max-dataset-hash-bytes"),
        (require_max_download_bytes, "max-download-bytes"),
    ],
    ids=["model", "dataset", "download"],
)
def test_named_wrappers_default_to_their_config_key(
    require: Callable[..., int], key: str
) -> None:
    assert require(np.int64(5)) == 5
    with pytest.raises(ValueError, match=rf"^\[tool\.pitloom\] {key}: must be") as exc:
        require(0)
    assert code_of(exc.value) == "config-invalid"
    assert "\n" not in str(exc.value)
    with pytest.raises(ValueError, match="^pc: must be") as lib:
        require(0, _PARAM)
    assert code_of(lib.value) == "option-invalid"


@pytest.mark.parametrize("text", ["8", "1", "004"])
def test_argparse_type_accepts_plain_integers(text: str) -> None:
    assert positive_byte_ceiling(text) == int(text)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("0", "must be an integer of at least 1, got an integer 0"),
        ("-1", "must be an integer of at least 1, got an integer -1"),
        ("abc", "must be an integer, got a string 'abc'"),
        ("1.5", "must be an integer, got a string '1.5'"),
        ("4GiB", "must be an integer, got a string '4GiB'"),
    ],
)
def test_argparse_type_rejects_with_unprefixed_message(text: str, message: str) -> None:
    """The flag stage: argparse prefixes ``argument --x:`` and the logging
    handler adds ``[option-invalid]``; the type's own text is bare."""
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        positive_byte_ceiling(text)
    assert str(exc.value) == message
