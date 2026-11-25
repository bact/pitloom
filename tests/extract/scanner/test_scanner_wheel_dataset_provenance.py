# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model read from a wheel names its archive member, not the temporary
copy, in the provenance of its datasets too.

See also: :mod:`tests.extract.scanner.test_scanner_wheel` (the producer) and
:mod:`tests.extract.ai_model.test_gguf_datasets` (the dataset reader).
"""

# W0632 false positive: pylint infers the returned `models = []` as empty.
# pylint: disable=missing-function-docstring,unbalanced-tuple-unpacking

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.extract.scanner import _restore_source_name
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import write_model_wheel
from tests.extract.ai_model.gguf_builders import STRING, UINT32, gguf_file, kv, string

pytestmark = pytest.mark.platform

_MEMBER = "demo/real-model.gguf"


def _gguf() -> bytes:
    pairs = [
        kv(b"general.dataset.count", UINT32, struct.pack("<I", 1)),
        kv(b"general.dataset.0.name", STRING, string("Ultrachat_200K")),
        kv(b"general.dataset.0.repo_url", STRING, string("https://example.org/u")),
    ]
    return gguf_file(0, len(pairs), b"".join(pairs))


def test_a_wheel_gguf_names_its_member_in_the_dataset_provenance(
    tmp_path: Path, copies: list[Path]
) -> None:
    pytest.importorskip("gguf")
    wheel = write_model_wheel(tmp_path, {_MEMBER: _gguf()})
    (meta,) = scan_wheel_for_ai_models(
        wheel,
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**8,
        trust=True,
    )
    assert copies  # a copy under another name was read
    assert all(copy.name != "real-model.gguf" for copy in copies)
    source = "Source: real-model.gguf"
    (ref,) = meta.datasets
    assert ref.metadata.provenance == {
        "name": f"{source} | Field: general.dataset.0.name",
        "download_url": f"{source} | Field: general.dataset.0.repo_url",
    }
    assert meta.provenance["datasets"].startswith(source + " |")
    for copy in copies:
        provenance = [*meta.provenance.values(), *ref.metadata.provenance.values()]
        assert not any(copy.name in value for value in provenance)


def test_dataset_provenance_is_restored_by_exact_prefix_only() -> None:
    data = DatasetMetadata(
        name="d",
        provenance={
            "name": "Source: 0.gguf | Field: x",
            "version": "Source: 0.gguf2 | Field: x",
            "description": "unrelated",
        },
    )
    second = DatasetMetadata(name="e", provenance={"name": "Source: 0.gguf"})
    meta = AiModelMetadata(
        datasets=[
            DatasetReference(role="trainedOn", metadata=data),
            DatasetReference(role="testedOn", metadata=second),
        ]
    )
    _restore_source_name(meta, Path("0.gguf"), "real.gguf")
    assert data.provenance == {
        "name": "Source: real.gguf | Field: x",
        "version": "Source: 0.gguf2 | Field: x",
        "description": "unrelated",
    }
    # Every dataset, not only the first; a bare prefix with no segment too.
    assert second.provenance == {"name": "Source: real.gguf"}
