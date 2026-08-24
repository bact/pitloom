# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for ``read_hdf5()`` against a real HDF5 fixture file
(``tests/fixtures/aimodels/hdf5/example-model.h5``). Requires h5py to be
installed and the fixture file to be present; both are skipped otherwise.

See also: test_hdf5_mocked.py (equivalent behaviour exercised against a
mocked ``h5py`` file) and test_hdf5_parsing.py (direct unit tests for the
lower-level ``_hdf5`` parsing helpers).
"""

# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.extract.ai_model import read_hdf5

_HDF5_DIR = Path(__file__).parent.parent / "fixtures" / "aimodels" / "hdf5"


@pytest.fixture(scope="module")
def fixture_hdf5() -> Any:
    pytest.importorskip("h5py")
    path = _HDF5_DIR / "example-model.h5"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return read_hdf5(path)


def test_hdf5_fixture_format(fixture_hdf5: Any) -> None:
    # Keras HDF5 fixture has keras_version attribute -> reclassified as KERAS.
    assert fixture_hdf5.format_info.model_format == AiModelFormat.KERAS


def test_hdf5_fixture_format_version(fixture_hdf5: Any) -> None:
    # keras_version "3.13.2" -> major 3 -> "v2" (Keras 3 legacy HDF5 mode).
    assert fixture_hdf5.format_info.format_version == "v2"


def test_hdf5_fixture_framework(fixture_hdf5: Any) -> None:
    assert fixture_hdf5.format_info.framework == "keras"


def test_hdf5_fixture_framework_version(fixture_hdf5: Any) -> None:
    assert fixture_hdf5.format_info.framework_version == "3.13.2"


def test_hdf5_fixture_version_is_none(fixture_hdf5: Any) -> None:
    # keras_version is the framework version, not the model version.
    assert fixture_hdf5.version is None


def test_hdf5_fixture_type_of_model(fixture_hdf5: Any) -> None:
    assert fixture_hdf5.type_of_model == "Sequential"


def test_hdf5_fixture_name(fixture_hdf5: Any) -> None:
    assert fixture_hdf5.name == "Binary_Classifier_v1"


def test_hdf5_fixture_input_shape(fixture_hdf5: Any) -> None:
    assert len(fixture_hdf5.inputs) == 1
    assert fixture_hdf5.inputs[0]["shape"] == [None, 10]


def test_hdf5_fixture_provenance_has_framework_version(fixture_hdf5: Any) -> None:
    assert "framework_version" in fixture_hdf5.provenance


def test_hdf5_fixture_provenance_has_name(fixture_hdf5: Any) -> None:
    assert "name" in fixture_hdf5.provenance
