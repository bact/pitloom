# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every shared option either reaches the library or warns -- exactly one.

The cells are read from the real ``argparse`` tree: every option of every
SBOM subcommand (those offering ``--config``) x every target kind that
subcommand takes x every value form of the option. A new flag is therefore
a new cell: it passes only once it has a value form and a reach check here,
or an entry in :data:`_OUTSIDE` saying why the invariant does not apply.

Each run replaces the library entry points with ``functools.wraps`` spies
that record their keyword arguments and the warnings logged so far, then
call the real function up to a stop point just past its own option
settling. Per cell, one of two outcomes must hold:

- *reached*: the value arrives at the entry point and nothing before the
  entry warned about it (the entry point may still warn once itself -- it
  is then the layer that dropped it, e.g. ``--id-registry`` for a Hugging
  Face model);
- *dropped*: the value does not arrive, and exactly one
  ``WARNING: Options:`` line named it before the entry point.

The expected outcome is never read from
:data:`pitloom.core.inert_options.INERT`: it comes from the user docs'
"Options with no effect" table (``docs/cli.md``). An option the docs list
for the target must warn exactly once, wherever it is dropped; any other
must warn zero times. So deleting a row in ``INERT``, dropping an option
silently inside an entry point, or warning about an option while still
forwarding it, fails here.

The last test runs a few commands end to end, with no spies, to count an
option crossing several layers (CLI, :func:`pitloom.assemble.generate`, the
delegate) or a multi-wheel batch: still one warning each.

See also: :mod:`tests.cli.test_cli_no_implicit_config` for ``--config``,
and :mod:`tests.test_build_flag_warnings` for the build flags, which sit
outside this matrix.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pitloom import __main__
from pitloom.assemble import (
    _model_generator,
    embed_wheel_sbom,
    enrich_model,
    generate_env_sbom,
    generate_model_sbom,
    generate_project_sbom,
    generate_wheel_sbom,
)
from pitloom.cli.parser import _build_parser
from pitloom.core.config_cascade import ConfigOverrides
from pitloom.core.creation import CreationMetadata
from pitloom.core.inert_options import PARAM_TO_FLAG
from pitloom.id_registry import IdRegistry
from tests.assemble.conftest import _make_dummy_wheel, _make_sdist
from tests.assemble.embed_surfaces_shared import demo_project, demo_wheel
from tests.cli.shared import SAFETENSORS_FIXTURE
from tests.core.test_inert_options import documented_rows
from tests.warning_helpers import (
    count_naming,
    logged_warnings,
    names_option,
    option_warning_spellings,
    stderr_warnings,
)

HF_URL = "https://huggingface.co/acme/demo-model"
_MARKER = "reach-marker"
_CREATOR = "Reach Creator"
_EMAIL = "reach@example.invalid"
_TOOL = "reach-tool"
_DATETIME = "2020-01-02T03:04:05Z"

#: Options outside the invariant, with the reason. Every other option of
#: every SBOM subcommand is a cell.
_OUTSIDE: dict[str, str] = {
    "--output": "where the SBOM goes, not how it is generated",
    "--verbose": "prints the resolved settings; changes no library call",
    "--embed": "wheel-only mode switch, not a shared generation option",
    "--project-dir": "selects the target itself (enrich, embed-wheel)",
    "--allow-build": "build flag: tests/test_build_flag_warnings.py",
    "--no-build-isolation": "build flag: tests/test_build_flag_warnings.py",
    "--build-timeout": "build flag: tests/test_build_flag_warnings.py",
    "--sbom": "selects embed-wheel's branch (a target kind here)",
    "--sbom-basename": "embed-wheel archive layout, not an SBOM setting",
    "--allow-mismatch": "embed-wheel --sbom safety valve, not a setting",
    "--verify": "post-embed check, runs after generation",
    "--validate": "post-embed check, runs after generation",
}

# Placeholders in a form's argv, filled per run.
_CONFIG = "<config>"
_REGISTRY = "<registry>"

