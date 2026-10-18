# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A model's and a dataset's ``software_packageUrl``.

A Hub model gets ``pkg:huggingface/<owner>/<name>[@<commit>]``; a model file
``pkg:generic/<file>?checksum=sha256:<digest>``; a dataset with an http(s)
download URL ``pkg:generic/<name>?download_url=<url>``. Nothing else gets
one: a source without the data leaves the property out.

See also: tests/core/test_purl.py (the builders),
tests/assemble/test_ai_package_verified_using.py (the digest).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import (
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.assemble.spdx3.document import build_model
from pitloom.core.ai_metadata import AiModelFormat, AiModelFormatInfo, AiModelMetadata
from pitloom.core.dataset_metadata import DatasetMetadata, DatasetReference
from pitloom.core.file_hash import HexDigests
from tests._author_routes import CREATED
from tests._wheel_models import safetensors_bytes, write_model_wheel
from tests.extract.remote.hf_patches._hf_patches_base import _patch_hf_calls

_MODEL = "m.safetensors"
_DATA = safetensors_bytes()
_SHA = hashlib.sha256(_DATA).hexdigest()
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_PYPROJECT = (
    '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'
    '[project]\nname = "demo"\nversion = "1.0.0"\nrequires-python = ">=3.10"\n'
)


def _purls(sbom: str, type_name: str) -> list[str | None]:
    graph = json.loads(sbom)["@graph"]
    return [e.get("software_packageUrl") for e in graph if e["type"] == type_name]


def _project(tmp: Path) -> str:
    root = tmp / "proj"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_bytes(b"x = 1\n")
    (root / "demo" / _MODEL).write_bytes(_DATA)
    (root / "pyproject.toml").write_bytes(_PYPROJECT.encode())
    return generate_project_sbom(root, creation_metadata=None, offline=True)


def _wheel(tmp: Path) -> str:
    wheel = write_model_wheel(tmp / "dist", {f"demo/{_MODEL}": _DATA})
    return generate_wheel_sbom(wheel, offline=True)


def _model(tmp: Path) -> str:
    path = tmp / _MODEL
    path.write_bytes(_DATA)
    return generate_model_sbom(path)


@pytest.mark.parametrize("route", [_project, _wheel, _model])
def test_model_file_purl_is_the_same_on_every_route(
    tmp_path: Path, route: Callable[[Path], str]
) -> None:
    expected = f"pkg:generic/{_MODEL}?checksum=sha256:{_SHA}"
    assert _purls(route(tmp_path), "ai_AIPackage") == [expected]


def _hub(hub_info: dict[str, Any], model_id: str = "acme/model") -> str:
    with _patch_hf_calls(hub_info=hub_info):
        return generate_model_sbom(model_id, creation_metadata=CREATED)


@pytest.mark.parametrize(
    ("hub_info", "model_id", "expected"),
    [
        ({"author": "acme", "sha": _COMMIT}, "acme/model",
         f"pkg:huggingface/acme/model@{_COMMIT}"),
        ({"author": "acme", "sha": _COMMIT.upper()}, "acme/model",
         f"pkg:huggingface/acme/model@{_COMMIT}"),
        # No commit known, or not a commit hash: the repository alone.
        ({"author": "acme"}, "acme/model", "pkg:huggingface/acme/model"),
        ({"author": "acme", "sha": "deadbeef"}, "acme/model",
         "pkg:huggingface/acme/model"),
    ],
    ids=["commit", "upper-commit", "no-commit", "short-commit"],
)  # fmt: skip
def test_hub_model_purl(
    hub_info: dict[str, Any], model_id: str, expected: str | None
) -> None:
    assert _purls(_hub(hub_info, model_id), "ai_AIPackage") == [expected]


def _model_with_dataset(download_url: str | None, version: str | None = None) -> str:
    dataset = DatasetMetadata(name="corpus", version=version, download_url=download_url)
    model = AiModelMetadata(
        name="m",
        datasets=[DatasetReference(role="trainedOn", metadata=dataset)],
        format_info=AiModelFormatInfo(
            file_name=None, model_format=AiModelFormat.UNKNOWN
        ),
    )
    return build_model(model, CREATED).to_json()


@pytest.mark.parametrize(
    ("download_url", "version", "expected"),
    [
        ("https://e.org/c.tar", None,
         "pkg:generic/corpus?download_url=https://e.org/c.tar"),
        ("http://e.org/c.tar", "2",
         "pkg:generic/corpus@2?download_url=http://e.org/c.tar"),
        # A local path or another scheme names no place a reader can fetch.
        ("data/train.txt", None, None),
        ("ftp://e.org/c.tar", None, None),
        (None, None, None),
    ],
    ids=["https", "http-version", "local-path", "ftp", "none"],
)  # fmt: skip
def test_dataset_purl(
    download_url: str | None, version: str | None, expected: str | None
) -> None:
    sbom = _model_with_dataset(download_url, version)
    assert _purls(sbom, "dataset_DatasetPackage") == [expected]


def test_model_without_a_file_or_hub_id_has_no_purl() -> None:
    model = AiModelMetadata(name="m")
    sbom = build_model(
        model, CREATED, digest=HexDigests("ab" * 32, "cd" * 64)
    ).to_json()
    assert _purls(sbom, "ai_AIPackage") == [None]


def test_model_file_without_a_digest_has_no_purl() -> None:
    model = AiModelMetadata(
        name="m",
        format_info=AiModelFormatInfo(
            file_name="m.gguf", model_format=AiModelFormat.GGUF
        ),
    )
    assert _purls(build_model(model, CREATED).to_json(), "ai_AIPackage") == [None]
