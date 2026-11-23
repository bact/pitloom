# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Hatchling version gate, the SBOM file name check and
build-datetime resolution in the Pitloom Hatchling build hook."""

# pylint: disable=protected-access

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from pitloom.core.config import PitloomConfig
from pitloom.messages import code_of
from pitloom.plugins._hatch_document import resolve_build_datetime
from pitloom.plugins.hatch import _check_hatchling_sbom_support

from ..conftest import make_hook


def test_check_hatchling_sbom_support_passes_for_current_hatchling() -> None:
    """The Hatchling installed in the test environment must satisfy the gate."""
    _check_hatchling_sbom_support()  # must not raise


@pytest.mark.parametrize("bad_version", ["1.28.0", "1.27.0", "1.0.0"])
def test_check_hatchling_sbom_support_raises_below_minimum(bad_version: str) -> None:
    """Hatchling older than the minimum must raise a clear coded error (a
    ``ValueError``), naming the release found and the one needed."""
    with patch("pitloom.plugins.hatch._pkg_version", return_value=bad_version):
        with pytest.raises(
            ValueError,
            match=rf"^Hatchling {bad_version} cannot embed an SBOM \(PEP 770 "
            r"needs 1\.29\.0 or later\); upgrade Hatchling$",
        ) as caught:
            _check_hatchling_sbom_support()
    assert code_of(caught.value) == "library-unusable/hatchling"


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
            "pitloom.plugins.hatch._pkg_version",
            side_effect=bad_version_or_error,
        )
    else:
        mock_patch = patch(
            "pitloom.plugins.hatch._pkg_version",
            return_value=bad_version_or_error,
        )
    with mock_patch:
        with pytest.raises(ValueError, match=r"^Hatchling ") as caught:
            _check_hatchling_sbom_support()
    assert code_of(caught.value) == "library-unusable/hatchling"


@pytest.mark.parametrize(
    "placed",
    ["mine.spdx3.json", "dist/MINE.Spdx3.JSON"],
    ids=["same", "other-case-in-a-directory"],
)
def test_an_sbom_files_entry_of_the_staged_name_is_refused_as_coded(
    tmp_path: Path, placed: str
) -> None:
    """The check runs on the name ignoring case, over Hatchling's own
    ``sbom-files`` and another hook's ``build_data``."""
    for config_side in (True, False):
        hook = make_hook(str(tmp_path), {})
        build_data: dict[str, Any] = {"sbom_files": []}
        if config_side:
            cast(Any, hook.build_config).sbom_files.append(placed)
        else:
            build_data["sbom_files"] = [placed]
        with pytest.raises(ValueError, match="sbom-files entry") as caught:
            hook._check_name_is_free("mine.spdx3.json", build_data)
        assert code_of(caught.value) == "sbom-name-conflict"
        assert str(caught.value).startswith("FILE=mine.spdx3.json: also the name")
        assert f"sbom-files entry '{placed}'" in str(caught.value)


def test_an_sbom_files_entry_of_another_name_is_free(tmp_path: Path) -> None:
    hook = make_hook(str(tmp_path), {})
    hook._check_name_is_free("mine.spdx3.json", {"sbom_files": ["other.spdx3.json"]})


def test_resolve_build_datetime_uses_source_date_epoch_when_unpinned() -> None:
    """No pinned ``creation-datetime`` but SOURCE_DATE_EPOCH resolves: the
    epoch-derived timestamp is used (reproducible-builds fallback), rather
    than falling through to the current wall-clock time."""
    epoch_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    config = PitloomConfig(creation_datetime=None)
    with patch(
        "pitloom.plugins._hatch_document.resolve_source_date_epoch",
        return_value=epoch_dt,
    ):
        result = resolve_build_datetime(config)

    assert result == "2020-01-01T00:00:00+00:00"


_PIN = "2026-01-01T00:00:00+00:00"


def test_a_pinned_creation_datetime_beats_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert resolve_build_datetime(PitloomConfig(creation_datetime=_PIN)) == _PIN


def test_a_malformed_epoch_fails_even_when_a_date_is_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "abc")
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        resolve_build_datetime(PitloomConfig(creation_datetime=_PIN))
