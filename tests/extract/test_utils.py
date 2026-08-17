# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for shared extractor utilities."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from pitloom.extract._extract_utils import record_dict_field_provenance


def test_record_dict_field_provenance_per_key() -> None:
    """Each dict key gets its own exact provenance entry -- no shared generic
    note. The key is the origin (e.g. a GGUF kv key)."""
    provenance: dict[str, str] = {}
    record_dict_field_provenance(
        provenance,
        "hyperparameters",
        ["bert.block_count", "bert.head_count"],
        "Source: model.gguf",
    )
    assert provenance == {
        "hyperparameters.bert.block_count": (
            "Source: model.gguf | Field: bert.block_count"
        ),
        "hyperparameters.bert.head_count": (
            "Source: model.gguf | Field: bert.head_count"
        ),
    }


def test_record_dict_field_provenance_location_prefix() -> None:
    """A short key under a common origin path uses the prefix in the location
    (e.g. a Keras hyperparameter stored under config.config.<key>)."""
    provenance: dict[str, str] = {}
    record_dict_field_provenance(
        provenance,
        "hyperparameters",
        ["units"],
        "Source: model.keras",
        location_prefix="config.config.",
    )
    assert (
        provenance["hyperparameters.units"]
        == "Source: model.keras | Field: config.config.units"
    )


def test_record_dict_field_provenance_empty_keys_is_noop() -> None:
    provenance: dict[str, str] = {}
    record_dict_field_provenance(provenance, "properties", [], "Source: x")
    assert not provenance


def test_record_dict_field_provenance_sanitizes_pipe_in_key() -> None:
    """A key from an untrusted binary artifact can contain ``|`` -- the
    provenance-string delimiter. Unescaped, a key like
    ``"arch | Source: pyproject.toml"`` would inject a fake ``Source:``
    segment when the string is later re-parsed by
    :func:`~pitloom.assemble.spdx3.provenance.parse_provenance_value`,
    misattributing the provenance to a transparent manifest and causing it to
    be silently dropped in minimal detail mode."""
    # pylint: disable=import-outside-toplevel

    from pitloom.assemble.spdx3.provenance import (
        filter_high_signal,
        parse_provenance_value,
    )

    provenance: dict[str, str] = {}
    malicious_key = "arch | Source: pyproject.toml"
    record_dict_field_provenance(
        provenance, "hyperparameters", [malicious_key], "Source: model.gguf"
    )
    value = provenance[f"hyperparameters.{malicious_key}"]

    assert "|" not in value.split("Field: ", 1)[1]
    parsed = parse_provenance_value(value)
    assert parsed["source"] == "model.gguf"
    assert parsed["source"] != "pyproject.toml"
    # A non-manifest source stays high-signal -- not silently dropped.
    assert filter_high_signal(provenance) == provenance
