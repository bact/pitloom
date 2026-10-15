# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hugging Face model's originator and supplier (the repository owner) and
parameter count (``safetensors.total``, else ``gguf.total``): what is recorded, its
provenance, and the one ``WARNING:`` for a count the Hub sent in a shape
that cannot be one.

See also: :mod:`tests.extract.remote.test_huggingface_fetch` (the fetch of
both totals), :mod:`tests.core.test_model_parameters` (the rules).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
from typing import Any

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.core.model_originators import (
    ORIGINATORS_PROVENANCE_KEY,
    SUPPLIER_PROVENANCE_KEY,
)
from pitloom.core.model_parameters import (
    MAX_PARAMETER_COUNT,
    PARAMETER_COUNT_NOTE,
    PARAMETER_COUNT_PROVENANCE_KEY,
)
from pitloom.extract.remote.huggingface import read_huggingface
from pitloom.extract.remote.huggingface_field import (
    HubProducer,
    hub_producer_and_count,
)
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls
from tests.warning_helpers import logged_warnings

_URL = "https://huggingface.co/o/model"
_OWNER_PROVENANCE = (
    "Source: Hugging Face Hub | Field: model_info author | Method: repository_owner"
)
_COUNT_PROVENANCE = (
    "Source: Hugging Face Hub | Field: model_info {} | Method: tensor_element_sum"
)
_ST_COUNT = _COUNT_PROVENANCE.format("safetensors.total")
_SKIPPED = "parameter count not recorded"


def _read(**hub_info: Any) -> Any:
    with _patch_hf_calls(hub_info=hub_info):
        return read_huggingface("o/model")


@pytest.mark.parametrize(
    ("author", "expected"),
    [("o", ["o"]), ("Org, Inc.", ["Org, Inc."]), ("  \t ", []), (None, [])],
    ids=["name", "comma-not-split", "blank", "absent"],
)
def test_the_author_is_the_one_originator_and_the_supplier(
    author: str | None, expected: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    # `_load_model_info` keeps a non-empty author only; hand the helper
    # whatever the Hub dict holds, whitespace included.
    provenance: dict[str, str] = {}
    hub_info = {"sha": "x"} if author is None else {"author": author}
    producer = hub_producer_and_count(hub_info, provenance, _URL)

    supplier = expected[0] if expected else None
    assert producer == HubProducer(expected, supplier, None)
    assert provenance == (
        {
            ORIGINATORS_PROVENANCE_KEY: _OWNER_PROVENANCE,
            SUPPLIER_PROVENANCE_KEY: _OWNER_PROVENANCE,
        }
        if expected
        else {}
    )
    assert not logged_warnings(caplog)


def test_the_originator_and_supplier_reach_the_model_metadata() -> None:
    meta = _read(author=" o ", sha="x")

    assert (meta.originators, meta.supplier) == (["o"], "o")
    assert meta.provenance[ORIGINATORS_PROVENANCE_KEY] == _OWNER_PROVENANCE
    assert meta.provenance[SUPPLIER_PROVENANCE_KEY] == _OWNER_PROVENANCE
    assert meta.extra_data["hf.author"] == " o "  # as read, unchanged
    no_author = _read(sha="x")
    assert ORIGINATORS_PROVENANCE_KEY not in no_author.provenance
    assert SUPPLIER_PROVENANCE_KEY not in no_author.provenance
    assert (no_author.originators, no_author.supplier) == ([], None)


@pytest.mark.parametrize(
    ("totals", "count", "field"),
    [
        ({"safetensors_total": 7}, 7, "safetensors.total"),
        ({"gguf_total": 9}, 9, "gguf.total"),  # a GGUF-only repository
        ({"safetensors_total": 7, "gguf_total": 9}, 7, "safetensors.total"),
        # A stated Safetensors zero is no count, not a reason to try GGUF
        ({"safetensors_total": 0, "gguf_total": 9}, None, None),
    ],
    ids=["safetensors", "gguf", "both", "safetensors-zero"],
)
def test_a_stated_count_is_recorded_with_its_source(
    totals: dict[str, Any],
    count: int | None,
    field: str | None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    meta = _read(sha="x", **totals)

    assert meta.parameter_count == count
    assert meta.provenance.get(PARAMETER_COUNT_PROVENANCE_KEY) == (
        field and _COUNT_PROVENANCE.format(field)
    )
    assert "extra_data" in meta.provenance  # the rest of the provenance stays
    assert not logged_warnings(caplog)


@pytest.mark.parametrize("total", [0, None, "absent"], ids=["zero", "none", "absent"])
def test_no_stated_count_is_quiet(total: Any, caplog: pytest.LogCaptureFixture) -> None:
    hub_info = (
        {"sha": "x"} if total == "absent" else {"sha": "x", "safetensors_total": total}
    )
    meta = _read(**hub_info)

    assert meta.parameter_count is None
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    assert not logged_warnings(caplog)


@pytest.mark.parametrize(
    ("total", "reason"),
    [
        (True, "not a non-negative integer"),
        ("7", "not a non-negative integer"),
        (-1, "not a non-negative integer"),
        (1.5, "not a non-negative integer"),
        (
            MAX_PARAMETER_COUNT + 1,
            f"larger than the {MAX_PARAMETER_COUNT}-element parameter-count cap",
        ),
    ],
    ids=["bool", "str", "negative", "float", "over-cap"],
)
@pytest.mark.parametrize("key", ["safetensors_total", "gguf_total"])
def test_a_rejected_count_warns_once_and_records_nothing(
    total: Any, reason: str, key: str, caplog: pytest.LogCaptureFixture
) -> None:
    meta = _read(author="o", sha="x", **{key: total})

    assert meta.parameter_count is None
    assert PARAMETER_COUNT_PROVENANCE_KEY not in meta.provenance
    # The owner is not lost with it
    assert (meta.originators, meta.supplier) == (["o"], "o")
    (message,) = logged_warnings(caplog)
    assert message.startswith(f"FORMAT=huggingface FILE={_URL}: ")
    assert reason in message
    assert message.endswith(f"; {_SKIPPED}")


def test_the_owner_and_count_reach_the_sbom() -> None:
    # Depends on the model assembler writing `originatedBy`, `suppliedBy`
    # and the count.
    # The default provenance detail is `minimal`: the Hub is a transparent
    # source, so only an entry with a Method is shown.
    with _patch_hf_calls(hub_info={"author": "o", "sha": "x", "safetensors_total": 7}):
        graph = json.loads(generate_model_sbom("o/model"))["@graph"]

    (package,) = [e for e in graph if e["type"] == "ai_AIPackage"]
    (agent,) = [e for e in graph if e["type"] == "Agent"]
    assert agent["name"] == "o"
    # The owner is one element, the originator and the supplier
    assert package["originatedBy"] == [agent["spdxId"]]
    assert package["suppliedBy"] == agent["spdxId"]
    assert {h["key"]: h["value"] for h in package["ai_hyperparameter"]}[
        "parameters"
    ] == "7"
    # All three entries survive `minimal`: each carries a Method.
    lines = package["comment"].split("\n")
    assert lines[0] == PARAMETER_COUNT_NOTE
    assert f"{PARAMETER_COUNT_PROVENANCE_KEY}: {_ST_COUNT}" in lines[1]
    assert f"{ORIGINATORS_PROVENANCE_KEY}: {_OWNER_PROVENANCE}" in lines[1]
    assert f"{SUPPLIER_PROVENANCE_KEY}: {_OWNER_PROVENANCE}" in lines[1]
