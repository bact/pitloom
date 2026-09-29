# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Declared-bad-registry failure, and undeclared-is-never-loaded, swept
across *every* ``(surface, mode)`` pair -- not just one representative
surface per category, as :mod:`tests.id_registry.test_surfaces`'s
narrower ``test_library_and_loom_declared_bad_registry_raises`` /
``test_hook_declared_bad_registry_raises_one_error_no_sbom_files`` do. A
surface
offering three declaration modes (``flag``/``own_key``/``config_key``)
resolves each through a different code path (see
:mod:`tests.id_registry.test_relative_paths`'s module docstring for the
per-route base-directory breakdown) -- only sweeping every mode, not just
``flag``, catches a route-specific regression.

``pitloom id generate``/``pitloom id import`` are excluded from both
sweeps below: they are registry-*producing* commands, not
registry-*consuming* ones, so neither invariant applies to them as
written --

- A "declared but missing" registry is not a failure for them (see
  :func:`pitloom.cli.id._load_or_create_registry`: a missing target is
  created fresh) -- only "malformed" is, and it is covered by a
  dedicated test in this module.
- "Undeclared" for them means "default to ``<project_dir>/
  loom-id-registry.json``" (see
  :func:`pitloom.cli.id._resolve_id_registry_target`), which *does* call
  ``IdRegistry.load`` when that default file happens to exist -- the
  opposite of "never loaded". :mod:`tests.id_registry.test_surfaces`'s
  ``test_id_generate_creates_missing_declared_registry_and_logs_hint``
  covers their own resolution default.

See also: :mod:`tests.id_registry.surfaces_shared` (``SURFACES``,
``SUPPORTED_MODES``, ``Declare``), :mod:`tests.id_registry.test_surfaces`
(the single-representative-surface versions of these same failure modes,
plus the completeness guards these sweeps rely on to stay exhaustive).
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.id_registry import DEFAULT_ID_REGISTRY_FILENAME, IdRegistry
from tests.id_registry.surfaces_shared import (
    CLI_SURFACES,
    LIBRARY_RUNNERS,
    LIBRARY_RUNNERS_WITH_OUTPUT_PATH,
    SUPPORTED_MODES,
    SURFACES,
    Declare,
    demo_project,
    demo_wheel,
    lib_embed_wheel_sbom,
    run_hook,
)

#: `id generate`/`id import` are registry-*producing* commands with their
#: own resolution semantics -- see the module docstring.
_ID_COMMAND_SURFACES = frozenset({"cli-id-generate", "cli-id-import"})

#: (surface, mode) pairs, for the CLI surfaces this module's generic
#: "declared bad registry -> one error, exit 1" sweep applies to.
_CLI_FAILURE_CASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (surface, mode)
        for surface, modes in SUPPORTED_MODES.items()
        if surface in CLI_SURFACES and surface not in _ID_COMMAND_SURFACES
        for mode in modes
    )
)

#: Same, for every library-function/hook/loom-run surface -- these raise
#: rather than returning an exit code.
_RAISING_FAILURE_CASES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (surface, mode)
        for surface, modes in SUPPORTED_MODES.items()
        if surface in (*LIBRARY_RUNNERS, "hook", "loom-run")
        for mode in modes
    )
)

#: Surface -> the SBOM output path its CLI runner writes with ``-o``, for
#: the surfaces where that path is predictable and separate from any
#: input. ``None``/absent (wheel-embed, embed-wheel) means the surface
#: embeds in place rather than writing a separate output file -- no
#: generic "no output file" assertion applies there; the exit-code and
#: single-``ERROR:``-line assertions still do.
_CLI_OUTPUT_PATH: dict[str, str] = {
    "cli-project": "out.spdx3.json",
    "cli-project-sdist": "out.spdx3.json",
    "cli-generate": "out.spdx3.json",
    "cli-wheel": "out.spdx3.json",
    "cli-env": "out.spdx3.json",
    "cli-model": "out.spdx3.json",
    "cli-enrich-standalone": "out.enrich.spdx3.json",
    "cli-enrich-project": "out.enrich.spdx3.json",
}

_CONTENT_IDS = ["missing", "malformed-json"]
_CONTENT_VALUES = [None, "{"]


# --- CLI surfaces: one ERROR: line, exit 1, no separate output file -----


