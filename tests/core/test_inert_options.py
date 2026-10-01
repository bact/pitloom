# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.core.inert_options`: the table itself, and the
user-facing copy of it in ``docs/cli.md``.

See also: :mod:`tests.cli.test_cli_option_reach` (every CLI option reaches
the library or warns, end to end).
"""

from __future__ import annotations

import argparse
import inspect
import re
from pathlib import Path

import pytest

from pitloom import _embed_generate, assemble
from pitloom.cli.options_config import run_options
from pitloom.cli.parser import _build_parser
from pitloom.core import inert_options
from pitloom.core._config_types import AssembleOptions
from pitloom.core.config import PitloomConfig
from pitloom.core.inert_options import (
    INERT,
    PARAM_TO_FLAG,
    forward_options,
    settle_inert,
)
from tests.warning_helpers import count_naming, logged_warnings

_CLI_DOC = Path(__file__).resolve().parents[2] / "docs" / "cli.md"
_SECTION = "### Options with no effect"

#: docs/cli.md row label -> target kind.
_ROW_KINDS = {
    "project directory": inert_options.PROJECT,
    "sdist archive": inert_options.SDIST,
    "wheel": inert_options.WHEEL,
    "installed environment": inert_options.ENV,
    "local model file": inert_options.MODEL_FILE,
    "Hugging Face model": inert_options.HF,
    "enrich --project-dir": inert_options.ENRICH,
    "enrich without --project-dir": inert_options.ENRICH_STANDALONE,
    "embed-wheel --project-dir": inert_options.EMBED_PROJECT,
    "embed-wheel without --project-dir": inert_options.EMBED_STANDALONE,
    "embed-wheel --sbom": inert_options.EMBED_SBOM,
    # The same embedded SBOM, and warnings, as embed-wheel without a project.
    "wheel --embed": inert_options.EMBED_STANDALONE,
}


def documented_rows() -> dict[str, list[str]]:
    """``docs/cli.md``'s "Options with no effect" table: row label -> the
    options it lists, in order."""
    text = _CLI_DOC.read_text(encoding="utf-8")
    section = text[text.index(_SECTION) :]
    rows: dict[str, list[str]] = {}
    for line in section.splitlines()[1:]:
        if line.startswith("#"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("Target", "") or set(cells[0]) <= {"-"}:
            continue
        rows[cells[0].strip("`")] = re.findall(r"`([^`]+)`", cells[1])
    return rows


def test_docs_table_matches_inert() -> None:
    """The user docs list exactly the options each target warns about, in
    flag-table order (the order one settle warns in) -- a row added to
    INERT without the docs (or the reverse) fails here."""
    documented = documented_rows()
    assert set(documented) == set(_ROW_KINDS)
    for label, kind in _ROW_KINDS.items():
        expected = [
            spelling.split("/", maxsplit=1)[0]
            for param, spelling in PARAM_TO_FLAG.items()
            if param in INERT[kind]
        ]
        assert documented[label] == expected, label


def test_every_kind_has_a_docs_row() -> None:
    kinds = {
        value
        for name, value in vars(inert_options).items()
        if name.isupper() and isinstance(value, str) and value in INERT
    }
    assert kinds == set(INERT) == set(_ROW_KINDS.values())


def _subcommand(name: str) -> argparse.ArgumentParser:
    """The real parser of subcommand *name*."""
    parser = _build_parser()
    # pylint: disable-next=protected-access
    for action in parser._actions:
        # pylint: disable-next=protected-access
        if isinstance(action, argparse._SubParsersAction):
            parser_: argparse.ArgumentParser = action.choices[name]
            return parser_
    raise LookupError(name)


def test_every_warned_flag_exists_on_the_cli() -> None:
    """A warning names a real option of the command that can give it; a
    glob names at least one. Shared options live on every SBOM command;
    ``--project-dir`` only on ``embed-wheel`` (and ``enrich``)."""
    commands = {"project": "shared", "embed-wheel": "project_dir"}
    options = {
        name: {
            option
            # pylint: disable-next=protected-access
            for action in _subcommand(command)._actions
            for option in action.option_strings
        }
        for command, name in commands.items()
    }
    for param, spelling in PARAM_TO_FLAG.items():
        offered = options["project_dir" if param == "project_dir" else "shared"]
        for part in spelling.split("/"):
            pattern = re.compile(re.escape(part).replace(r"\*", ".*") + "$")
            assert any(pattern.match(option) for option in offered), part


def test_every_inert_param_has_a_flag_spelling() -> None:
    for row in INERT.values():
        assert set(row) <= set(PARAM_TO_FLAG)


@pytest.mark.parametrize("value", [False, 0, ""])
def test_a_falsy_given_value_still_warns(
    caplog: pytest.LogCaptureFixture, value: object
) -> None:
    """``None`` alone means "not given"; ``False``/``0`` are choices."""
    with caplog.at_level("WARNING"):
        dropped = settle_inert(inert_options.WHEEL, "w", {"enrich": value})
    assert dropped == {"enrich"}
    assert len(caplog.records) == 1


def test_none_is_not_given(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert settle_inert(inert_options.WHEEL, "w", {"enrich": None}) == set()
    assert not caplog.records


# --- forward_options: the contract every layer relies on -------------------


def _callee(*, pretty: bool | None = None) -> bool | None:
    """A delegate that accepts only ``pretty``."""
    return pretty


def test_forward_raises_for_an_undeclared_dropped_option() -> None:
    """A given option the callee cannot take and INERT does not declare
    would vanish without a word: a wiring bug, so it fails loudly."""
    with pytest.raises(ValueError, match="does not declare") as info:
        forward_options(inert_options.PROJECT, "p", _callee, {"offline": True})
    assert "_callee" in str(info.value) and "offline" in str(info.value)


def test_forward_drops_an_undeclared_option_left_unset(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``None`` was not given, so dropping it deviates from nothing."""
    with caplog.at_level("WARNING"):
        forwarded = forward_options(
            inert_options.PROJECT, "p", _callee, {"offline": None, "pretty": True}
        )
    assert forwarded == {"pretty": True}
    assert not caplog.records


