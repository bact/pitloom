# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Over the entry cap, the Safetensors entries kept are the same in every
process: ``safetensors`` returns ``__metadata__`` in no fixed order.

See also: :mod:`tests.extract.ai_model.test_safetensors`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pitloom.extract.ai_model.limits import MAX_MODEL_ENTRIES
from pitloom.extract.ai_model.safetensors import read_safetensors
from tests._wheel_models import safetensors_bytes

_KEPT_KEYS = """
import json, sys
from pathlib import Path
from pitloom.extract.ai_model.limits import cap_entries
from pitloom.extract.ai_model.safetensors import read_safetensors
meta = read_safetensors(Path(sys.argv[1]))
raw_before = list(meta.raw_metadata)
cut = cap_entries(meta)
print(json.dumps([raw_before, cut, list(meta.properties), list(meta.raw_metadata)]))
"""


def test_the_entries_kept_over_the_cap_are_the_same_in_every_process(
    tmp_path: Path,
) -> None:
    """Regression: ``safetensors`` returns ``__metadata__`` in an order that
    changes per process, and the cap kept "the first" of it, so one file gave
    different SBOMs run to run."""
    pytest.importorskip("safetensors")
    keys = [f"key.{i:04d}" for i in range(MAX_MODEL_ENTRIES + 500)]
    model_file = tmp_path / "m.safetensors"
    model_file.write_bytes(safetensors_bytes(metadata=dict.fromkeys(keys, "v")))
    runs = []
    for seed in ("1", "2", "3"):
        done = subprocess.run(  # noqa: S603
            [sys.executable, "-c", textwrap.dedent(_KEPT_KEYS), str(model_file)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert done.returncode == 0, done.stderr
        runs.append(json.loads(done.stdout))
    kept = sorted(keys)[:MAX_MODEL_ENTRIES]
    # One past the cap leaves the reader, so that the cap sees and reports it.
    assert all(run[0] == sorted(keys)[: MAX_MODEL_ENTRIES + 1] for run in runs)
    assert all(run[1:] == [["properties", "raw_metadata"], kept, kept] for run in runs)


@pytest.mark.parametrize("extra", [0, 2])
def test_a_map_is_cut_to_its_smallest_keys_only_over_the_cap(
    tmp_path: Path, extra: int
) -> None:
    """In-process, so that coverage sees it (the subprocess test does not)."""
    pytest.importorskip("safetensors")
    keys = [f"k{i:04d}" for i in range(MAX_MODEL_ENTRIES + extra)]
    model_file = tmp_path / "m.safetensors"
    model_file.write_bytes(safetensors_bytes(metadata=dict.fromkeys(keys[::-1], "v")))
    kept = read_safetensors(model_file).raw_metadata
    assert set(kept) == set(keys[: MAX_MODEL_ENTRIES + 1])  # one past the cap
    assert extra == 0 or list(kept) == keys[: MAX_MODEL_ENTRIES + 1]


def test_well_known_keys_sorting_after_the_cap_are_still_read(tmp_path: Path) -> None:
    """Regression: the cut to the smallest keys came before the lookup of
    ``modelspec.title`` and the like, so a model with many ``a...`` keys lost
    its name, version, architecture, precision and framework."""
    pytest.importorskip("safetensors")
    well_known = {
        "modelspec.title": "RealName",
        "modelspec.description": "Some text",
        "modelspec.version": "2.0",
        "modelspec.architecture": "llama",
        "modelspec.precision": "fp16",
        "format": "pt",
    }
    filler = {f"a{i:04d}": "v" for i in range(MAX_MODEL_ENTRIES + 500)}
    model_file = tmp_path / "m.safetensors"
    model_file.write_bytes(safetensors_bytes(metadata={**filler, **well_known}))
    meta = read_safetensors(model_file)
    assert len(meta.raw_metadata) == MAX_MODEL_ENTRIES + 1
    assert well_known.keys().isdisjoint(meta.raw_metadata)  # cut, as before
    assert (
        meta.name,
        meta.description,
        meta.version,
        meta.architecture,
        meta.quantization,
        meta.format_info.framework,
    ) == ("RealName", "Some text", "2.0", "llama", "fp16", "pt")
    for field in ("name", "description", "version", "architecture", "quantization"):
        assert meta.provenance[field].endswith("Field: __metadata__")
