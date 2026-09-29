# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :class:`~pitloom.id_registry.IdRegistrySession`.

See also: test_registry.py (the underlying ``IdRegistry``),
tests/core/generator/test_generator_registry_sync_claim.py (the same
claim/collision semantics exercised through the real resolvers).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pitloom.id_registry import IdRegistry, IdRegistrySession

_REPO_SRC = Path(__file__).resolve().parents[2] / "src"


def _registry_with(namespace: str = "urn:test") -> IdRegistry:
    registry = IdRegistry.new(namespace.removeprefix("urn:"))
    registry.namespace = namespace
    return registry


def test_file_id_no_registry_returns_none_without_on_miss() -> None:
    calls: list[None] = []
    session = IdRegistrySession(None)

    result = session.file_id(
        "a", ["a.py"], "deadbeef", on_miss=lambda: calls.append(None)
    )

    assert result is None
    assert not calls


def test_entity_id_no_registry_returns_none_without_on_miss() -> None:
    calls: list[None] = []
    session = IdRegistrySession(None)

    result = session.entity_id(
        "a", ["model"], "ai_AIPackage", on_miss=lambda: calls.append(None)
    )

    assert result is None
    assert not calls


def test_file_id_raw_miss_calls_on_miss_once() -> None:
    registry = _registry_with()
    session = IdRegistrySession(registry)
    calls: list[None] = []

    result = session.file_id(
        "a", ["a.py", "b.py"], "deadbeef", on_miss=lambda: calls.append(None)
    )

    assert result is None
    assert len(calls) == 1


def test_entity_id_raw_miss_calls_on_miss_once() -> None:
    registry = _registry_with()
    session = IdRegistrySession(registry)
    calls: list[None] = []

    result = session.entity_id(
        "a", ["model", "model2"], "ai_AIPackage", on_miss=lambda: calls.append(None)
    )

    assert result is None
    assert len(calls) == 1


def test_file_id_tries_paths_in_order_first_hit_wins() -> None:
    registry = _registry_with()
    sha = "a" * 64
    registered_id = registry.register_file("physical/a.py", sha)
    session = IdRegistrySession(registry)

    result = session.file_id("a", ["physical/a.py", "dist/a.py"], sha)

    assert result == registered_id


def test_file_id_falls_back_to_second_path() -> None:
    registry = _registry_with()
    sha = "b" * 64
    registered_id = registry.register_file("dist/a.py", sha)
    session = IdRegistrySession(registry)

    result = session.file_id("a", ["physical/a.py", "dist/a.py"], sha)

    assert result == registered_id


def test_entity_id_hit_is_claimed() -> None:
    registry = _registry_with()
    registered_id = registry.register_entity("model", "ai_AIPackage")
    session = IdRegistrySession(registry)

    result = session.entity_id("claimant", ["model"], "ai_AIPackage")

    assert result == registered_id
    assert session.claimed_ids() == [registered_id]


def test_second_claimant_on_same_id_is_rejected_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The *first* claimant of a registry hit keeps it; every repeat is a
    miss -- and a rejection is not an on_miss trigger (see the next
    test)."""
    registry = _registry_with()
    registered_id = registry.register_entity("model", "ai_AIPackage")
    session = IdRegistrySession(registry)

    first = session.entity_id("first", ["model"], "ai_AIPackage")
    with caplog.at_level("WARNING"):
        second = session.entity_id("second", ["model"], "ai_AIPackage")

    assert first == registered_id
    assert second is None
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "registered for both" in warnings[0].message
    assert "first" in warnings[0].message
    assert "second" in warnings[0].message


def test_rejected_claim_does_not_call_on_miss() -> None:
    """A claim rejection (the id exists, but something else already
    claimed it) is not a raw miss -- on_miss must not fire for it."""
    registry = _registry_with()
    registry.register_entity("model", "ai_AIPackage")
    session = IdRegistrySession(registry)
    session.entity_id("first", ["model"], "ai_AIPackage")

    calls: list[None] = []
    result = session.entity_id(
        "second", ["model"], "ai_AIPackage", on_miss=lambda: calls.append(None)
    )

    assert result is None
    assert not calls


def test_claimed_ids_reflects_claim_order_across_file_and_entity_hits() -> None:
    registry = _registry_with()
    file_sha = "c" * 64
    file_id = registry.register_file("a.py", file_sha)
    entity_id = registry.register_entity("model", "ai_AIPackage")
    session = IdRegistrySession(registry)

    session.entity_id("model-claimant", ["model"], "ai_AIPackage")
    session.file_id("a.py-claimant", ["a.py"], file_sha)

    assert session.claimed_ids() == [entity_id, file_id]


def test_claimed_ids_empty_for_fresh_session() -> None:
    assert not IdRegistrySession(None).claimed_ids()
    assert not IdRegistrySession(_registry_with()).claimed_ids()


def test_registry_property_exposes_underlying_registry() -> None:
    registry = _registry_with()
    assert IdRegistrySession(registry).registry is registry
    assert IdRegistrySession(None).registry is None


def test_no_direct_registry_lookup_outside_id_registry_package() -> None:
    """Guard: every ``IdRegistry.lookup_file``/``lookup_entity`` call in
    ``src/`` outside ``pitloom.id_registry`` itself must go through
    :class:`IdRegistrySession` instead -- a direct call bypasses the
    first-claimant-wins collision guard this session exists to enforce."""
    result = subprocess.run(
        [
            "grep",
            "-rEn",
            r"\.lookup_(file|entity)\(",
            "--include=*.py",
            str(_REPO_SRC),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    offending = [
        line
        for line in result.stdout.splitlines()
        if "/id_registry/" not in line.replace("\\", "/")
    ]
    assert not offending, "\n".join(offending)
