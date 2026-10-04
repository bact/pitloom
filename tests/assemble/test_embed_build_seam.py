# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Config values reach the SBOM assembler identically on every surface.

``content_type_method`` and ``provenance.max_source_metadata_bytes`` are
resolved from the CLI flag / library override / ``[tool.pitloom]`` cascade
by each surface, then handed to ``build()`` or ``build_deployed()``. Each
surface reaches that hand-off by its own route, so one can drop a value the
others keep.

The seam observed here is ``_finish_dependency_enrichment()``, the one leaf
both ``add_dependencies()`` (``build()``) and ``_build_deployed_package()``
(``build_deployed()``) funnel each dependency through. Spying there, rather
than at either assembler's entry, is what makes a value *accepted and then
dropped* visible: a parameter that never arrives at the leaf fails here even
though every signature still names it.

See also:
- :mod:`tests.assemble.embed_surfaces_shared` for the surfaces run here.
- :mod:`tests.assemble.test_embed_authors_fetch` for what the assembler then
  does with the method.
- :mod:`tests.core.test_config_cascade` for ``apply_overrides`` itself.
- :mod:`tests.test_build_flag_warnings` for the surface x target matrix this
  module's runners are modelled on.
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from pitloom.assemble.spdx3 import document as spdx3_document
from pitloom.assemble.spdx3.deps import _finish_dependency_enrichment
from pitloom.core.config import AssembleOptions, PitloomConfig
from pitloom.core.config_cascade import apply_overrides
from pitloom.core.provenance import ProvenanceConfig
from pitloom.embed import ConfigOverrides, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel
from tests.assemble.embed_surfaces_shared import (
    DEPENDENCY,
    RUNNERS,
    config_toml,
    demo_project,
    demo_wheel,
    hatch_hook,
    run_cli,
)


