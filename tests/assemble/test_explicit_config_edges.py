# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Edge cases of explicit config sources and inert options in the library.

Each test pins one reviewed defect: an explicit config's ``use-lockfile``
reaching every lock-file decision, an sdist target's inert ``enrich`` and
registry, and an embed batch warning once.

See also: :mod:`tests.assemble.test_generator_no_implicit_config` (no
implicit reads) and :mod:`tests.cli.test_cli_option_reach` (every CLI
option reaches the library or warns).
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest

from pitloom.assemble import enrich_model, generate_project_sbom
from pitloom.core.config import PitloomConfig
from pitloom.core.creation import CreationMetadata
from pitloom.embed import ConfigOverrides, EmbedFileCache, embed_wheel_sbom
from pitloom.extract.project import resolve_project_with_lockfile
from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.assemble.enrich_identity_shared import (
    enrich_base_namespace,
    sbom_namespace,
)
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.warning_helpers import count_naming, logged_warnings

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"
_PINNED = CreationMetadata(creation_datetime="2026-01-01T00:00:00Z")


def _locked_project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    shutil.copytree(_FIXTURES / "sampleproject-poetry", project)
    return project


def test_resolver_takes_use_lockfile_from_an_explicit_config(tmp_path: Path) -> None:
    """The explicit config's ``use-lockfile`` decides the cascade when the
    flag is omitted, and the flag still wins over it."""
    project = _locked_project(tmp_path)
    no_lock = dataclasses.replace(PitloomConfig(), use_lockfile=False)

    via_config, config, _ = resolve_project_with_lockfile(project, None, no_lock)
    via_flag, _, _ = resolve_project_with_lockfile(project, False)
    flag_wins, _, _ = resolve_project_with_lockfile(project, True, no_lock)
    default, _, _ = resolve_project_with_lockfile(project, None)

    assert config is no_lock
    assert via_config.locked_dependencies == via_flag.locked_dependencies
    assert flag_wins.locked_dependencies == default.locked_dependencies
    # Non-vacuous: the lock file does change the metadata.
    assert via_flag.locked_dependencies != default.locked_dependencies


def test_enrich_model_base_identity_follows_the_explicit_config(
    tmp_path: Path,
) -> None:
    """``enrich --project-dir D --config C`` computes D's document identity
    with C's ``use-lockfile``, as ``project D --config C`` builds the base
    -- else the fragment names a document that does not exist."""
    project = _locked_project(tmp_path)
    no_lock = dataclasses.replace(PitloomConfig(), use_lockfile=False)
    base = sbom_namespace(
        generate_project_sbom(
            project, creation_metadata=_PINNED, pitloom_config=no_lock, offline=True
        )
    )

    def identity(**kwargs: Any) -> str:
        return enrich_base_namespace(project, tmp_path / "model", **kwargs)

    assert identity(pitloom_config=no_lock) == base
    assert identity(use_lockfile=False) == base
    # Non-vacuous: the lock file does change the identity.
    assert identity(use_lockfile=True) != base


def test_sdist_with_explicit_config_does_not_warn_about_use_lockfile(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An explicit config's ``use-lockfile`` (always set, default true) is not
    a given ``--use-lockfile``: an sdist has nothing to warn about."""
    sdist = _make_sdist(tmp_path)
    with caplog.at_level(logging.WARNING):
        generate_project_sbom(sdist, pitloom_config=PitloomConfig())
    assert count_naming(logged_warnings(caplog), "--use-lockfile") == 0


@pytest.mark.parametrize("value", [True, False])
def test_sdist_enrich_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: bool
) -> None:
    """An sdist has no AI-model scan, so a given ``enrich`` (either way)
    warns once instead of being dropped silently."""
    sdist = _make_sdist(tmp_path)
    with caplog.at_level(logging.WARNING):
        generate_project_sbom(sdist, enrich=value)
    assert count_naming(logged_warnings(caplog), "--enrich") == 1


def test_sdist_does_not_search_for_a_registry_beside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The directory holding an sdist (``dist/``, Downloads, cwd) is not its
    project: no ``loom-id-registry.json`` is searched for there or above; a named
    one is still loaded."""
    (tmp_path / "dist").mkdir()
    sdist = _make_sdist(tmp_path / "dist")
    registry_path = tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    IdRegistry(namespace="https://example.org/ns", path=registry_path).save()
    monkeypatch.chdir(tmp_path)
    loaded: list[Path] = []
    load = IdRegistry.load

    def spy_load(path: Path) -> IdRegistry:
        loaded.append(Path(path))
        return load(path)

    monkeypatch.setattr(IdRegistry, "load", spy_load)

    generate_project_sbom(sdist, creation_metadata=_PINNED)
    assert not loaded

    generate_project_sbom(sdist, creation_metadata=_PINNED, id_registry=registry_path)
    assert loaded == [registry_path]


@pytest.mark.parametrize("project", [False, True], ids=["standalone", "project"])
def test_embed_batch_warns_once_per_batch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, project: bool
) -> None:
    """A library batch sharing one EmbedFileCache warns once about an inert
    option and once about a too-small byte cap -- as the CLI batch does,
    and as the cache already does for build flags."""
    wheels = [
        _make_dummy_wheel(tmp_path / "w", name=name) for name in ("alpha", "beta")
    ]
    project_dir = None
    if project:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").write_text(
            '[project]\nname = "alpha"\nversion = "1.0.0"\n', encoding="utf-8"
        )
    overrides = ConfigOverrides(pretty=True, max_source_metadata_bytes=5)
    with caplog.at_level(logging.WARNING), EmbedFileCache() as cache:
        for wheel in wheels:
            embed_wheel_sbom(
                wheel,
                project_dir=project_dir,
                output_path=wheel.with_suffix(".out.whl"),
                creation_metadata=_PINNED,
                overrides=overrides,
                file_cache=cache,
            )
    warnings = logged_warnings(caplog)
    assert count_naming(warnings, "--pretty") == 1
    assert sum("too small" in w for w in warnings) == 1