@pytest.mark.parametrize("content", _CONTENT_VALUES, ids=_CONTENT_IDS)
@pytest.mark.parametrize(
    ("surface", "mode"),
    _CLI_FAILURE_CASES,
    ids=[f"{s}-{m}" for s, m in _CLI_FAILURE_CASES],
)
def test_cli_declared_bad_registry_every_mode(
    surface: str,
    mode: str,
    content: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path = tmp_path / "bad.json"
    if content is not None:
        registry_path.write_text(content, encoding="utf-8")
    declare = Declare(**{mode: registry_path})

    result = SURFACES[surface](tmp_path, monkeypatch, declare)

    assert result == 1, f"{surface}/{mode} exited {result}"
    captured = capsys.readouterr()
    error_lines = [
        line for line in captured.err.splitlines() if line.startswith("ERROR:")
    ]
    assert len(error_lines) == 1, f"{surface}/{mode}: {captured.err}"
    assert "ID registry file " in error_lines[0]
    assert registry_path.name in error_lines[0]

    output_name = _CLI_OUTPUT_PATH.get(surface)
    if output_name is not None:
        assert not (tmp_path / output_name).exists(), f"{surface}/{mode}"


# --- Library/hook/loom-run surfaces: a ValueError, nothing produced -----


@pytest.mark.parametrize("content", _CONTENT_VALUES, ids=_CONTENT_IDS)
@pytest.mark.parametrize(
    ("surface", "mode"),
    _RAISING_FAILURE_CASES,
    ids=[f"{s}-{m}" for s, m in _RAISING_FAILURE_CASES],
)
def test_raising_surfaces_declared_bad_registry_every_mode(
    surface: str,
    mode: str,
    content: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry_path = tmp_path / "bad.json"
    if content is not None:
        registry_path.write_text(content, encoding="utf-8")
    declare = Declare(**{mode: registry_path})

    if surface in LIBRARY_RUNNERS_WITH_OUTPUT_PATH:
        # Registry resolution must fail before any output is written --
        # proves the ordering, not just that *something* raised (a
        # library runner that resolved the registry *after* generating
        # and writing output would still raise here, but too late).
        output_path = tmp_path / "lib-output.spdx3.json"
        with pytest.raises(ValueError, match=r"^ID registry file "):
            LIBRARY_RUNNERS_WITH_OUTPUT_PATH[surface](
                tmp_path, monkeypatch, declare, output_path=output_path
            )
        assert not output_path.exists(), f"{surface}/{mode}: output written"
        return

    if surface == "lib-embed_wheel_sbom":
        # Embeds into the wheel it's given rather than writing a
        # separate output file -- assert the wheel itself is untouched
        # instead (see LOW 1: embed_wheel_sbom() must resolve the
        # registry before it ever reads/rewrites the wheel).
        wheel = demo_wheel(tmp_path)
        before = wheel.read_bytes()
        with pytest.raises(ValueError, match=r"^ID registry file "):
            lib_embed_wheel_sbom(tmp_path, monkeypatch, declare, wheel=wheel)
        after = wheel.read_bytes()
        assert before == after, f"{surface}/{mode}: wheel was modified"
        return

    if surface == "hook":
        build_data: dict[str, object] = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match=r"^ID registry file "):
                run_hook(tmp_path, monkeypatch, declare, build_data=build_data)
        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) == 1, f"{surface}/{mode}: {caplog.records}"
        assert "sbom_files" not in build_data
        return

    with pytest.raises(ValueError, match=r"^ID registry file "):
        SURFACES[surface](tmp_path, monkeypatch, declare)


@pytest.mark.parametrize("surface", ["cli-id-generate", "cli-id-import"])
def test_id_command_malformed_declared_registry_is_one_error(
    surface: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unlike a *missing* declared file (created fresh -- not a failure,
    see the module docstring), a *malformed* one still fails: it exists,
    so ``IdRegistry.load`` is still the code path that runs."""
    registry_path = tmp_path / "bad.json"
    registry_path.write_text("{", encoding="utf-8")
    declare = Declare(flag=registry_path)

    result = SURFACES[surface](tmp_path, monkeypatch, declare)

    assert result == 1
    captured = capsys.readouterr()
    error_lines = [
        line for line in captured.err.splitlines() if line.startswith("ERROR:")
    ]
    assert len(error_lines) == 1, captured.err
    assert "ID registry file " in error_lines[0]


# --- Undeclared: IdRegistry.load is never called, on any surface -------


def test_undeclared_registry_never_loaded_across_every_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, load_spy: list[Path]
) -> None:
    # cwd is a SIBLING of the project directory, not its parent -- with
    # demo_project() writing to tmp_path / "proj", chdir-ing to tmp_path
    # itself would make cwd and the project's parent directory the same
    # spot, silently failing to catch a surface that mixes the two up.
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    project = demo_project(tmp_path)
    assert len({cwd, project, project.parent}) == 3, "cwd/project/parent must differ"
    candidates = [
        cwd / DEFAULT_ID_REGISTRY_FILENAME,
        project / DEFAULT_ID_REGISTRY_FILENAME,
        project.parent / DEFAULT_ID_REGISTRY_FILENAME,
    ]
    for candidate in candidates:
        IdRegistry.new("undeclared", path=candidate).save()
        assert candidate.is_file()  # vacuous-pass guard

    monkeypatch.chdir(cwd)
    surfaces = sorted(set(SURFACES) - _ID_COMMAND_SURFACES)
    for surface in surfaces:
        SURFACES[surface](tmp_path, monkeypatch, Declare())

    assert not load_spy, f"registry auto-loaded via: {load_spy}"
