# ruff: noqa: F403, F405
from __future__ import annotations

import re
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from pitloom.core.config import PitloomConfig
from pitloom.plugins.hatch import (  # noqa: E402
    _HATCHLING_ERROR_PREFIX,
    _check_hatchling_sbom_support,
    _resolve_build_datetime,
)


def test_check_hatchling_sbom_support_passes_for_current_hatchling() -> None:
    """The Hatchling installed in the test environment must satisfy the gate."""
    _check_hatchling_sbom_support()  # must not raise


@pytest.mark.parametrize("bad_version", ["1.28.0", "1.27.0", "1.0.0"])
def test_check_hatchling_sbom_support_raises_below_minimum(bad_version: str) -> None:
    """Hatchling older than the minimum must raise a clear ``RuntimeError``."""
    with patch("pitloom.plugins.hatch._pkg_version", return_value=bad_version):
        with pytest.raises(RuntimeError, match="too old for PEP 770 SBOM embedding"):
            _check_hatchling_sbom_support()


def test_check_hatchling_sbom_support_accepts_exact_minimum() -> None:
    """Hatchling exactly at the minimum version must not raise."""
    with patch("pitloom.plugins.hatch._pkg_version", return_value="1.29.0"):
        _check_hatchling_sbom_support()


def test_check_hatchling_sbom_support_accepts_dev_build_of_minimum() -> None:
    """A pre-release/dev build of the minimum version already has the
    ``build_data["sbom_files"]`` mechanism, so it must not be rejected for
    sorting below the final release under plain PEP 440 ordering."""
    with patch(
        "pitloom.plugins.hatch._pkg_version",
        return_value="1.29.0.dev0+gabcdef",
    ):
        _check_hatchling_sbom_support()


@pytest.mark.parametrize(
    "bad_version_or_error",
    ["1.27.0", PackageNotFoundError("hatchling")],
)
def test_check_hatchling_sbom_support_errors_share_filterable_prefix(
    bad_version_or_error: str | PackageNotFoundError,
) -> None:
    """Every failure mode must share one prefix, so callers can grep/filter
    for this whole family of error with a single, stable string."""
    if isinstance(bad_version_or_error, Exception):
        mock_patch = patch(
            "pitloom.plugins.hatch._pkg_version", side_effect=bad_version_or_error
        )
    else:
        mock_patch = patch(
            "pitloom.plugins.hatch._pkg_version", return_value=bad_version_or_error
        )
    with mock_patch:
        with pytest.raises(RuntimeError, match=re.escape(_HATCHLING_ERROR_PREFIX)):
            _check_hatchling_sbom_support()


def test_resolve_build_datetime_uses_source_date_epoch_when_unpinned() -> None:
    """No pinned ``creation-datetime`` but SOURCE_DATE_EPOCH resolves: the
    epoch-derived timestamp is used (reproducible-builds fallback), rather
    than falling through to the current wall-clock time."""
    epoch_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    config = PitloomConfig(creation_datetime=None)
    with patch(
        "pitloom.plugins.hatch.resolve_source_date_epoch", return_value=epoch_dt
    ):
        result = _resolve_build_datetime(config)

    assert result == "2020-01-01T00:00:00+00:00"