def test_embed_without_a_batch_still_warns_per_call(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Without a shared cache each call is its own batch of one."""
    wheels = [
        _make_dummy_wheel(tmp_path / "w", name=name) for name in ("alpha", "beta")
    ]
    with caplog.at_level(logging.WARNING):
        for wheel in wheels:
            embed_wheel_sbom(
                wheel,
                output_path=wheel.with_suffix(".out.whl"),
                creation_metadata=_PINNED,
                overrides=ConfigOverrides(pretty=True),
            )
    assert count_naming(logged_warnings(caplog), "--pretty") == 2


@pytest.mark.parametrize("explicit", [False, True], ids=["own", "explicit"])
def test_enrich_model_registry_follows_the_base_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit: bool
) -> None:
    """``enrich --project-dir D`` looks ids up in the registry D's base SBOM
    used: D's own ``id-registry``, or an explicit config's in its place."""
    project = _locked_project(tmp_path)
    own = project / "own-id-registry.json"
    named = tmp_path / "named-id-registry.json"
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8")
        + '\n[tool.pitloom]\nid-registry = "own-id-registry.json"\n',
        encoding="utf-8",
    )
    for path in (own, named):
        IdRegistry(namespace="https://example.org/ns", path=path).save()
    loaded: list[Path] = []
    load = IdRegistry.load

    def spy_load(path: Path) -> IdRegistry:
        loaded.append(Path(path))
        return load(path)

    monkeypatch.setattr(IdRegistry, "load", spy_load)
    config = (
        dataclasses.replace(PitloomConfig(), id_registry=str(named))
        if explicit
        else None
    )
    enrich_model(
        SAFETENSORS_FIXTURE,
        project_target=project,
        creation_metadata=_PINNED,
        pitloom_config=config,
    )
    assert loaded == [named if explicit else own]


def test_embed_external_sbom_inert_byte_cap_warns_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An inert byte cap gets its no-effect warning only, not also the
    too-small one about a value nothing uses."""
    wheel = _make_dummy_wheel(tmp_path / "w", name="demo")
    sbom = tmp_path / "given.spdx3.json"
    sbom.write_text(generate_project_sbom(_make_sdist(tmp_path)), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(
            wheel,
            sbom_path=sbom,
            output_path=tmp_path / "out.whl",
            overrides=ConfigOverrides(max_source_metadata_bytes=-1),
            allow_mismatch=True,
        )
    warnings = logged_warnings(caplog)
    assert count_naming(warnings, "--max-source-metadata-bytes") == 1
    assert not any("too small" in w for w in warnings)


def test_sdist_relative_registry_resolves_as_for_a_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative ``id_registry=`` means the same file for an sdist as for a
    wheel -- the one under the current directory, not beside the archive."""
    (tmp_path / "dist").mkdir()
    sdist = _make_sdist(tmp_path / "dist")
    IdRegistry(namespace="https://example.org/ns", path=tmp_path / "ids.json").save()
    monkeypatch.chdir(tmp_path)
    loaded: list[Path] = []
    load = IdRegistry.load

    def spy_load(path: Path) -> IdRegistry:
        loaded.append(Path(path))
        return load(path)

    monkeypatch.setattr(IdRegistry, "load", spy_load)
    generate_project_sbom(sdist, creation_metadata=_PINNED, id_registry="ids.json")
    assert [p.resolve() for p in loaded] == [(tmp_path / "ids.json").resolve()]


def test_enrich_against_an_sdist_names_the_sdist_sbom_document(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``enrich --project-dir x.tar.gz`` computes the identity the sdist's
    own SBOM has, without walking the archive as if it were a directory
    (which only logs a file-discovery failure)."""
    sdist = _make_sdist(tmp_path)
    base = sbom_namespace(generate_project_sbom(sdist, creation_metadata=_PINNED))
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        namespace = enrich_base_namespace(sdist, tmp_path / "model")
    assert namespace == base
    assert not logged_warnings(caplog)


def test_enrich_against_an_sdist_does_not_search_for_a_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As for the sdist's own SBOM: the archive's directory is not a
    project, so no ``loom-id-registry.json`` is searched for there."""
    sdist = _make_sdist(tmp_path)
    IdRegistry(
        namespace="https://example.org/ns", path=tmp_path / DEFAULT_ID_REGISTRY_FILENAME
    ).save()
    monkeypatch.chdir(tmp_path)
    loaded: list[Path] = []
    load = IdRegistry.load

    def spy_load(path: Path) -> IdRegistry:
        loaded.append(Path(path))
        return load(path)

    monkeypatch.setattr(IdRegistry, "load", spy_load)
    enrich_model(
        SAFETENSORS_FIXTURE,
        project_target=sdist,
        creation_metadata=_PINNED,
        output_path=tmp_path / "frag.json",
    )
    assert not loaded


@pytest.mark.parametrize("value", [True, False])
def test_enrich_against_an_sdist_warns_about_use_lockfile_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, value: bool
) -> None:
    """An sdist has no lock-file cascade, as for its own SBOM."""
    sdist = _make_sdist(tmp_path)
    with caplog.at_level(logging.WARNING):
        enrich_model(
            SAFETENSORS_FIXTURE,
            project_target=sdist,
            creation_metadata=_PINNED,
            output_path=tmp_path / "frag.json",
            use_lockfile=value,
        )
    assert count_naming(logged_warnings(caplog), "--use-lockfile") == 1


def test_standalone_embed_uses_the_config_id_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wheel embedded without a project takes its registry from the given
    config's ``id-registry`` -- the only registry source it has."""
    wheel = _make_dummy_wheel(tmp_path / "w", name="demo")
    named = tmp_path / "named-id-registry.json"
    IdRegistry(namespace="https://example.org/ns", path=named).save()
    loaded: list[Path] = []
    load = IdRegistry.load

    def spy_load(path: Path) -> IdRegistry:
        loaded.append(Path(path))
        return load(path)

    monkeypatch.setattr(IdRegistry, "load", spy_load)
    config = dataclasses.replace(PitloomConfig(), id_registry=str(named))
    embed_wheel_sbom(
        wheel,
        pitloom_config=config,
        output_path=tmp_path / "out.whl",
        creation_metadata=_PINNED,
    )
    assert loaded == [named]


def test_embed_external_sbom_warns_about_a_project_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A project directory cannot change an SBOM embedded as is: the library
    says so, as the CLI does, instead of ignoring it."""
    wheel = _make_dummy_wheel(tmp_path / "w", name="demo")
    sbom = tmp_path / "given.spdx3.json"
    sbom.write_text(generate_project_sbom(_make_sdist(tmp_path)), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(
            wheel,
            sbom_path=sbom,
            project_dir=tmp_path / "nodir",
            output_path=tmp_path / "out.whl",
            allow_mismatch=True,
        )
    assert count_naming(logged_warnings(caplog), "--project-dir") == 1


def test_standalone_embed_warns_about_file_scan_options(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A wheel embedded without a project has no files to scan or models to
    enrich: the library warns once per such option, as the CLI does (the
    CLI clears them before the library sees them, so only this checks the
    library's own settle)."""
    wheel = _make_dummy_wheel(tmp_path / "w", name="demo")
    overrides = ConfigOverrides(
        enrich=True, content_type=True, extract_file_header=False
    )
    with caplog.at_level(logging.WARNING):
        embed_wheel_sbom(
            wheel,
            output_path=tmp_path / "out.whl",
            creation_metadata=_PINNED,
            overrides=overrides,
        )
    warnings = logged_warnings(caplog)
    for flag in ("--enrich", "--content-type", "--extract-file-header"):
        named = [w for w in warnings if f" {flag}/" in w]
        assert len(named) == 1, (flag, warnings)
        assert "no project directory" in named[0]
