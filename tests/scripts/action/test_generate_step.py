# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the "Generate SBOM" step of ``action.yml`` against a stub ``loom``.

The step's ``run:`` script is extracted from ``action.yml`` and run under
bash with ``PATH`` limited to stubs (POSIX only), so the tests cover the
argument handling, output/annotation capture and exit-code propagation
without installing Pitloom.

See also: :mod:`tests.scripts.action.test_generate_step_id_registry`
(the ``id-registry``/``update-id-registry`` input tests, split out to
keep this file under this repo's file-size guidance) -- both share the
``generate`` fixture and wheel-building helpers from
:mod:`tests.scripts.action._generate_step_shared`.
"""

import itertools
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.scripts.action._generate_step_shared import (
    EMBED_STDOUT,
    _make_wheel,
    _Result,
)

# Re-exported (not just imported for its side effect of registering with
# pytest): pytest discovers a fixture by the module attribute carrying
# it, so this module needs its own reference to the shared "generate"
# fixture, not just test_generate_step_id_registry.py's.
from tests.scripts.action._generate_step_shared import (  # noqa: F401
    generate_fixture as generate_fixture,
)

if TYPE_CHECKING:
    from tests.scripts.action.conftest import StubBin


def test_project_mode_reports_the_printed_sbom_path(
    generate: Callable[..., _Result],
) -> None:
    result = generate()
    assert result.returncode == 0
    assert result.sbom_path == "out/sbom.spdx3.json"
    assert result.loom_args == ["project", "."]


@pytest.mark.parametrize(
    "value",
    ["30", "1h30m", "not-a-duration"],
    ids=["seconds", "unit-form", "invalid-passed-verbatim"],
)
def test_build_timeout_is_passed_through_verbatim(
    generate: Callable[..., _Result], value: str
) -> None:
    """The action script never parses/validates PL_BUILD_TIMEOUT itself
    (single-parser rule: pitloom.core._models_wheel_types.parse_build_timeout
    is the only duration parser) -- every value, including an invalid
    one, is passed straight through as an argv token for "loom" itself
    to accept or reject."""
    result = generate(PL_BUILD_TIMEOUT=value)
    assert result.loom_args == ["project", ".", "--build-timeout", value]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ("true", ["--scan-model-usage"]),
        ("false", ["--no-scan-model-usage"]),
        ("yes", []),
    ],
)
def test_scan_model_usage_input_is_tri_state(
    generate: Callable[..., _Result], value: str, expected: list[str]
) -> None:
    """Only ``true``/``false`` become a flag; empty defers to the config."""
    result = generate(PL_SCAN_MODEL_USAGE=value)
    assert result.loom_args == ["project", ".", *expected]


@pytest.mark.parametrize(
    ("mode", "env", "head"),
    [
        ("project", {}, ["project", "."]),
        ("model", {"PL_MODEL": "m.safetensors"}, ["model", "m.safetensors"]),
    ],
)
def test_config_is_passed_on_every_mode(
    generate: Callable[..., _Result], mode: str, env: dict[str, str], head: list[str]
) -> None:
    """``config`` becomes ``--config FILE`` whatever the mode, verbatim (a
    path with a space stays one argument); empty passes nothing."""
    del mode
    assert "--config" not in generate(**env).loom_args
    result = generate(PL_CONFIG="ci dir/pitloom.toml", **env)
    assert result.loom_args[:2] == head
    index = result.loom_args.index("--config")
    assert result.loom_args[index + 1] == "ci dir/pitloom.toml"


_BUILD_INPUTS = (
    ("PL_ALLOW_BUILD", ("false", "true"), ["--allow-build"]),
    ("PL_NO_BUILD_ISOLATION", ("false", "true"), ["--no-build-isolation"]),
    ("PL_BUILD_TIMEOUT", ("", "1h30m"), ["--build-timeout", "1h30m"]),
)
_BUILD_INPUT_COMBOS = list(
    itertools.product(*(values for _, values, _ in _BUILD_INPUTS))
)


@pytest.mark.parametrize("mode", ["project", "embed-wheel", "model"])
@pytest.mark.parametrize(
    "values",
    _BUILD_INPUT_COMBOS,
    ids=["-".join(v or "empty" for v in combo) for combo in _BUILD_INPUT_COMBOS],
)
def test_build_input_matrix(
    generate: Callable[..., _Result], tmp_path: Path, mode: str, values: tuple[str, ...]
) -> None:
    """Every combination of the three build inputs in every mode (the
    Action's row of the cross-surface build-flag matrix, see
    tests/test_build_flag_warnings.py). "project"/"embed-wheel" pass each
    set input on as its CLI flag, in a fixed order, and warn about none --
    loom itself decides what has no effect. "model" has no such flags: it
    passes none and warns once per set input instead."""
    env = {
        name: value for (name, _, _), value in zip(_BUILD_INPUTS, values, strict=True)
    }
    if mode == "embed-wheel":
        _make_wheel(tmp_path / "p-1.whl")
        env.update(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), LOOM_STDOUT=EMBED_STDOUT)
    elif mode == "model":
        env["PL_MODEL"] = "dummy.gguf"
    is_set = [value not in ("", "false") for value in values]

    result = generate(**env)

    assert result.returncode == 0
    assert result.loom_args[0] == mode
    expected: list[str] = []
    for (name, _, argv), given in zip(_BUILD_INPUTS, is_set, strict=True):
        if mode != "model" and given:
            expected += argv
        flag = name.removeprefix("PL_").lower().replace("_", "-")
        warning = f"::warning::{flag} has no effect in model mode"
        assert result.output.count(warning) == (mode == "model" and given)
    assert _build_flags(result.loom_args) == expected


def test_build_inputs_follow_the_mode_actually_chosen(
    generate: Callable[..., _Result], tmp_path: Path
) -> None:
    """With both ``embed-wheel`` and ``model`` set, embed-wheel is the mode
    that runs, so the build inputs go with it: keying them on ``model``
    being set instead would drop three flags the command accepts and warn
    that they have no effect "in model mode", which is not the mode."""
    _make_wheel(tmp_path / "p-1.whl")

    result = generate(
        PL_EMBED_WHEEL=str(tmp_path / "*.whl"),
        PL_MODEL="dummy.gguf",
        LOOM_STDOUT=EMBED_STDOUT,
        PL_ALLOW_BUILD="true",
        PL_NO_BUILD_ISOLATION="true",
        PL_BUILD_TIMEOUT="1h30m",
    )

    assert result.returncode == 0
    assert result.loom_args[0] == "embed-wheel"
    assert _build_flags(result.loom_args) == [
        "--allow-build",
        "--no-build-isolation",
        "--build-timeout",
        "1h30m",
    ]
    assert "has no effect in model mode" not in result.output


def _build_flags(loom_args: list[str]) -> list[str]:
    """The build-flag tokens in *loom_args*, with ``--build-timeout``'s value."""
    flags: list[str] = []
    for index, arg in enumerate(loom_args):
        if arg in ("--allow-build", "--no-build-isolation"):
            flags.append(arg)
        elif arg == "--build-timeout":
            flags += loom_args[index : index + 2]
    return flags


def test_windows_crlf_in_loom_output_is_dropped(
    generate: Callable[..., _Result],
) -> None:
    result = generate(
        LOOM_STDOUT="PITLOOM_SBOM_OUTPUT_PATH=out/x.json\\r\\n",
        LOOM_STDERR="WARNING: careful\\r\\n",
    )
    assert result.sbom_path == "out/x.json"
    assert "::warning::careful\n" in result.output


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ('--creator-name "CI Bot" --x', ["--creator-name", "CI Bot", "--x"]),
        ('--creator-name ""', ["--creator-name", ""]),
        ('--a "" --b', ["--a", "", "--b"]),
        ('"" ""', ["", ""]),
        ("--glob '*' -v", ["--glob", "*", "-v"]),
        ("   ", []),
        ('--a\n--b "c d"\n', ["--a", "--b", "c d"]),
        ('--a "x\ny" --b', ["--a", "x\ny", "--b"]),
        ('--a "\n"', ["--a", "\n"]),
        ("--a $HOME `id` $(id)", ["--a", "$HOME", "`id`", "$(id)"]),
        ("--u 'é ü' \"it's\"", ["--u", "é ü", "it's"]),
        ("# not a comment", ["#", "not", "a", "comment"]),
        ("-- --", ["--", "--"]),
    ],
    ids=[
        "quoted",
        "trailing-empty",
        "middle-empty",
        "only-empty",
        "glob",
        "blank",
        "yaml-multiline",
        "newline-in-quotes",
        "only-newline",
        "no-expansion",
        "unicode-and-apostrophe",
        "hash",
        "double-dash",
    ],
)
def test_args_are_split_like_a_shell_would(
    generate: Callable[..., _Result], args: str, expected: list[str]
) -> None:
    result = generate(args)
    assert result.returncode == 0
    assert result.loom_args == ["project", ".", *expected]


