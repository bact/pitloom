# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""NumPy array file metadata extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pitloom.core.ai_metadata import AiModelFormat, AiModelMetadata


def read_numpy(model_path: Path) -> AiModelMetadata:
    """Extract metadata from a NumPy array file (``.npy`` or ``.npz``).

    Requires the ``numpy`` package (``pip install numpy``).

    For ``.npy`` files the array header is memory-mapped so that shape and
    dtype are read without loading the full tensor data.  For ``.npz``
    archives each constituent array is loaded to retrieve its shape and dtype;
    arrays are listed as :attr:`inputs <AiModelMetadata.inputs>` entries.

    Neither format embeds a model name, description, or training configuration,
    so :attr:`~AiModelMetadata.name`, :attr:`~AiModelMetadata.description`,
    and :attr:`~AiModelMetadata.version` are always ``None``.

    Args:
        model_path: Path to a ``.npy`` or ``.npz`` file.

    Returns:
        AiModelMetadata with shape/dtype information in
        :attr:`~AiModelMetadata.inputs`.

    Raises:
        ImportError: If ``numpy`` is not installed.
        ValueError: If the file cannot be read as a valid NumPy file.
    """
    try:
        import numpy as np  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "The 'numpy' package is required to extract NumPy model metadata. "
            "Install it with: pip install numpy"
        ) from exc

    source = f"Source: {model_path.name}"
    provenance: dict[str, str] = {}
    inputs: list[dict[str, Any]] = []

    suffix = model_path.suffix.lower()

    try:
        if suffix == ".npy":
            # mmap_mode='r' reads shape/dtype from the header without loading
            # the full tensor data into memory.
            arr = np.load(str(model_path), mmap_mode="r", allow_pickle=False)
            inputs = [{"shape": list(arr.shape), "dtype": str(arr.dtype)}]
            if inputs:
                provenance["inputs"] = f"{source} | Field: .npy header (shape, dtype)"
        elif suffix == ".npz":
            with np.load(str(model_path), allow_pickle=False) as npzfile:
                for array_name in npzfile.files:
                    arr = npzfile[array_name]
                    inputs.append(
                        {
                            "name": array_name,
                            "shape": list(arr.shape),
                            "dtype": str(arr.dtype),
                        }
                    )
            if inputs:
                provenance["inputs"] = f"{source} | Fields: array names, shapes, dtypes"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ValueError(f"Failed to read NumPy file {model_path}: {exc}") from exc

    return AiModelMetadata(
        format=AiModelFormat.NUMPY,
        type_of_model="numpy array",
        inputs=inputs,
        provenance=provenance,
    )