class _Recorded:
    """The ``_finish_dependency_enrichment()`` calls one surface run made."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self.calls = calls

    def method(self) -> str:
        # A call site that omits the keyword leaves it to the leaf's own
        # "auto" default -- the silent drop under test -- so read it as
        # absent rather than letting it read back as a deliberate "auto".
        methods = {c.get("content_type_method", "<not passed>") for c in self.calls}
        assert len(methods) == 1, methods
        return str(methods.pop())

    def max_bytes(self) -> int:
        # Read like method(): a call site that omits the keyword is the
        # silent drop under test, not a legitimate "no cap".
        assert all("provenance_config" in c for c in self.calls), (
            "a call site reached the leaf without passing provenance_config"
        )
        sizes = {c["provenance_config"].max_source_metadata_bytes for c in self.calls}
        assert len(sizes) == 1, sizes
        return int(sizes.pop())


# Both call sites hold their own reference to the leaf, so one patch cannot
# cover both: deps.py calls it as a module global, _document_deployed.py
# imported it by name.
_SPY_TARGETS = (
    "pitloom.assemble.spdx3.deps._finish_dependency_enrichment",
    "pitloom.assemble.spdx3._document_deployed._finish_dependency_enrichment",
)


@pytest.fixture(name="calls")
def _calls_fixture(monkeypatch: pytest.MonkeyPatch) -> _Recorded:
    calls: list[dict[str, Any]] = []

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return _finish_dependency_enrichment(*args, **kwargs)

    for target in _SPY_TARGETS:
        monkeypatch.setattr(target, _spy)
    return _Recorded(calls)


_METHOD_CASES = [
    # (config value, override, expected effective method) -- one tuple
    # parameter keeps each test under the argument-count ceiling.
    pytest.param((None, None, "auto"), id="nothing-given"),
    pytest.param(("extension", None, "extension"), id="config-only"),
    pytest.param((None, "extension", "extension"), id="override-only"),
    # An explicit override equal to the built-in default must still win.
    pytest.param(("extension", "auto", "auto"), id="override-default-beats-config"),
    pytest.param(("auto", "extension", "extension"), id="override-beats-config"),
]


@pytest.mark.parametrize("surface", sorted(RUNNERS))
@pytest.mark.parametrize("case", _METHOD_CASES)
def test_content_type_method_reaches_assembler(
    surface: str,
    case: tuple[str | None, str | None, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: _Recorded,
) -> None:
    """Every surface resolves the same cascade and hands the winner on."""
    config, override, expected = case
    RUNNERS[surface](tmp_path, monkeypatch, config_toml(config, None), override, None)
    assert calls.calls, "surface never reached the assembler"
    assert calls.method() == expected


# The hook has no per-run override to carry a byte cap.
@pytest.mark.parametrize("surface", [s for s in sorted(RUNNERS) if s != "hatch-hook"])
@pytest.mark.parametrize(
    "case",
    [
        pytest.param((None, 5000, 5000), id="override-only"),
        pytest.param((7000, None, 7000), id="config-only"),
        pytest.param((7000, 5000, 5000), id="override-beats-config"),
        # 0 is falsy and the default: an explicit 0 must still clear the config's cap.
        pytest.param((7000, 0, 0), id="override-zero-clears-config"),
    ],
)
def test_max_source_metadata_bytes_reaches_assembler(
    surface: str,
    case: tuple[int | None, int | None, int],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    calls: _Recorded,
) -> None:
    """The byte cap is not lost between the override and the assembler."""
    config, override, expected = case
    RUNNERS[surface](tmp_path, monkeypatch, config_toml(None, config), None, override)
    assert calls.max_bytes() == expected


def test_hatch_hook_reads_config_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """The hook's only input is the config file: a non-default method and
    byte cap must both arrive (the byte-cap test above excludes the hook)."""
    hatch_hook(tmp_path, monkeypatch, config_toml("extension", 4321), None, None)
    assert (calls.method(), calls.max_bytes()) == ("extension", 4321)


def test_embed_batch_passes_method_for_every_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """One ``EmbedFileCache`` batch: the method reaches each wheel's build,
    not just the first (the cache holds per-batch state)."""
    project = demo_project(tmp_path, config_toml("extension", None))
    wheels = [
        _make_dummy_wheel(
            tmp_path / f"dist{i}",
            "demo",
            "1.0.0",
            requires_dist=(f"{DEPENDENCY}==1.0",),
        )
        for i in range(2)
    ]
    run_cli(
        [
            "embed-wheel",
            *map(str, wheels),
            "--project-dir",
            str(project),
            "--offline",
        ],
        monkeypatch,
    )
    assert len(calls.calls) >= 2, "expected one assembler run per wheel"
    assert calls.method() == "extension"


# "" is falsy but not None: an ignored empty override would silently fall
# back to the config value instead of being rejected.
@pytest.mark.parametrize("method", ["mimetypes", ""])
def test_embed_rejects_invalid_method_before_assembling(
    method: str, tmp_path: Path, calls: _Recorded
) -> None:
    project = demo_project(tmp_path)
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    with pytest.raises(ValueError, match="content_type_method must be one of"):
        embed_wheel_sbom(
            wheel,
            project_dir=project,
            overrides=ConfigOverrides(content_type_method=method),
        )
    assert not calls.calls


def test_embed_sbom_bytes_are_deterministic_with_method(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Recorded
) -> None:
    """Two embeds under the same non-default method give identical bytes.
    The method only affects the authors-file fetch, which offline skips, so
    this guards against the hand-off adding run-to-run variation."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    outputs = []
    for run in ("a", "b"):
        base = tmp_path / run
        project = demo_project(base, config_toml("extension", None))
        wheel = demo_wheel(base)
        _, _, sbom_json, _, _ = embed_wheel_sbom(
            wheel,
            project_dir=project,
            overrides=ConfigOverrides(offline=True),
        )
        outputs.append(sbom_json)
    assert {c["content_type_method"] for c in calls.calls} == {"extension"}
    assert outputs[0] == outputs[1]