def test_forward_leaves_an_accepted_inert_option_to_the_callee(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The deepest layer that drops an option warns; one the callee accepts
    is forwarded unwarned, even when the kind lists it as inert."""
    assert "pretty" in INERT[inert_options.EMBED_STANDALONE]
    with caplog.at_level("WARNING"):
        forwarded = forward_options(
            inert_options.EMBED_STANDALONE, "e", _callee, {"pretty": True}
        )
    assert forwarded == {"pretty": True}
    assert not caplog.records


def test_forward_settles_a_declared_dropped_option_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        forwarded = forward_options(
            inert_options.WHEEL, "w", _callee, {"enrich": False, "pretty": None}
        )
    assert forwarded == {"pretty": None}
    assert count_naming(logged_warnings(caplog), "--enrich") == 1


def test_forward_passes_everything_to_a_var_keyword_callee(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ``**kwargs`` callee's signature says nothing about what it drops,
    so nothing is settled here -- the callee owns it."""

    def open_callee(**kwargs: object) -> dict[str, object]:
        """Accepts anything."""
        return kwargs

    options = {"enrich": True, "offline": True, "pretty": None}
    with caplog.at_level("WARNING"):
        forwarded = forward_options(inert_options.WHEEL, "w", open_callee, options)
    assert forwarded == options and forwarded is not options
    assert not caplog.records


# --- settle_inert: adversarial inputs ---------------------------------------


def test_settle_rejects_an_unknown_kind() -> None:
    with pytest.raises(KeyError):
        settle_inert("no-such-kind", "x", {"enrich": True})


def test_settle_ignores_a_given_option_the_kind_can_use(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        dropped = settle_inert(inert_options.WHEEL, "w", {"pretty": True})
    assert dropped == set()
    assert not caplog.records


def test_settle_warning_order_does_not_follow_the_mapping_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Same warnings, same order, whatever order the caller built its dict
    in -- so stderr is deterministic across callers."""
    params = list(INERT[inert_options.EMBED_SBOM])
    runs = []
    for order in (params, params[::-1]):
        caplog.clear()
        with caplog.at_level("WARNING"):
            settle_inert(inert_options.EMBED_SBOM, "s", dict.fromkeys(order, 1))
        runs.append(logged_warnings(caplog))
    assert runs[0] == runs[1]
    assert len(runs[0]) == len(params) > 1
    expected = [flag for param, flag in PARAM_TO_FLAG.items() if param in params]
    assert [w.split(": ")[2].split(" has no effect")[0] for w in runs[0]] == expected


# --- wiring drift: every real (kind, callee) pairing -------------------------

#: Every ``forward_options(kind, ..., callee, ...)`` pairing in ``src/``.
_PAIRINGS = [
    (inert_options.ENV, "generate_env_sbom"),
    (inert_options.WHEEL, "generate_wheel_sbom"),
    (inert_options.HF, "generate_model_sbom"),
    (inert_options.MODEL_FILE, "generate_model_sbom"),
    (inert_options.ENRICH, "enrich_model"),
]
_NOT_OPTIONS = {"target", "project_target", "build_options"}


def _generate_options() -> list[str]:
    """Every option ``generate()`` hands its delegates."""
    return [
        name
        for name in inspect.signature(assemble.generate).parameters
        if name not in _NOT_OPTIONS
    ]


def test_every_forward_call_site_is_listed() -> None:
    """A new ``forward_options()`` pairing in ``src/`` must join
    :data:`_PAIRINGS`, so the test below checks its wiring too."""
    src = Path(assemble.__file__).resolve().parents[1]
    calls = [
        match
        for path in sorted(src.rglob("*.py"))
        for match in re.findall(
            r"forward_options\(\s*(\w+),\s*[^,]+,\s*(\w+),",
            path.read_text(encoding="utf-8"),
        )
    ]
    assert len(calls) >= 8  # non-vacuous: the scan finds the real calls
    listed_callees = {callee for _, callee in _PAIRINGS}
    assert {callee for _, _, callee in _CALLERS} == listed_callees
    for kind, callee in calls:
        if kind.isupper():
            assert (getattr(inert_options, kind), callee) in _PAIRINGS, (kind, callee)
        else:  # a kind chosen at run time (model: HF or MODEL_FILE)
            assert callee in listed_callees, callee


def _cli_options(argv: list[str]) -> list[str]:
    """Every shared option the subcommand in *argv* offers (``run_options()``
    reads a flag the command lacks as ``None``, i.e. not given)."""
    namespace = _build_parser().parse_args(argv)
    return [
        name
        for name in run_options(namespace, PitloomConfig())
        if name == "creation_metadata" or hasattr(namespace, name)
    ]


#: Each real caller of ``forward_options()``: the options it can give, with
#: the kind and delegate it settles them against.
_CALLERS = [
    *(("generate()", kind, callee) for kind, callee in _PAIRINGS[:4]),
    ("loom wheel", inert_options.WHEEL, "generate_wheel_sbom"),
    ("loom env", inert_options.ENV, "generate_env_sbom"),
    ("loom model", inert_options.MODEL_FILE, "generate_model_sbom"),
    ("loom model", inert_options.HF, "generate_model_sbom"),
    ("loom enrich", inert_options.ENRICH, "enrich_model"),
]


def _caller_options(caller: str) -> list[str]:
    if caller == "generate()":
        return _generate_options()
    command = caller.split()[1]
    targets = {"wheel": ["x.whl"], "env": [], "model": ["m.onnx"], "enrich": ["m.onnx"]}
    return _cli_options([command, *targets[command]])


@pytest.mark.parametrize(
    ("caller", "kind", "callee_name"),
    _CALLERS,
    ids=[f"{caller}-{kind}" for caller, kind, _ in _CALLERS],
)
def test_every_option_reaches_or_is_declared_inert(
    caller: str, kind: str, callee_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Every option a real caller can give, all given at once, is either
    accepted by the delegate or declared inert for its kind -- never the
    wiring-bug ``ValueError`` -- and each inert one warns exactly once."""
    callee = getattr(assemble, callee_name)
    options = dict.fromkeys(_caller_options(caller), object())
    assert len(options) > 5  # non-vacuous
    with caplog.at_level("WARNING"):
        forwarded = forward_options(kind, "t", callee, options)
    accepted = set(inspect.signature(callee).parameters)
    assert set(forwarded) == set(options) & accepted
    warned = logged_warnings(caplog)
    assert len(warned) == len(set(options) - accepted)
    for param in set(options) - accepted:
        assert count_naming(warned, PARAM_TO_FLAG[param].split("/")[0]) == 1, param


def test_generate_options_cover_every_cli_option() -> None:
    """``loom generate`` passes every shared CLI option to ``generate()``,
    and ``generate()`` hands a project target all of them unfiltered."""
    cli_options = set(_cli_options(["generate", "."]))
    assert cli_options <= set(_generate_options())
    project_params = set(inspect.signature(assemble.generate_project_sbom).parameters)
    assert set(_generate_options()) <= project_params


#: Options a delegate accepts and settles itself (warning through
#: ``settle_inert`` before it acts), so they are declared for the kind
#: without being stale. Every other accepted option must not be declared.
_SETTLES_ITSELF = {"generate_model_sbom": {"offline", "enrich", "id_registry"}}


@pytest.mark.parametrize(
    ("kind", "callee_name"), _PAIRINGS, ids=[f"{k}-{c}" for k, c in _PAIRINGS]
)
def test_no_option_is_both_declared_inert_and_accepted(
    kind: str, callee_name: str
) -> None:
    """A row for an option its delegate accepts is stale (the parameter was
    added and the row kept): the delegate would act on the option while
    the caller warns it has no effect."""
    accepted = set(inspect.signature(getattr(assemble, callee_name)).parameters)
    settled = _SETTLES_ITSELF.get(callee_name, set())
    assert settled <= accepted  # non-vacuous: the exclusion names real parameters
    assert not (set(inert_options.INERT[kind]) & accepted) - settled


def test_the_standalone_embed_builder_reads_no_declared_inert_option() -> None:
    """``embed_wheel_sbom(overrides=...)`` accepts every override and settles
    the inert ones away; what the builder then reads from the resolved config
    must not be a declared one."""
    source = inspect.getsource(_embed_generate._build_sbom_standalone_wheel)
    read = set(re.findall(r"\bcfg\.(\w+)", source))
    read |= set(AssembleOptions.__annotations__)  # cfg.assemble_options
    assert {"scan_model_usage", "max_model_extract_bytes"} <= read  # non-vacuous
    assert not read & set(inert_options.INERT[inert_options.EMBED_STANDALONE])


def test_trust_wheel_model_with_a_project_dir_says_why() -> None:
    """``embed-wheel --project-dir`` reads its models from the project; the
    reason must not claim the target reads no wheel."""
    reason = INERT[inert_options.EMBED_PROJECT]["trust_wheel_model"]
    assert "--project-dir" in reason
    assert "not the wheel" in reason
