# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for ``generate_env_sbom``'s id-mint-collision fix:
a deployed dependency's hit-based pre-resolution
(:func:`pitloom.assemble.spdx3._document_deployed._resolve_deployed_package_hits`)
must never duplicate a spdxId across repeated runs with a harvested
registry, including when the installed environment's dependency set
changes between runs.

See also: :mod:`tests.core.generator.test_generator_registry_sync` for the
wheel/directory mint-collision regressions this mirrors, and
:mod:`tests.core.generator.test_generator_model` for ``build_deployed()``'s
basic (single-call) registry-reuse behaviour.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pitloom.assemble import generate_env_sbom
from pitloom.core.creation import CreationMetadata
from pitloom.id_registry import IdRegistry

from ...conftest import _assert_no_duplicate_spdx_ids


def _fake_pipdeptree_result(
    tree: list[dict[str, Any]],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pipdeptree", "--json-tree", "--all"],
        returncode=0,
        stdout=json.dumps(tree),
        stderr="",
    )


def _node(key: str, version: str = "1.0.0") -> dict[str, Any]:
    return {
        "package": {"key": key, "package_name": key, "installed_version": version},
    }


def _node_with_declared_name(
    key: str, package_name: str, version: str
) -> dict[str, Any]:
    """A node whose pipdeptree ``key`` and declared ``package_name`` differ
    in case, e.g. ``key="pyyaml"``, ``package_name="PyYAML"`` -- the real
    shape pipdeptree reports for a mixed-case-named PyPI distribution."""
    return {
        "package": {
            "key": key,
            "package_name": package_name,
            "installed_version": version,
        },
    }


def test_generate_env_sbom_grown_environment_never_duplicates_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 1 sees only ``requests``; run 2's environment has grown to
    ``{aaa, requests}``, with the registry auto-harvested from run 1 in
    between. The main ``deployed-environment`` package (always minted,
    never looked up) and ``aaa`` (never in the registry) must not collide
    with ``requests``'s reused id -- only exact-hit reservation (not a
    type-wide scan of every ``software_Package`` entity) keeps this
    deterministic; see ``_document_deployed.py``'s docstrings."""
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    with patch(
        "subprocess.run", return_value=_fake_pipdeptree_result([_node("requests")])
    ):
        first_json = generate_env_sbom(
            registry=registry_path, creation_metadata=creation_metadata
        )
    _assert_no_duplicate_spdx_ids(first_json)
    assert IdRegistry.load(registry_path).entities

    with patch(
        "subprocess.run",
        return_value=_fake_pipdeptree_result([_node("aaa"), _node("requests")]),
    ):
        second_json = generate_env_sbom(
            registry=registry_path, creation_metadata=creation_metadata
        )
    _assert_no_duplicate_spdx_ids(second_json)


def test_generate_env_sbom_identical_env_rerun_is_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rerunning against the *exact same* environment ``{requests}`` twice,
    registry harvested in between, must return byte-identical output --
    every package's own hit is reused, nothing is ever a miss, so no
    reservation choice can affect the result. Kept distinct from
    ``test_generate_env_sbom_dep_added_then_removed_returns_to_original_bytes``
    below: a naive type-wide ``software_Package`` reservation (every
    registry entry of that type, not just this run's own hits) still
    passes *this* test, since nothing here is ever a miss whose fresh
    mint could drift -- catching that mutant needs the add-then-remove
    round trip instead."""
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    def _run() -> str:
        with patch(
            "subprocess.run", return_value=_fake_pipdeptree_result([_node("requests")])
        ):
            return generate_env_sbom(
                registry=registry_path, creation_metadata=creation_metadata
            )

    first_json = _run()
    _assert_no_duplicate_spdx_ids(first_json)

    second_json = _run()
    _assert_no_duplicate_spdx_ids(second_json)
    assert second_json == first_json


def test_generate_env_sbom_dep_added_then_removed_returns_to_original_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dependency added then removed again (run1 {requests} -> run2
    {aaa, requests} -> run3 {requests}) must return run3 to run1's exact
    bytes -- reserving the whole type-wide ``software_Package`` entity
    set (instead of only the ids this document's own lookups actually
    hit) drifts ``requests``'s own id between these runs even though its
    own hit never changes, since unrelated entries (the main
    ``deployed-environment`` package, ``aaa``) get reserved too and shift
    every miss's fresh-minted number."""
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")

    def _run(tree: list[dict[str, Any]]) -> str:
        with patch("subprocess.run", return_value=_fake_pipdeptree_result(tree)):
            return generate_env_sbom(
                registry=registry_path, creation_metadata=creation_metadata
            )

    first_json = _run([_node("requests")])
    _assert_no_duplicate_spdx_ids(first_json)

    second_json = _run([_node("aaa"), _node("requests")])
    _assert_no_duplicate_spdx_ids(second_json)
    # Confirm the environment actually changed between run 1 and run 2, so
    # a byte match between run 1 and run 3 below is meaningful and not a
    # vacuous pass from a no-op rerun.
    assert first_json != second_json

    third_json = _run([_node("requests")])
    _assert_no_duplicate_spdx_ids(third_json)
    assert third_json == first_json


def test_generate_env_sbom_reuses_package_id_despite_name_case_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package's declared name (``PyYAML``, what harvest stores as the
    element's ``name``) and pipdeptree's own lowercased ``key`` (used only
    to query the lookup) must resolve to the same registry entry -- both
    sides go through PEP 503 canonicalization
    (:func:`packaging.utils.canonicalize_name`), so a purely-cosmetic name
    mismatch doesn't leave the harvested entry dead weight and the
    package's id unstable across runs."""
    monkeypatch.chdir(tmp_path)
    registry_path = tmp_path / "loom-ids.json"
    IdRegistry.new("env-sync", path=registry_path).save()
    creation_metadata = CreationMetadata(creation_datetime="2026-01-01T00:00:00+00:00")
    tree = [_node_with_declared_name("pyyaml", "PyYAML", "6.0")]

    def _run() -> str:
        with patch("subprocess.run", return_value=_fake_pipdeptree_result(tree)):
            return generate_env_sbom(
                registry=registry_path, creation_metadata=creation_metadata
            )

    first_json = _run()
    _assert_no_duplicate_spdx_ids(first_json)
    reloaded = IdRegistry.load(registry_path)
    assert ("software_Package", "pyyaml") in reloaded.entities
    first_id = json.loads(first_json)["@graph"]
    first_pkg_id = next(
        e["spdxId"]
        for e in first_id
        if e.get("type") == "software_Package" and e.get("name") == "PyYAML"
    )

    second_json = _run()
    _assert_no_duplicate_spdx_ids(second_json)
    second_pkg_id = next(
        e["spdxId"]
        for e in json.loads(second_json)["@graph"]
        if e.get("type") == "software_Package" and e.get("name") == "PyYAML"
    )
    assert second_pkg_id == first_pkg_id