#: Value for an option that is neither boolean, int nor a choice.
_VALUES: dict[str, tuple[str, ...]] = {
    "--config": (_CONFIG,),
    "--id-registry": (_REGISTRY,),
    "--creator-name": (_CREATOR,),
    "--creation-tool": (_TOOL,),
    "--creation-datetime": (_DATETIME,),
    "--creation-comment": (_MARKER,),
}
#: A creator attribute sets the most recent --creator-name's field.
_CREATOR_ATTRIBUTES = {"--creator-type": "agent", "--creator-email": _EMAIL}


def _creation(kwargs: dict[str, Any]) -> CreationMetadata | None:
    value = kwargs.get("creation_metadata")
    assert value is None or isinstance(value, CreationMetadata)
    return value


def _creators(kwargs: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    cm = _creation(kwargs)
    return [] if cm is None else [(c.name, c.type, c.email) for c in cm.creators]


#: Reach checks for options whose value is not passed under its own dest.
_REACH: dict[str, Callable[[dict[str, Any]], bool]] = {
    "--config": lambda kw: (
        getattr(kw.get("pitloom_config"), "sbom_basename", None) == _MARKER
    ),
    "--creator-name": lambda kw: (_CREATOR, "person", None) in _creators(kw),
    "--creator-type": lambda kw: (_CREATOR, "agent", None) in _creators(kw),
    "--creator-email": lambda kw: (_CREATOR, "person", _EMAIL) in _creators(kw),
    "--creation-tool": lambda kw: any(
        t.name == _TOOL for t in (getattr(_creation(kw), "tools", None) or [])
    ),
    "--no-creation-tool": lambda kw: getattr(_creation(kw), "tools", None) == [],
    "--creation-datetime": lambda kw: (
        getattr(_creation(kw), "creation_datetime", None) == _DATETIME
    ),
    "--creation-comment": lambda kw: (
        getattr(_creation(kw), "creation_comment", None) == _MARKER
    ),
}


class _Form(NamedTuple):
    option: str
    argv: tuple[str, ...]
    dest: str
    expected: object


def _key(action: argparse.Action) -> str:
    return next(s for s in action.option_strings if s.startswith("--"))


def _forms(action: argparse.Action) -> list[_Form]:
    """Every value form of *action*; raises for a shape with no form yet."""
    key = _key(action)
    if isinstance(action, argparse.BooleanOptionalAction):
        negative = f"--no-{key[2:]}"
        return [
            _Form(key, (key,), action.dest, True),
            _Form(negative, (negative,), action.dest, False),
        ]
    if action.nargs == 0:
        return [_Form(key, (key,), action.dest, True)]
    if action.type is int:
        return [_Form(key, (key, "0"), action.dest, 0)]
    if key in _CREATOR_ATTRIBUTES:
        value = _CREATOR_ATTRIBUTES[key]
        return [
            _Form(key, ("--creator-name", _CREATOR, key, value), action.dest, value)
        ]
    if action.choices is not None:
        choice = sorted(action.choices)[-1]
        return [_Form(key, (key, choice), action.dest, choice)]
    (value,) = _VALUES[key]
    return [_Form(key, (key, value), action.dest, value)]


def _sbom_parsers() -> dict[str, argparse.ArgumentParser]:
    """Subcommand name -> parser, for every subcommand offering --config."""
    # pylint: disable-next=protected-access
    actions = _build_parser()._actions
    # pylint: disable-next=protected-access
    (subparsers,) = [a for a in actions if isinstance(a, argparse._SubParsersAction)]
    return {
        name: parser
        for name, parser in subparsers.choices.items()
        # pylint: disable-next=protected-access
        if any("--config" in a.option_strings for a in parser._actions)
    }


def _options(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    # pylint: disable-next=protected-access
    return [a for a in parser._actions if a.option_strings and a.dest != "help"]


#: Target id -> (subcommand, argv after the subcommand name). ``{name}``
#: fields are filled per run by :func:`_paths`.
_TARGETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "generate:wheel": ("generate", ("{wheel}", "-o", "{out}")),
    "generate:env": ("generate", ("env", "-o", "{out}")),
    "generate:model_file": ("generate", ("{model}", "-o", "{out}")),
    "generate:hf": ("generate", (HF_URL, "-o", "{out}")),
    "generate:project": ("generate", ("{project}", "-o", "{out}")),
    "generate:sdist": ("generate", ("{sdist}", "-o", "{out}")),
    "project:project": ("project", ("{project}",)),
    "project:sdist": ("project", ("{sdist}",)),
    "wheel": ("wheel", ("{wheel}",)),
    "env": ("env", ()),
    "model:model_file": ("model", ("{model}",)),
    "model:hf": ("model", (HF_URL,)),
    "enrich": ("enrich", ("{model}",)),
    "embed-wheel:sbom": ("embed-wheel", ("{wheel}", "--sbom", "{sbom}")),
    "embed-wheel:project": ("embed-wheel", ("{wheel}", "--project-dir", "{project}")),
    "embed-wheel:standalone": ("embed-wheel", ("{wheel}",)),
}


#: Target id -> its row in the docs "Options with no effect" table.
_DOC_ROWS = {
    "generate:wheel": "wheel",
    "wheel": "wheel",
    "generate:env": "installed environment",
    "env": "installed environment",
    "generate:model_file": "local model file",
    "model:model_file": "local model file",
    "generate:hf": "Hugging Face model",
    "model:hf": "Hugging Face model",
    "generate:project": "project directory",
    "project:project": "project directory",
    "generate:sdist": "sdist archive",
    "project:sdist": "sdist archive",
    "enrich": "enrich without --project-dir",
    "embed-wheel:sbom": "embed-wheel --sbom",
    "embed-wheel:project": "embed-wheel --project-dir",
    "embed-wheel:standalone": "embed-wheel without --project-dir",
}


def _documented_no_effect(target: str, option: str) -> bool:
    """Whether the user docs say *option* has no effect for *target*. A
    table cell lists a flag's first spelling (``--creator-*`` for the
    creator/creation group); :data:`PARAM_TO_FLAG` gives its full one."""
    full = {spelling.split("/")[0]: spelling for spelling in PARAM_TO_FLAG.values()}
    return any(
        names_option(full.get(listed, listed), option)
        for listed in documented_rows()[_DOC_ROWS[target]]
    )


def _cells() -> list[Any]:
    parsers = _sbom_parsers()
    cells = []
    for target, (command, _argv) in _TARGETS.items():
        cells.append(pytest.param(target, None, id=f"{target}:none"))
        for action in _options(parsers[command]):
            if _key(action) in _OUTSIDE:
                continue
            for form in _forms(action):
                cells.append(pytest.param(target, form, id=f"{target}:{form.option}"))
    return cells


def _paths(tmp: Path) -> dict[str, str]:
    """Build every target file once; return the ``{name}`` fields."""
    model = tmp / "model.safetensors"
    shutil.copyfile(SAFETENSORS_FIXTURE, model)
    sbom = tmp / "external.spdx3.json"
    sbom.write_text("{}", encoding="utf-8")
    config = tmp / "reach-config.toml"
    config.write_text(f'[tool.pitloom]\nsbom-basename = "{_MARKER}"\n', "utf-8")
    # A declared registry must load (a missing/broken one is now an ERROR,
    # not a silent no-op) -- a real, empty, valid registry is enough for
    # this module's own purpose of checking the flag/kwarg reaches the
    # library, not that anything in it is looked up.
    registry_path = tmp / "reach-ids.json"
    IdRegistry.new("reach", path=registry_path).save()
    return {
        "wheel": str(demo_wheel(tmp)),
        "model": str(model),
        "project": str(demo_project(tmp)),
        "sdist": str(_make_sdist(tmp)),
        "sbom": str(sbom),
        "out": str(tmp / "out.spdx3.json"),
        _CONFIG: str(config),
        _REGISTRY: str(tmp / "reach-ids.json"),
    }


def _fill(arg: str, paths: dict[str, str]) -> str:
    """*arg* with its ``<placeholder>`` or ``{name}`` fields filled."""
    return paths[arg] if arg.startswith("<") else arg.format(**paths)


class _Stop(Exception):
    """Raised at a stop point: the entry point has settled its options."""


def _stop(*_args: object, **_kwargs: object) -> Any:
    raise _Stop


#: Called just after each entry point settles its own options.
_STOP_POINTS = (
    "pitloom.assemble._generators.apply_overrides",
    "pitloom.assemble._generators_wheel.read_wheel",
    "pitloom.assemble._generators_env.read_environment",
    "pitloom.assemble._model_generator.resolve_standalone_config",
    "pitloom._embed_generate.resolve_standalone_config",
    "pitloom._embed_generate.apply_overrides",
    "pitloom.embed._enforce_sbom_name_version",
)
_ENTRY_POINTS: dict[Callable[..., Any], tuple[str, ...]] = {
    generate_project_sbom: ("pitloom.assemble", "pitloom.cli.commands.project"),
    generate_wheel_sbom: ("pitloom.assemble", "pitloom.cli.commands.wheel"),
    generate_env_sbom: ("pitloom.assemble", "pitloom.cli.commands.env"),
    generate_model_sbom: ("pitloom.assemble", "pitloom.cli.commands.model"),
    enrich_model: ("pitloom.cli.commands.enrich",),
    embed_wheel_sbom: ("pitloom.cli.commands._embed_wheel_batch",),
}


class _Entry(NamedTuple):
    kwargs: dict[str, Any]
    warnings_before: list[str]


def _spy_entry_points(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> list[_Entry]:
    entries: list[_Entry] = []

    def _spy(real: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(real)
        def spy(*args: Any, **kwargs: Any) -> Any:
            entries.append(_Entry(dict(kwargs), logged_warnings(caplog)))
            try:
                return real(*args, **kwargs)
            except _Stop:
                if real is embed_wheel_sbom:
                    return (
                        Path(args[0]),
                        "x.dist-info/sboms/x.spdx3.json",
                        "{}",
                        (),
                        False,
                    )
                return "{}"

        return spy

    for real, modules in _ENTRY_POINTS.items():
        for module in modules:
            monkeypatch.setattr(f"{module}.{real.__name__}", _spy(real))
    for point in _STOP_POINTS:
        monkeypatch.setattr(point, _stop)
    return entries


def _received(kwargs: dict[str, Any], form: _Form, registry: str) -> bool:
    """Whether *form*'s value arrived in an entry point's *kwargs*;
    *registry* is the path the ``--id-registry`` placeholder stood for."""
    if form.option in _REACH:
        return _REACH[form.option](kwargs)
    overrides = kwargs.get("overrides")
    names = {f.name for f in dataclasses.fields(ConfigOverrides)}
    if isinstance(overrides, ConfigOverrides) and form.dest in names:
        value = getattr(overrides, form.dest)
    else:
        value = kwargs.get(form.dest)
    expected = form.expected
    if form.dest == "id_registry":
        if isinstance(value, IdRegistry):
            # embed-wheel resolves the registry once for the whole batch
            # (see _run_embed_wheel_command) and passes the already-loaded
            # IdRegistry down instead of the raw path.
            return value.path is not None and Path(value.path) == Path(registry)
        return value is not None and Path(value) == Path(registry)
    # Strict: 0 == False in Python, and either would pass a plain ==.
    return type(value) is type(expected) and value == expected


def _run(
    target: str,
    form: _Form | None,
    paths: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> list[_Entry]:
    command, argv = _TARGETS[target]
    extra = () if form is None else form.argv
    filled = [_fill(a, paths) for a in (*argv, *extra)]
    entries = _spy_entry_points(monkeypatch, caplog)
    monkeypatch.setattr(sys, "argv", ["loom", command, *filled])
    assert __main__.main() == 0
    return entries


@pytest.mark.parametrize(("target", "form"), _cells())
def test_option_reaches_library_xor_warns_once(
    target: str,
    form: _Form | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    paths = _paths(tmp_path)
    entries = _run(target, form, paths, monkeypatch, caplog)
    assert len(entries) == 1, "the run must reach exactly one library entry point"
    entry = entries[0]
    logged = logged_warnings(caplog)
    printed = stderr_warnings(capsys.readouterr().err)
    if form is None:
        # Nothing given: nothing may warn, resolved creation metadata included.
        assert option_warning_spellings(logged) == []
        assert option_warning_spellings(printed) == []
        return

    # Only the option given may be named, and the log and stderr agree.
    assert all(
        names_option(s, form.option) for s in option_warning_spellings(logged)
    ), logged
    assert count_naming(printed, form.option) == count_naming(logged, form.option)
    before = count_naming(entry.warnings_before, form.option)
    total = count_naming(logged, form.option)
    documented = _documented_no_effect(target, form.option)
    assert total == int(documented), (
        f"{form.option}: {total} warnings, docs say "
        f"{'no effect' if documented else 'effective'}: {logged}"
    )
    if _received(entry.kwargs, form, paths[_REGISTRY]):
        # The entry point may drop it itself; it is then the one warning.
        assert before == 0, f"{form.option} was warned about and still forwarded"
    else:
        assert (before, total) == (1, 1), (
            f"{form.option} was dropped with {total} warnings: {logged}"
        )


def test_matrix_accounts_for_every_option() -> None:
    """Every option of every SBOM subcommand is a cell or is declared
    outside the invariant with a reason; no declaration is stale; and
    every SBOM subcommand has at least one target."""
    parsers = _sbom_parsers()
    assert set(parsers) == {
        "generate",
        "project",
        "wheel",
        "embed-wheel",
        "model",
        "enrich",
        "env",
    }
    assert {command for command, _ in _TARGETS.values()} == set(parsers)
    seen: set[str] = set()
    for parser in parsers.values():
        for action in _options(parser):
            key = _key(action)
            seen.add(key)
            if key not in _OUTSIDE:
                assert _forms(action), key
    assert set(_OUTSIDE) <= seen, set(_OUTSIDE) - seen
    assert all(reason.strip() for reason in _OUTSIDE.values())
    assert set(_REACH) <= seen


# pylint: disable-next=too-few-public-methods
class _FakeExporter:
    def to_json(self, *, pretty: bool, describe_relationship: bool) -> str:
        del pretty, describe_relationship
        return "{}"


#: (argv with ``{name}`` fields, the option given, the option to count).
_ONCE_CASES = [
    pytest.param(
        ("generate", "{wheel}", "-o", "{out}", "--offline", "--content-type"),
        "--content-type",
        id="generate-wheel:cli+generate()",
    ),
    pytest.param(
        ("generate", "{wheel}", "-o", "{out}", "--offline", "--no-content-type"),
        "--no-content-type",
        id="generate-wheel:negative-form-counts-as-given",
    ),
    pytest.param(
        ("generate", "{model}", "-o", "{out}", "--offline"),
        "--offline",
        id="generate-model:delegate-settles",
    ),
    pytest.param(
        ("embed-wheel", "{wheel}", "{wheel2}", "--offline", "--pretty"),
        "--pretty",
        id="embed-wheel-batch:once-per-batch",
    ),
    pytest.param(
        ("embed-wheel", "{wheel}", "{wheel2}", "--offline", "--no-content-type"),
        "--no-content-type",
        id="embed-wheel-batch:no-project-dir",
    ),
    pytest.param(
        ("model", HF_URL, "--no-offline", "--id-registry", "<registry>"),
        "--id-registry",
        id="model-hf:dropped-inside-generate_model_sbom",
    ),
    pytest.param(
        ("enrich", "{model}", "--describe-relationship"),
        "--describe-relationship",
        id="enrich:cli",
    ),
]


@pytest.mark.parametrize(("argv", "option"), _ONCE_CASES)
def test_ignored_option_warns_exactly_once_end_to_end(
    argv: tuple[str, ...],
    option: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No spies: every layer runs for real, and the one ignored option is
    named once on the log and once on stderr, whichever layer drops it."""
    monkeypatch.chdir(tmp_path)
    paths = _paths(tmp_path)
    paths["wheel2"] = str(_make_dummy_wheel(tmp_path / "dist2", "other", "2.0.0"))
    # The Hugging Face fetch is the only network step; stand in for it.
    monkeypatch.setattr(_model_generator, "read_huggingface", lambda _s: object())
    monkeypatch.setattr(
        _model_generator, "build_model", lambda *_a, **_k: _FakeExporter()
    )
    filled = [_fill(a, paths) for a in argv]
    monkeypatch.setattr(sys, "argv", ["loom", *filled])

    assert __main__.main() == 0
    logged = logged_warnings(caplog)
    printed = stderr_warnings(capsys.readouterr().err)
    assert count_naming(logged, option) == 1, logged
    assert count_naming(printed, option) == 1, printed
    assert all(names_option(s, option) for s in option_warning_spellings(logged))