def test_unbalanced_args_quoting_is_an_error(generate: Callable[..., _Result]) -> None:
    result = generate('--x "unbalanced')
    assert result.returncode == 1
    assert "::error::" in result.output
    assert result.loom_args == []


def test_python_is_only_required_when_used(generate: Callable[..., _Result]) -> None:
    assert generate(with_python=False).returncode == 0
    result = generate("--x", with_python=False)
    assert result.returncode == 1
    assert "::error::" in result.output


def test_loom_exit_status_and_error_annotation_are_kept(
    generate: Callable[..., _Result],
) -> None:
    result = generate(LOOM_EXIT="3", LOOM_STDERR="ERROR: boom\\n")
    assert result.returncode == 3
    assert "::error::boom" in result.output
    assert result.sbom_path is None


def test_last_stderr_line_without_newline_is_annotated(
    generate: Callable[..., _Result],
) -> None:
    result = generate(LOOM_EXIT="1", LOOM_STDERR="INFO: a\\nERROR: no newline")
    assert result.returncode == 1
    assert "::notice::a\n" in result.output
    assert "::error::no newline\n" in result.output


def test_blank_stderr_lines_produce_no_empty_annotations(
    generate: Callable[..., _Result],
) -> None:
    result = generate(LOOM_STDERR="WARNING: a\\n\\nINFO: b\\n\\r\\n")
    assert "::warning::a\n" in result.output
    assert "::notice::b\n" in result.output
    assert "::warning::\n" not in result.output
    assert "::notice::\n" not in result.output


