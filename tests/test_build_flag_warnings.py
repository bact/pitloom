# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Cross-surface test matrix for the build flags
(``--allow-build``/``--no-build-isolation``/``--build-timeout``).

Dimensions: surface x target kind x every combination of the three flags.
Every surface x target cell runs unless :data:`_NOT_APPLICABLE` names it
with the reason it can't occur -- :func:`test_matrix_accounts_for_every_cell`
fails on a cell that is neither, so a new surface or target kind can't go
untested by omission. Each run checks both outcomes:

- exactly one ``WARNING: Build: ...`` per explicitly given but ineffective
  flag -- never zero, never two -- carrying the right reason; and
- the build settings that actually reach file discovery (none unless
  ``--allow-build`` and the target reaches discovery; default timeout
  1200 s).

Surfaces outside this matrix: the Hatchling build hook takes no build
options (:func:`test_hatchling_hook_is_silent` below); the GitHub Action
maps its inputs to CLI flags (``test_build_input_matrix`` in
``tests/scripts/action/test_generate_step.py``).

See also: :mod:`tests.core.test_build_options` for the unit tests of the
shared mechanism, :mod:`tests.cli.test_cli_build_timeout` for
``--build-timeout`` parsing, :mod:`tests.test_build_flag_warning_ordering`
for warning order.
"""

from __future__ import annotations

import itertools
import json
import logging
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom import __main__
from pitloom.assemble import generate, generate_project_sbom
from pitloom.core._models_wheel_dispatch import _discover_included_files
from pitloom.core._models_wheel_types import BuildSettings
from pitloom.core.build_options import BuildOptions
from pitloom.core.models import get_wheel_files
from pitloom.embed import ConfigOverrides, EmbedFileCache, embed_wheel_sbom
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.extract.conftest import make_hook, write_pyproject

_FLAGS = ("--allow-build", "--no-build-isolation", "--build-timeout")
_STRAY = "without --allow-build"
_NOT_PROJECT = "for this target (no build-backend file discovery"
_SDIST = "for an sdist archive target"
_EXT_SBOM = "for an externally-supplied --sbom"
_NO_PROJECT = "with no project directory to rescan"
_HF_URL = "https://huggingface.co/acme/demo-model"
# Spec'd default, not read from the source, so a changed default fails here.
_DEFAULT_TIMEOUT = 1200


def _combo_name(options: BuildOptions) -> str:
    parts = [
        name
        for name, given in (
            ("allow", options.allow),
            ("no-isolation", options.no_isolation),
            ("timeout", options.timeout is not None),
        )
        if given
    ]
    return "+".join(parts) or "none"


# Every combination of the three flags (2 x 2 x 2).
_COMBOS = {
    _combo_name(options): options
    for options in (
        BuildOptions(allow=allow, no_isolation=no_isolation, timeout=timeout)
        for allow, no_isolation, timeout in itertools.product(
            (False, True), (False, True), (None, 900)
        )
    )
}

# Target kind -> the "has no effect" reason every given flag gets, or None
# when the target reaches file discovery (only a flag given without
# --allow-build is then warned about). "_multi": two wheels in one run.
_KIND_REASONS: dict[str, str | None] = {
    "project_dir": None,
    "project_dir_default": None,
    "sdist": _SDIST,
    "wheel": _NOT_PROJECT,
    "env": _NOT_PROJECT,
    "model_file": _NOT_PROJECT,
    "hf": _NOT_PROJECT,
    "embed_project_dir": None,
    "embed_cwd_project": None,
    "embed_sbom": _EXT_SBOM,
    "embed_no_project": _NO_PROJECT,
    "embed_project_dir_multi": None,
    "embed_cwd_project_multi": None,
    "embed_sbom_multi": _EXT_SBOM,
    "embed_no_project_multi": _NO_PROJECT,
}
_EMBED_KINDS = tuple(kind for kind in _KIND_REASONS if kind.startswith("embed_"))
_GENERATE_KINDS = tuple(kind for kind in _KIND_REASONS if kind not in _EMBED_KINDS)
_NOT_PROJECT_KINDS = ("wheel", "env", "model_file", "hf")


class _Env(NamedTuple):
    """Per-test fixture paths shared by every runner."""

    tmp: Path
    project: Path
    wheel: Path
    output: Path


def _make_env(tmp_path: Path) -> _Env:
    project = tmp_path / "proj"
    (project / "demo").mkdir(parents=True)
    (project / "demo" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling"]\n'
        'build-backend = "hatchling.build"\n\n'
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    wheel = _make_dummy_wheel(tmp_path / "dist", "demo", "1.0.0")
    return _Env(tmp_path, project, wheel, tmp_path / "out.spdx3.json")


def _argv_flags(options: BuildOptions) -> list[str]:
    flags = ["--allow-build"] if options.allow else []
    if options.no_isolation:
        flags.append("--no-build-isolation")
    if options.timeout is not None:
        flags += ["--build-timeout", str(options.timeout)]
    return flags


def _external_sbom(env: _Env) -> Path:
    path = env.tmp / "external.spdx3.json"
    path.write_text(
        json.dumps({"@context": "https://spdx.org/rdf/3.0.1/spdx-context.jsonld"}),
        encoding="utf-8",
    )
    return path


def _target(env: _Env, kind: str) -> str:
    """The target argument for a generate-style *kind*."""
    if kind in ("project_dir", "project_dir_default"):
        return str(env.project)
    if kind == "sdist":
        return str(_make_sdist(env.tmp))
    if kind == "wheel":
        return str(env.wheel)
    if kind == "env":
        return "env"
    if kind == "model_file":
        model = env.tmp / "model.gguf"
        model.write_bytes(b"")
        return str(model)
    if kind == "hf":
        return _HF_URL
    raise AssertionError(f"no runner support for target kind {kind!r}")


def _run_cli(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["loom", *argv])
    assert __main__.main() == 0


def _cli_target_argv(env: _Env, kind: str, mp: pytest.MonkeyPatch) -> list[str]:
    """No target argument for ``project_dir_default``: the CLI's own
    default (``.``) then resolves to the project, via cwd."""
    if kind == "project_dir_default":
        mp.chdir(env.project)
        return []
    return [_target(env, kind)]


def _cli_project(
    env: _Env, kind: str, options: BuildOptions, mp: pytest.MonkeyPatch
) -> None:
    argv = ["project", *_cli_target_argv(env, kind, mp), "-o", str(env.output)]
    _run_cli(argv + _argv_flags(options), mp)


def _cli_generate(
    env: _Env, kind: str, options: BuildOptions, mp: pytest.MonkeyPatch
) -> None:
    argv = ["generate", *_cli_target_argv(env, kind, mp), "-o", str(env.output)]
    _run_cli(argv + _argv_flags(options), mp)


def _cli_embed_wheel(
    env: _Env, kind: str, options: BuildOptions, mp: pytest.MonkeyPatch
) -> None:
    argv = ["embed-wheel", str(env.wheel)]
    if kind.endswith("_multi"):
        argv.append(str(_make_dummy_wheel(env.tmp / "dist2", "demo", "1.0.0")))
        kind = kind.removesuffix("_multi")
    if kind == "embed_project_dir":
        argv += ["--project-dir", str(env.project)]
    elif kind == "embed_sbom":
        argv += ["--sbom", str(_external_sbom(env))]
    elif kind == "embed_cwd_project":
        # No --project-dir: the CLI falls back to the current directory.
        mp.chdir(env.project)
    elif kind == "embed_no_project":
        # No --project-dir, and the current directory has no pyproject.toml.
        mp.chdir(env.tmp)
    else:
        raise AssertionError(f"no runner support for target kind {kind!r}")
    _run_cli(argv + _argv_flags(options), mp)


def _lib_generate(
    env: _Env, kind: str, options: BuildOptions, mp: pytest.MonkeyPatch
) -> None:
    if kind == "project_dir_default":
        mp.chdir(env.project)
        generate(offline=True, build_options=options)
        return
    generate(_target(env, kind), offline=True, build_options=options)


def _lib_generate_project_sbom(
    env: _Env, kind: str, options: BuildOptions, _mp: pytest.MonkeyPatch
) -> None:
    generate_project_sbom(_target(env, kind), offline=True, build_options=options)


def _lib_embed_wheel_sbom(
    env: _Env, kind: str, options: BuildOptions, _mp: pytest.MonkeyPatch
) -> None:
    """A ``_multi`` kind embeds two wheels sharing one public
    :class:`EmbedFileCache` batch."""
    wheels = [env.wheel]
    if kind.endswith("_multi"):
        wheels.append(_make_dummy_wheel(env.tmp / "dist2", "demo", "1.0.0"))
        kind = kind.removesuffix("_multi")
    kwargs: dict[str, Any] = {}
    if kind == "embed_project_dir":
        kwargs["project_dir"] = env.project
    elif kind == "embed_sbom":
        kwargs["sbom_path"] = _external_sbom(env)
    elif kind != "embed_no_project":
        raise AssertionError(f"no runner support for target kind {kind!r}")
    overrides = ConfigOverrides(build_options=options)
    with EmbedFileCache() as file_cache:
        for wheel in wheels:
            embed_wheel_sbom(
                wheel, overrides=overrides, file_cache=file_cache, **kwargs
            )


def _lib_get_wheel_files(
    env: _Env, kind: str, options: BuildOptions, _mp: pytest.MonkeyPatch
) -> None:
    if kind != "project_dir":
        raise AssertionError(f"no runner support for target kind {kind!r}")
    _, _, cleanup = get_wheel_files(env.project, build_options=options)
    cleanup()


_Runner = Callable[[_Env, str, BuildOptions, pytest.MonkeyPatch], None]

_RUNNERS: dict[str, _Runner] = {
    "cli-project": _cli_project,
    "cli-generate": _cli_generate,
    "cli-embed-wheel": _cli_embed_wheel,
    "lib-generate": _lib_generate,
    "lib-generate_project_sbom": _lib_generate_project_sbom,
    "lib-embed_wheel_sbom": _lib_embed_wheel_sbom,
    "lib-get_wheel_files": _lib_get_wheel_files,
}
_EMBED_SURFACES = ("cli-embed-wheel", "lib-embed_wheel_sbom")

# (surface, target kind) -> why that cell can't occur. Every other cell runs.
_NOT_APPLICABLE: dict[tuple[str, str], str] = {
    **{
        (surface, kind): "takes no wheel to embed into"
        for surface in _RUNNERS
        if surface not in _EMBED_SURFACES
        for kind in _EMBED_KINDS
    },
    **{
        (surface, kind): "embeds into a wheel; its project source is an embed_* kind"
        for surface in _EMBED_SURFACES
        for kind in _GENERATE_KINDS
    },
    **{
        (surface, kind): "accepts a project directory or sdist only"
        for surface in ("cli-project", "lib-generate_project_sbom")
        for kind in _NOT_PROJECT_KINDS
    },
    ("lib-generate_project_sbom", "project_dir_default"): "target is required",
    **{
        ("lib-get_wheel_files", kind): "takes a project directory only"
        for kind in _GENERATE_KINDS
        if kind != "project_dir"
    },
    **{
        ("lib-embed_wheel_sbom", kind): (
            "no cwd fallback: project_dir=None is embed_no_project"
        )
        for kind in ("embed_cwd_project", "embed_cwd_project_multi")
    },
}

_CASES = [
    (surface, kind)
    for surface in _RUNNERS
    for kind in _KIND_REASONS
    if (surface, kind) not in _NOT_APPLICABLE
]


def _expected_warnings(options: BuildOptions, reason: str | None) -> dict[str, str]:
    """Flag -> the reason its one warning must carry."""
    if reason is not None:
        return dict.fromkeys(options.given, reason)
    if options.allow:
        return {}
    return dict.fromkeys(options.given, _STRAY)


def _expected_settings(
    options: BuildOptions, reason: str | None
) -> BuildSettings | None:
    """The build settings file discovery must receive."""
    if reason is not None or not options.allow:
        return None
    timeout = _DEFAULT_TIMEOUT if options.timeout is None else options.timeout
    return BuildSettings(isolated=not options.no_isolation, timeout=timeout)


def _stub_heavy_paths(mp: pytest.MonkeyPatch) -> tuple[list[object], list[object]]:
    """Stub the env/model/HF generators (slow or networked), record any
    real PEP 517 build attempt (no case here may trigger one), and record
    the build settings each file-discovery call receives."""
    for name in ("generate_env_sbom", "generate_model_sbom"):
        mp.setattr(f"pitloom.assemble.{name}", lambda *_a, **_k: "{}")
    builds: list[object] = []

    def _no_build(*args: object, **_kwargs: object) -> None:
        builds.append(args)

    mp.setattr(
        "pitloom.core._models_wheel_build_and_read.build_and_read_wheel", _no_build
    )

    discovery_settings: list[object] = []

    def _spy_discover(*args: Any, **kwargs: Any) -> Any:
        discovery_settings.append(kwargs.get("build"))
        return _discover_included_files(*args, **kwargs)

    mp.setattr("pitloom.core._models_wheel._discover_included_files", _spy_discover)
    return builds, discovery_settings


@pytest.mark.parametrize("combo", list(_COMBOS))
@pytest.mark.parametrize(
    ("surface", "kind"), _CASES, ids=[f"{surface}:{kind}" for surface, kind in _CASES]
)
# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def test_build_flags_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    surface: str,
    kind: str,
    combo: str,
) -> None:
    options = _COMBOS[combo]
    reason = _KIND_REASONS[kind]
    env = _make_env(tmp_path)
    builds, discovery_settings = _stub_heavy_paths(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="pitloom"):
        _RUNNERS[surface](env, kind, options, monkeypatch)

    assert not builds
    if reason is None:
        # Once per run, a multi-wheel batch included (EmbedFileCache).
        assert discovery_settings == [_expected_settings(options, reason)]
    else:
        assert not discovery_settings

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    expected = _expected_warnings(options, reason)
    for flag in _FLAGS:
        lines = [m for m in messages if f"{flag} has no effect" in m]
        if flag not in expected:
            assert lines == []
            continue
        assert len(lines) == 1, lines
        assert lines[0].startswith("Build: ")
        assert expected[flag] in lines[0]

    if surface.startswith("cli-"):
        stderr = capsys.readouterr().err.splitlines()
        for flag in expected:
            lines = [line for line in stderr if f"{flag} has no effect" in line]
            assert len(lines) == 1, lines
            assert lines[0].startswith("WARNING: Build: ")


def test_matrix_accounts_for_every_cell() -> None:
    """Every surface x target cell either runs or is listed as not
    applicable with a reason -- never silently absent -- and every
    surface and every kind runs at least once."""
    cells = set(itertools.product(_RUNNERS, _KIND_REASONS))
    assert set(_NOT_APPLICABLE) <= cells
    assert set(_CASES) | set(_NOT_APPLICABLE) == cells
    assert not set(_CASES) & set(_NOT_APPLICABLE)
    assert all(reason.strip() for reason in _NOT_APPLICABLE.values())
    assert {surface for surface, _ in _CASES} == set(_RUNNERS)
    assert {kind for _, kind in _CASES} == set(_KIND_REASONS)
    assert len(_COMBOS) == 8


def test_hatchling_hook_is_silent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The Hatchling build hook reaches ``get_wheel_files()`` with no build
    options: it must never log a build-flag warning."""
    calls: list[dict[str, Any]] = []

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return get_wheel_files(*args, **kwargs)

    monkeypatch.setattr("pitloom.plugins.hatch.get_wheel_files", _spy)
    with tempfile.TemporaryDirectory() as tmp:
        write_pyproject(Path(tmp))
        hook = make_hook(tmp, {})
        build_data: dict[str, Any] = {}
        with caplog.at_level(logging.WARNING, logger="pitloom"):
            hook.initialize("standard", build_data)
        hook.finalize("standard", build_data, "")

    assert len(calls) == 1
    assert "build_options" not in calls[0]
    assert not [r for r in caplog.records if "has no effect" in r.getMessage()]
