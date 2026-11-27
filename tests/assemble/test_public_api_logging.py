# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every public library-API entry point (``pitloom.assemble``'s
``__all__`` -- ``generate_*`` (``generate_merged_sbom`` too)/``enrich_model``/
``embed_wheel_sbom``/``embed_sbom_in_wheel``/``merge_fragments``) calls
:func:`pitloom.logging_config.configure_logging` before doing anything else,
so ``log.warning(...)`` output gets the same ``WARNING: `` prefix whether
Pitloom is invoked via the CLI, the Hatchling build hook (``__main__.py`` and
``plugins/hatch.py`` do this too) or as a plain library import.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pitloom._wheel_sbom_location import find_embedded_sbom
from pitloom.assemble import (
    BuildOptions,
    embed_sbom_in_wheel,
    embed_wheel_sbom,
    enrich_model,
    generate,
    generate_env_sbom,
    generate_merged_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
    merge_fragments,
    project_document_id,
)
from pitloom.core.fetch_policy import RemoteFetchPolicy
from pitloom.export.spdx3_json import Spdx3JsonExporter
from pitloom.extract.remote.errors import RemoteSourceError
from pitloom.extract.remote.git import fetch_git_project
from pitloom.id_registry import IdRegistry, resolve_registry


def test_generate_configures_logging_before_its_own_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``generate()`` logs its own "has no effect" warnings for a
    non-project target before delegating, so it must configure logging
    first -- otherwise those lines reach stderr without ``WARNING:``."""
    events: list[str] = []
    monkeypatch.setattr(
        "pitloom.assemble.configure_logging", lambda: events.append("configure")
    )
    monkeypatch.setattr(
        "pitloom.assemble.generate_env_sbom", lambda **_kwargs: events.append("env")
    )

    def _settle(_self: BuildOptions, _subject: object, _reason: str) -> BuildOptions:
        events.append("warn")
        return BuildOptions()

    monkeypatch.setattr(BuildOptions, "settle_not_applicable", _settle)
    generate("env", build_options=BuildOptions(allow=True))
    assert events == ["configure", "warn", "env"]


def test_generate_project_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators.configure_logging", lambda: calls.append(True)
    )
    with pytest.raises(FileNotFoundError):
        generate_project_sbom(tmp_path / "does-not-exist")
    assert calls == [True]


def test_generate_wheel_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators_wheel.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        generate_wheel_sbom(tmp_path / "does-not-exist.whl")
    assert calls == [True]


def test_generate_env_sbom_configures_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators_env.configure_logging",
        lambda: calls.append(True),
    )

    class _Sentinel(Exception):
        pass

    def _raise() -> None:
        raise _Sentinel

    monkeypatch.setattr("pitloom.assemble._generators_env.read_environment", _raise)
    with pytest.raises(_Sentinel):
        generate_env_sbom()
    assert calls == [True]


def test_generate_model_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._model_generator.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        generate_model_sbom(tmp_path / "does-not-exist.gguf")
    assert calls == [True]


def test_enrich_model_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._model_generator.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        enrich_model(tmp_path / "does-not-exist.gguf")
    assert calls == [True]


def test_embed_wheel_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr("pitloom.embed.configure_logging", lambda: calls.append(True))
    with pytest.raises(FileNotFoundError):
        embed_wheel_sbom(tmp_path / "does-not-exist.whl")
    assert calls == [True]


def test_embed_sbom_in_wheel_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom._embed_wheel.configure_logging", lambda: calls.append(True)
    )
    with pytest.raises(FileNotFoundError):
        embed_sbom_in_wheel(tmp_path / "does-not-exist.whl", "{}")
    assert calls == [True]


def test_merge_fragments_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble.spdx3.fragments.configure_logging",
        lambda: calls.append(True),
    )
    merge_fragments(tmp_path, [], Spdx3JsonExporter())
    assert calls == [True]


def test_generate_merged_sbom_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._generators_merge.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        generate_merged_sbom(tmp_path / "does-not-exist")
    assert calls == [True]


def test_project_document_id_configures_logging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []
    monkeypatch.setattr(
        "pitloom.assemble._model_generator.configure_logging",
        lambda: calls.append(True),
    )
    with pytest.raises(FileNotFoundError):
        project_document_id(tmp_path)
    assert calls == [True]


def _registry_entry(tmp_path: Path) -> object:
    return IdRegistry.load(tmp_path / "gone.json")


def _registry_object(tmp_path: Path) -> object:
    return IdRegistry(namespace="https://example.org/ns/", path=tmp_path / "r.json")


def _resolve(tmp_path: Path) -> object:
    return resolve_registry(tmp_path / "gone.json", None, None)


def _embedded(tmp_path: Path) -> object:
    return find_embedded_sbom(tmp_path / "gone-1.0-py3-none-any.whl")


def _git(_tmp_path: Path) -> None:
    with fetch_git_project(
        "https://h.example/o/r", policy=RemoteFetchPolicy(offline=True)
    ):
        pytest.fail("fetched offline")  # pragma: no cover


@pytest.mark.platform
@pytest.mark.parametrize(
    ("module", "call"),
    [
        ("pitloom.id_registry._registry", _registry_entry),
        ("pitloom.id_registry._registry", _registry_object),
        ("pitloom.id_registry.resolve", _resolve),
        ("pitloom._wheel_sbom_location", _embedded),
        ("pitloom.extract.remote.git", _git),
    ],
    ids=["registry-load", "registry-new", "resolve-registry", "find-sbom", "git"],
)
def test_other_public_entries_configure_logging(
    module: str,
    call: Callable[[Path], object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``IdRegistry`` (every method runs on an object its constructor or
    ``load()`` made), ``resolve_registry``, ``find_embedded_sbom`` and
    ``fetch_git_project`` configure logging first, before what they read
    fails."""
    calls: list[bool] = []
    monkeypatch.setattr(f"{module}.configure_logging", lambda: calls.append(True))
    try:
        call(tmp_path)
    except (OSError, ValueError, RemoteSourceError):
        pass
    assert calls[:1] == [True]
