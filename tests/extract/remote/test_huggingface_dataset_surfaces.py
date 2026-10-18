# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Hub dataset's licence and metadata reach the SBOM of its model on each
surface that reads a Hugging Face model (the library, ``loom model`` and
``loom generate``; the build hook reads no Hub model), never when the model
is not looked up, and in the same bytes on every run.

See also: tests/extract/remote/test_huggingface_dataset.py (the reader).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from pitloom import __main__
from pitloom.assemble import generate_model_sbom
from pitloom.core.provenance import ProvenanceConfig
from pitloom.extract.remote import huggingface_dataset as hub_dataset
from tests._author_routes import CREATED
from tests._license_graph import license_elements, license_targets
from tests.conformance.g7ai_shared import without_licence_database
from tests.conformance.g7ai_surfaces import MODEL_SURFACES
from tests.extract.remote.hf_patches._hf_patches_base import (
    HubDataset,
    _make_card_data,
    _patch_hf_calls,
)

_SHA = "89abcdef0123456789abcdef0123456789abcdef"
_LINK = "https://example.org/licence"
#: Three datasets: an SPDX licence, ``other`` with a link, and none.
_HUB: dict[str, HubDataset] = {
    "o/d": {
        "info": {"author": "acme", "sha": _SHA},
        "card_text": "---\nlicense: ODC-By-1.0\n---\n\nA corpus.\n",
        "card_data": {"license": "ODC-By-1.0", "tags": ["web"]},
    },
    "o/e": {"card_data": {"license": "other", "license_link": _LINK}},
    "o/f": {},
}


@contextmanager
def _hub() -> Generator[None, None, None]:
    card = _make_card_data(license="apache-2.0", datasets=list(_HUB))
    with without_licence_database(), _patch_hf_calls(card_data=card, datasets=_HUB):
        yield


def _datasets(sbom: str) -> dict[str, dict[str, Any]]:
    """Each dataset package of *sbom* by name: the values a surface must not
    change, and the licence it declares."""
    graph = json.loads(sbom)["@graph"]
    out: dict[str, dict[str, Any]] = {}
    for element in graph:
        if element["type"] != "dataset_DatasetPackage":
            continue
        own = [
            r
            for r in graph
            if r.get("relationshipType") == "hasDeclaredLicense"
            and r["from"] == element["spdxId"]
        ]
        out[element["name"]] = {
            "version": element.get("software_packageVersion"),
            "description": element.get("description"),
            "licence": license_targets([*own, *license_elements(graph)]),
        }
    return out


_EXPECTED = {
    "o/d": {"version": _SHA, "description": "A corpus.", "licence": ["ODC-By-1.0"]},
    "o/e": {"version": None, "description": None, "licence": [_LINK]},
    "o/f": {"version": None, "description": None, "licence": []},
}


@pytest.mark.parametrize("surface", list(MODEL_SURFACES))
def test_each_surface_writes_the_dataset_metadata(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # "acme/model" must not name a local path
    with _hub():
        # A Hub id, not a path: a Path would turn the slash round on Windows.
        source = cast(Path, "acme/model")
        sbom = MODEL_SURFACES[surface](source, tmp_path, monkeypatch)
    assert _datasets(sbom) == _EXPECTED


def test_the_provenance_names_the_card_fields_and_no_keywords() -> None:
    full = ProvenanceConfig(format="comment", detail="full")
    with _hub():
        sbom = generate_model_sbom(
            "acme/model", creation_metadata=CREATED, provenance=full
        )
    comments = [
        str(e.get("comment"))
        for e in json.loads(sbom)["@graph"]
        if e["type"] == "dataset_DatasetPackage"
    ]
    joined = "\n".join(comments)
    assert "license: Source: Hugging Face Hub | Field: dataset card license" in joined
    assert "Field: dataset card license, license_link" in joined
    assert "creator: Source: Hugging Face Hub | Field: dataset_info author" in joined
    assert "keywords" not in joined  # no SPDX 3.0.1 property holds them


def test_two_runs_give_the_same_bytes() -> None:
    runs = []
    for _ in range(2):
        with _hub():
            runs.append(generate_model_sbom("acme/model", creation_metadata=CREATED))
    assert "ODC-By-1.0" in runs[0]
    assert runs[0] == runs[1]


@pytest.mark.parametrize("surface", ["library", "cli-model"])
def test_no_dataset_is_requested_when_the_model_is_not_looked_up(
    surface: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    info, download = MagicMock(), MagicMock()
    monkeypatch.chdir(tmp_path)
    seam_info, seam_card = MagicMock(), MagicMock()
    with (
        _hub(),
        patch.object(hub_dataset, "_load_dataset_info", seam_info),
        patch.object(hub_dataset, "_load_dataset_card", seam_card),
        patch("huggingface_hub.dataset_info", info),
        patch("huggingface_hub.hf_hub_download", download),
    ):
        if surface == "library":
            with pytest.raises(ValueError, match="Offline mode"):
                generate_model_sbom("acme/model", offline=True)
        else:
            monkeypatch.setattr(
                sys, "argv", ["loom", "model", "acme/model", "--offline"]
            )
            assert __main__.main() == 1
    assert not any(m.called for m in (seam_info, seam_card, info, download))
