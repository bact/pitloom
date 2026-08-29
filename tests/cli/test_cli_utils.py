# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for pitloom.cli.commands.utils.resolve_effective_provenance()."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import argparse
import logging

import pytest

from pitloom.cli.commands.utils import resolve_effective_provenance
from pitloom.core.config import PitloomConfig


def _args(max_source_metadata_bytes: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(max_source_metadata_bytes=max_source_metadata_bytes)


def test_no_override_returns_config_provenance_unchanged() -> None:
    cfg = PitloomConfig(provenance_max_source_metadata_bytes=1234)
    provenance = resolve_effective_provenance(cfg, _args())
    assert provenance.max_source_metadata_bytes == 1234


def test_cli_override_replaces_config_value() -> None:
    cfg = PitloomConfig(provenance_max_source_metadata_bytes=1234)
    provenance = resolve_effective_provenance(
        cfg, _args(max_source_metadata_bytes=9000)
    )
    assert provenance.max_source_metadata_bytes == 9000


def test_cli_override_preserves_other_provenance_fields() -> None:
    cfg = PitloomConfig(provenance_format="annotation", provenance_detail="full")
    provenance = resolve_effective_provenance(
        cfg, _args(max_source_metadata_bytes=9000)
    )
    assert provenance.format == "annotation"
    assert provenance.detail == "full"


def test_negative_cli_override_normalizes_to_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cfg = PitloomConfig()
    with caplog.at_level(logging.WARNING):
        provenance = resolve_effective_provenance(
            cfg, _args(max_source_metadata_bytes=-5)
        )
    assert provenance.max_source_metadata_bytes == 0
    assert "max-source-metadata-bytes" in caplog.text


def test_missing_attribute_treated_as_no_override() -> None:
    cfg = PitloomConfig(provenance_max_source_metadata_bytes=1234)
    provenance = resolve_effective_provenance(cfg, argparse.Namespace())
    assert provenance.max_source_metadata_bytes == 1234
