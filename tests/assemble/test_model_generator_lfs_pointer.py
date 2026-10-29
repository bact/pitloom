# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The local model gate refuses a Git LFS pointer before any hash is taken,
so a pointer is neither an ``ai_AIPackage`` nor hashed for a registry lookup.

See also: tests/assemble/test_model_outcome_parity.py (the same refusal with
a non-pointer header); tests/id_registry/test_registry_lfs_pointer.py.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import _model_generator, enrich_model, generate_model_sbom
from pitloom.id_registry import IdRegistry
from tests._lfs import lfs_pointer_bytes


@pytest.mark.parametrize("api", [generate_model_sbom, enrich_model])
@pytest.mark.parametrize("suffix", [".gguf", ".safetensors", ".bin", ".onnx"])
def test_a_pointer_is_refused_and_never_hashed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api: Callable[..., str],
    suffix: str,
) -> None:
    path = tmp_path / f"model{suffix}"
    path.write_bytes(lfs_pointer_bytes(b"weights"))
    registry = tmp_path / "ids.json"
    IdRegistry.new("m").save(registry)

    def hashed(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("hashed a refused pointer")

    for reader in ("file_digests", "sha256_digest"):
        monkeypatch.setattr(_model_generator, reader, hashed)
    with pytest.raises(ValueError, match="Git LFS"):
        api(path, id_registry=registry)


@pytest.mark.parametrize(("content", "said"), [(b"x", "1 byte"), (b"xy", "2 bytes")])
def test_the_refusal_states_the_size_in_the_singular_for_one(
    tmp_path: Path, content: bytes, said: str
) -> None:
    path = tmp_path / "model.gguf"
    path.write_bytes(lfs_pointer_bytes(content))
    with pytest.raises(ValueError, match=rf"size {said}\)"):
        generate_model_sbom(path)


def test_a_pointer_that_cannot_be_read_again_keeps_the_plain_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is said before the pointer is re-read for its ``oid``; a
    read that then fails still refuses, without the ``oid`` and size."""
    path = tmp_path / "model.gguf"
    path.write_bytes(lfs_pointer_bytes(b"weights"))

    def unreadable(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(_model_generator, "read_lfs_pointer", unreadable)
    with pytest.raises(ValueError, match="header is a Git LFS pointer") as caught:
        generate_model_sbom(path)
    assert "content not pulled" not in str(caught.value)
