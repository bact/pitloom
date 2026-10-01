# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A ``.pth`` Python path-configuration file is not a PyTorch model, on the
project and the wheel producer alike; a real ``.pt``/``.pth`` still is.

See also: :mod:`tests.extract.ai_model.test_ai_model_header` (the detector).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.core.ai_metadata import AiModelFormat
from pitloom.core.project import ProjectFile
from pitloom.extract.scanner import discover_ai_models
from pitloom.extract.scanner_project import project_candidates
from pitloom.extract.scanner_wheel import scan_wheel_for_ai_models
from tests._wheel_models import write_model_wheel

_FIXTURES = Path(__file__).parents[2] / "fixtures" / "aimodels" / "pytorch"
_PATH_CONFIG = {
    "distutils-precedence.pth": (
        b"import os; var = 'SETUPTOOLS_USE_DISTUTILS'; "
        b"enabled = os.environ.get(var, 'local') == 'local'; "
        b"enabled and __import__('_distutils_hack').add_shim(); \n"
    ),
    "a1_coverage.pth": b"import coverage; coverage.process_startup()\n",
    "demo-nspkg.pth": b"import sys, types, os;has_mfs = sys.version_info > (3, 5)\n",
    "empty.pth": b"",
    "paths.pth": b"/opt/lib\n",
}


@pytest.mark.parametrize("name", _PATH_CONFIG)
def test_a_path_config_file_is_not_a_model_in_a_project(
    name: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / name).write_bytes(_PATH_CONFIG[name])
    files = [ProjectFile(physical_path=name, distribution_path=name)]
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        assert not discover_ai_models(project_candidates(tmp_path, files))
    assert not [r for r in caplog.records if r.levelno >= logging.INFO]


def test_path_config_files_are_not_models_in_a_wheel(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No ``AIPackage``, no gate ``INFO`` urging ``--trust-wheel-model``, no
    usage hint."""
    wheel = write_model_wheel(tmp_path / "d", dict(_PATH_CONFIG))
    asked: list[bool] = []

    def hint() -> bool:
        asked.append(True)
        return True

    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        models = scan_wheel_for_ai_models(
            wheel,
            scan_usage=False,
            usage_hint=hint,
            max_bytes=10**7,
        )
    assert not models
    assert not asked
    assert not [r for r in caplog.records if r.levelno >= logging.INFO]


@pytest.mark.parametrize("name", ["example-model.pt", "example-model.pth"])
def test_a_real_pytorch_file_is_still_a_model_on_both_producers(
    name: str, tmp_path: Path
) -> None:
    data = (_FIXTURES / name).read_bytes()
    (tmp_path / name).write_bytes(data)
    files = [ProjectFile(physical_path=name, distribution_path=name)]
    (in_project,) = discover_ai_models(project_candidates(tmp_path, files))
    (in_wheel,) = scan_wheel_for_ai_models(
        write_model_wheel(tmp_path / "d", {name: data}),
        scan_usage=False,
        usage_hint=lambda: False,
        max_bytes=10**7,
    )
    assert in_project.format_info.model_format == AiModelFormat.PYTORCH
    assert in_wheel.format_info.model_format == AiModelFormat.PYTORCH