def _every_field_non_default(prov: ProvenanceConfig) -> ProvenanceConfig:
    """*prov* with every field changed away from its default."""
    changed: dict[str, Any] = {}
    for f in dataclasses.fields(prov):
        value = getattr(prov, f.name)
        # +8: the smallest valid change of a byte budget from 0
        changed[f.name] = value + 8 if isinstance(value, int) else f"{value}-x"
    return dataclasses.replace(prov, **changed)


def test_apply_overrides_round_trips_every_provenance_field() -> None:
    """A ``ProvenanceConfig`` field with no matching
    ``PitloomConfig.provenance_<name>`` (or not read back by
    ``PitloomConfig.provenance``) fails here, whatever its name."""
    prov = _every_field_non_default(ProvenanceConfig())
    assert all(
        getattr(prov, f.name) != getattr(ProvenanceConfig(), f.name)
        for f in dataclasses.fields(prov)
    ), "the input must differ from the default in every field"

    overridden = apply_overrides(PitloomConfig(), ConfigOverrides(provenance=prov))
    assert overridden.provenance == prov


def test_assemble_options_mirror_the_config() -> None:
    """Each key carries its own config value (all non-default, so a key
    wired to the wrong source cannot pass by coincidence)."""
    cfg = PitloomConfig(
        provenance_detail="full",
        provenance_max_source_metadata_bytes=999,
        offline=True,
        content_type_method="extension",
    )
    options = cfg.assemble_options
    assert options["provenance"] == cfg.provenance
    assert options["provenance"] != ProvenanceConfig()
    assert options["offline"] is True
    assert options["content_type_method"] == "extension"


# build() parameters a caller supplies per call, not from [tool.pitloom].
_PER_CALL_BUILD_PARAMS = frozenset(
    {"doc", "merkle_root", "sbom_type", "registry", "enrichment_results_by_model"}
)


def test_every_build_parameter_is_classified() -> None:
    """A new ``build()`` parameter must be added to ``AssembleOptions`` (a
    config-sourced setting) or to ``_PER_CALL_BUILD_PARAMS`` (supplied per
    call) -- the converse of the drift this module guards, where a surface
    keeps a setting the shared hand-off never learned about."""
    build_params = set(inspect.signature(spdx3_document.build).parameters)
    assert build_params - _PER_CALL_BUILD_PARAMS == set(AssembleOptions.__annotations__)


def test_provenance_override_replaces_the_config_provenance_whole() -> None:
    """``ConfigOverrides.provenance`` is one object: a partial one resets the
    fields it leaves at their defaults, byte cap included, exactly as it does
    the other four (the CLI always passes a fully resolved object)."""
    cfg = PitloomConfig(
        provenance_detail="full", provenance_max_source_metadata_bytes=8192
    )
    overridden = apply_overrides(
        cfg, ConfigOverrides(provenance=ProvenanceConfig(format="fields"))
    )
    assert overridden.provenance == ProvenanceConfig(format="fields")
    assert cfg.provenance != overridden.provenance


@dataclasses.dataclass(frozen=True)
class _ExtendedProvenance(ProvenanceConfig):
    """A caller's own subclass: its extra field has no config counterpart."""

    note: str = "extra"


def test_apply_overrides_reads_only_provenance_config_fields() -> None:
    """An override that is not a plain ``ProvenanceConfig`` (a subclass, or a
    ``Mock(spec=...)``) contributes its five known fields; extras are ignored,
    not passed on to ``PitloomConfig``."""
    subclass = _ExtendedProvenance(detail="full", max_source_metadata_bytes=4096)
    overridden = apply_overrides(PitloomConfig(), ConfigOverrides(provenance=subclass))
    assert overridden.provenance == ProvenanceConfig(
        detail="full", max_source_metadata_bytes=4096
    )

    fake = mock.Mock(spec=ProvenanceConfig, **dataclasses.asdict(subclass))
    overridden = apply_overrides(PitloomConfig(), ConfigOverrides(provenance=fake))
    assert overridden.provenance == ProvenanceConfig(
        detail="full", max_source_metadata_bytes=4096
    )