def test_percent_in_annotation_text_is_escaped(
    generate: Callable[..., _Result],
) -> None:
    result = generate(LOOM_STDERR="WARNING: 100%%25 x%%0Ay\\n")
    assert "::warning::100%2525 x%250Ay\n" in result.output


def test_last_stderr_line_is_annotated_after_a_slow_loom(
    stub_bin: "StubBin", generate: Callable[..., _Result]
) -> None:
    stub_bin.link("sleep")
    stub_bin.add(
        "loom",
        'printf "INFO: first\\n" >&2; sleep 0.3; printf "ERROR: last\\n" >&2; exit 2\n',
    )
    result = generate()
    assert result.returncode == 2
    assert "::notice::first" in result.output
    assert "::error::last" in result.output


def test_large_output_on_both_streams_does_not_deadlock(
    stub_bin: "StubBin", generate: Callable[..., _Result]
) -> None:
    stub_bin.add(
        "loom",
        'printf "PITLOOM_SBOM_OUTPUT_PATH=big.json\\n"\n'
        "python -c \"print('x' * 655360)\"\n"
        "python -c \"import sys; print('y' * 655360, file=sys.stderr)\"\n"
        'printf "ERROR: after the flood\\n" >&2\n',
    )
    result = generate()
    assert result.returncode == 0
    assert result.sbom_path == "big.json"
    assert "::error::after the flood" in result.output


def test_workflow_commands_in_loom_output_are_not_run(
    generate: Callable[..., _Result],
) -> None:
    result = generate(
        LOOM_STDOUT="::set-output name=x::y\\n",
        LOOM_STDERR="INFO: fine\\n::add-mask::secret\\n",
    )
    lines = result.output.splitlines()
    stop = next(line for line in lines if line.startswith("::stop-commands::"))
    resume = f"::{stop.removeprefix('::stop-commands::')}::"
    start, end = lines.index(stop), lines.index(resume)
    for raw in ("::set-output name=x::y", "::add-mask::secret"):
        assert start < lines.index(raw) < end
    assert lines.index("::notice::fine") > end


def test_first_printed_path_wins(generate: Callable[..., _Result]) -> None:
    result = generate(
        LOOM_STDOUT=(
            "note\\nPITLOOM_SBOM_OUTPUT_PATH=a.json\\n"
            "PITLOOM_SBOM_OUTPUT_PATH=b.json\\n"
        )
    )
    assert result.sbom_path == "a.json"


def test_no_printed_path_reports_an_empty_sbom_path(
    generate: Callable[..., _Result],
) -> None:
    result = generate(LOOM_STDOUT="nothing useful\\n")
    assert result.returncode == 0
    assert result.sbom_path == ""


def test_loom_killed_by_a_signal_fails_the_step(
    stub_bin: "StubBin", generate: Callable[..., _Result]
) -> None:
    stub_bin.add("loom", 'kill -9 "$$"\n')
    result = generate()
    assert result.returncode == 137
    assert result.sbom_path is None


def test_embed_wheel_extracts_the_embedded_sbom(
    generate: Callable[..., _Result], tmp_path: Path
) -> None:
    _make_wheel(tmp_path / "p-1.whl")
    result = generate(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), LOOM_STDOUT=EMBED_STDOUT)
    assert result.returncode == 0
    assert result.sbom_path == "p-1.spdx3.json"
    assert (tmp_path / "work" / "p-1.spdx3.json").read_text("utf-8") == "{}"
    assert "-o" not in result.loom_args


def test_embed_wheel_with_several_wheels_warns_and_drops_output(
    generate: Callable[..., _Result], tmp_path: Path
) -> None:
    _make_wheel(tmp_path / "p-1.whl")
    _make_wheel(tmp_path / "q-1.whl")
    result = generate(PL_EMBED_WHEEL=str(tmp_path / "*.whl"), PL_OUTPUT="out.json")
    assert result.returncode == 0
    assert "::warning::" in result.output
    assert "-o" not in result.loom_args
    assert result.sbom_path is None


def test_embed_wheel_without_a_reported_sbom_name_is_an_error(
    generate: Callable[..., _Result], tmp_path: Path
) -> None:
    _make_wheel(tmp_path / "p-1.whl")
    result = generate(PL_EMBED_WHEEL=str(tmp_path / "*.whl"))
    assert result.returncode == 1
    assert "::error::" in result.output
