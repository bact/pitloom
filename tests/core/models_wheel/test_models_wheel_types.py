# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``warn_discovery_failed()`` (the shared per-backend
discovery-failure ``WARNING:``) and ``has_uv_build_backend_overrides()``.

``has_uv_build_backend_overrides()``: every malformed/
absent-nesting branch of its ``tool.uv.build-backend`` walk, plus the
tri-state (absent/empty/populated) distinction on the two file-filtering
keys themselves. See also:
tests/core/models_wheel/test_models_wheel_dispatch.py's
``test_get_wheel_files_uv_build_fallback_warns_about_wheel_exclude``/
``test_get_wheel_files_uv_build_fallback_no_hint_without_file_filter_keys``
for the end-to-end (parsed real pyproject.toml -> sharpened WARNING:)
behavior this function feeds into.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core._models_wheel_hatchling import discover as discover_hatchling
from pitloom.core._models_wheel_types import (
    has_uv_build_backend_overrides,
    warn_discovery_failed,
)
from pitloom.logging_config import configure_logging

_MULTI_LINE = "first line\n\n  second line\r\nthird"
_ONE_LINE = "first line second line third"


@pytest.mark.parametrize(
    ("module_name", "backend", "raiser"),
    [
        pytest.param("flit", "Flit", ("flit_core.config", "read_flit_config")),
        pytest.param(
            "hatchling", "Hatchling", ("hatchling.builders.wheel", "WheelBuilder")
        ),
        pytest.param("pdm", "PDM", ("pdm.backend.wheel", "WheelBuilder")),
        pytest.param("poetry", "Poetry", ("poetry.core.factory", "Factory")),
        pytest.param(
            "setuptools",
            "Setuptools",
            ("pitloom.core._models_wheel_setuptools", "_load_distribution"),
        ),
    ],
)
def test_backend_discovery_failure_logs_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    module_name: str,
    backend: str,
    raiser: tuple[str, str],
) -> None:
    """Every backend discoverer routes its blanket failure through the
    shared helper, which collapses a multi-line exception to one line."""
    module = importlib.import_module(f"pitloom.core._models_wheel_{module_name}")

    def fail(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError(_MULTI_LINE)

    monkeypatch.setattr(importlib.import_module(raiser[0]), raiser[1], fail)
    spy = mock.create_autospec(warn_discovery_failed, side_effect=warn_discovery_failed)
    monkeypatch.setattr(module, "warn_discovery_failed", spy)

    with caplog.at_level(logging.WARNING):
        assert module.discover(tmp_path) is None

    spy.assert_called_once()
    assert [r.getMessage() for r in caplog.records] == [
        f"{backend} file discovery failed for {tmp_path}: {_ONE_LINE}"
    ]


def test_real_hatchling_failure_is_one_tagged_stderr_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hatchling's own "no directory matches the project name" error is
    multi-line; the WARNING must still be one ``WARNING:`` line."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "nomatch"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    configure_logging(debug=False)

    assert discover_hatchling(tmp_path) is None

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("WARNING: Hatchling file discovery failed for ")
    assert "no directory that matches the name of your project" in lines[0]


@pytest.mark.parametrize(
    ("pyproject_data", "expected"),
    [
        pytest.param({}, False, id="no_tool_table"),
        pytest.param({"tool": "not-a-dict"}, False, id="tool_not_a_dict"),
        pytest.param({"tool": {}}, False, id="tool_present_no_uv"),
        pytest.param({"tool": {"uv": "not-a-dict"}}, False, id="uv_not_a_dict"),
        pytest.param({"tool": {"uv": {}}}, False, id="uv_present_no_build_backend"),
        pytest.param(
            {"tool": {"uv": {"build-backend": "not-a-dict"}}},
            False,
            id="build_backend_not_a_dict",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {}}}},
            False,
            id="build_backend_present_but_empty",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"module-root": ""}}}},
            False,
            id="only_non_filtering_key_present",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"module-name": "pkg._core"}}}},
            False,
            id="module_name_alone_is_not_a_filter",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-exclude": []}}}},
            False,
            id="wheel_exclude_present_but_empty_list",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-include": []}}}},
            False,
            id="wheel_include_present_but_empty_list",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-exclude": ["a/**"]}}}},
            True,
            id="wheel_exclude_populated",
        ),
        pytest.param(
            {"tool": {"uv": {"build-backend": {"wheel-include": ["a/**"]}}}},
            True,
            id="wheel_include_populated",
        ),
        pytest.param(
            {
                "tool": {
                    "uv": {
                        "build-backend": {
                            "module-root": "",
                            "wheel-exclude": ["a/**"],
                        }
                    }
                }
            },
            True,
            id="filter_key_alongside_non_filter_key",
        ),
        pytest.param(
            {
                "tool": {
                    "uv": {
                        "build-backend": {
                            "wheel-exclude": [],
                            "wheel-include": ["a/**"],
                        }
                    }
                }
            },
            True,
            id="one_empty_one_populated_still_true",
        ),
    ],
)
def test_has_uv_build_backend_overrides(
    pyproject_data: dict[str, object], expected: bool
) -> None:
    assert has_uv_build_backend_overrides(pyproject_data) is expected
