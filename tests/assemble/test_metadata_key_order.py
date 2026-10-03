# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model file's own metadata key order does not change the output bytes.

Two files carrying the same metadata in a different order (a Safetensors
header, a GGUF key-value table, a Keras config) are the same input. Keys are
sorted where they reach the output: per-key provenance
(:func:`pitloom.extract._extract_utils.record_dict_field_provenance`) and
``ai_hyperparameter`` (``_populate_ai_pkg_hyperparameters``, and the
``pitloom.loom`` run).

See also: :mod:`tests.test_sbom_io` and :mod:`tests.assemble.test_built_time`
(the other canonical-output checks).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from spdx_python_model.bindings import v3_0_1 as spdx3

from pitloom import loom
from pitloom.assemble import generate_model_sbom
from pitloom.assemble.spdx3._ai_package import _populate_ai_pkg_hyperparameters
from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.creation import CreationMetadata
from pitloom.extract._extract_utils import record_dict_field_provenance
from tests._wheel_models import safetensors_bytes

_METADATA = {
    "modelspec.title": "demo",
    "zeta": "1",
    "alpha": "2",
    "mid": "3",
}
_HYPERPARAMETERS = {"lr": "0.1", "epoch": "5", "dim": "100"}


def _reversed(data: dict[str, str]) -> dict[str, str]:
    return dict(reversed(list(data.items())))


def _safetensors_sbom(tmp_path: Path, metadata: dict[str, str]) -> str:
    model = tmp_path / "model.safetensors"
    model.write_bytes(safetensors_bytes())
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    ctx.metadata.return_value = metadata
    ctx.keys.return_value = ["w"]
    module = MagicMock()
    module.safe_open.return_value = ctx
    with patch.dict("sys.modules", {"safetensors": module}):
        return generate_model_sbom(
            model,
            creation_metadata=CreationMetadata(
                creation_datetime="2026-01-01T00:00:00Z"
            ),
            id_registry=None,
        )


def test_safetensors_metadata_order_does_not_change_the_bytes(
    tmp_path: Path,
) -> None:
    permuted = _reversed(_METADATA)
    assert list(permuted) != list(_METADATA)  # the input really differs
    first = _safetensors_sbom(tmp_path, _METADATA)
    assert "__metadata__.zeta" in first  # the keys reach the output
    assert first == _safetensors_sbom(tmp_path, permuted)


def test_dict_field_provenance_is_recorded_in_key_order() -> None:
    provenance: dict[str, str] = {}
    record_dict_field_provenance(provenance, "properties", ["b", "c", "a"], "S")
    assert list(provenance) == ["properties.a", "properties.b", "properties.c"]


def _hyperparameter_keys(entries: Any) -> list[str]:
    return [entry.key for entry in entries]


def test_model_hyperparameters_are_emitted_in_key_order() -> None:
    """Quantization stays first; the format's own keys follow sorted."""
    ai_pkg = spdx3.ai_AIPackage(spdxId="urn:x:1", name="m")
    _populate_ai_pkg_hyperparameters(
        ai_pkg,
        AiModelMetadata(quantization="q8", hyperparameters=dict(_HYPERPARAMETERS)),
    )
    assert _hyperparameter_keys(ai_pkg.ai_hyperparameter) == [
        "quantization",
        "dim",
        "epoch",
        "lr",
    ]


def _loom_hyperparameters(path: Path, *, at_set_model: bool) -> list[str]:
    with loom.run(path) as run:
        if at_set_model:
            run.set_model("m", hyperparameters=dict(_HYPERPARAMETERS))
        else:
            run.set_model("m")
            run.set_model_hyperparameters(dict(_HYPERPARAMETERS))
    graph = json.loads(path.read_text(encoding="utf-8"))["@graph"]
    (model,) = [o for o in graph if o["type"] == "ai_AIPackage"]
    return [entry["key"] for entry in model["ai_hyperparameter"]]


def test_loom_hyperparameters_are_emitted_in_key_order(tmp_path: Path) -> None:
    assert list(_HYPERPARAMETERS) != sorted(_HYPERPARAMETERS)  # not vacuous
    for at_set_model in (True, False):
        path = tmp_path / f"run-{at_set_model}.json"
        keys = _loom_hyperparameters(path, at_set_model=at_set_model)
        assert keys == ["dim", "epoch", "lr"]
