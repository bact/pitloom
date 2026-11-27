# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Against the real Hugging Face Hub: a model id it knows no model for is
refused (``input-not-found/hub``), while a gated model and the page of a
model with a one-part id (``gpt2``, moved to ``openai-community/gpt2``) are
read. Asked without a token unless ``HF_TOKEN`` is set; none of these
answers depends on one.

See also: tests/extract/remote/test_hub_repository_not_found.py (the same
answers, mocked, on every surface).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pitloom.assemble import generate_model_sbom
from pitloom.extract.remote._hub_api import REPOSITORY_NOT_FOUND
from pitloom.extract.remote.errors import RemoteSourceError
from tests._network import require_reachable, skip_on_network_error

pytestmark = pytest.mark.network

#: An id no model has: its owner is not a Hub account.
_MISSING = "pitloom-no-such-owner-0/no-such-model"


@pytest.fixture(autouse=True)
def _hub_reachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    require_reachable("https://huggingface.co/api/models/openai-community/gpt2")


def test_a_missing_model_is_refused() -> None:
    with skip_on_network_error(), pytest.raises(RemoteSourceError) as raised:
        generate_model_sbom(_MISSING, output_path=Path("o.json"))
    assert raised.value.code == REPOSITORY_NOT_FOUND
    assert raised.value.pitloom_code == "input-not-found/hub"
    assert not Path("o.json").exists()


@pytest.mark.parametrize(
    ("target", "name"),
    [
        ("google/gemma-2b", "gemma-2b"),
        ("https://huggingface.co/gpt2/tree/main", "gpt2"),
    ],
    ids=["gated", "one-part-id-page"],
)
def test_a_model_the_hub_knows_is_read(target: str, name: str) -> None:
    with skip_on_network_error():
        sbom = json.loads(generate_model_sbom(target))
    names = {e.get("name") for e in sbom["@graph"] if e.get("type") == "ai_AIPackage"}
    assert names == {name}
