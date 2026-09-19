# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for the "Generate SBOM" step of ``action.yml`` against a stub ``loom``.

The step's ``run:`` script is extracted from ``action.yml`` and run under
bash with ``PATH`` limited to stubs (POSIX only), so the tests cover the
argument handling, output/annotation capture and exit-code propagation
without installing Pitloom.
"""

import itertools
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest
import yaml

if TYPE_CHECKING:
    from tests.scripts.action.conftest import StubBin

# Stub env: LOOM_ARGS_FILE, LOOM_EXIT, LOOM_STDOUT, LOOM_STDERR (printf formats).
LOOM_STUB = """\
printf '%s\\0' "$@" > "${LOOM_ARGS_FILE}"
printf "${LOOM_STDOUT-PITLOOM_SBOM_OUTPUT_PATH=out/sbom.spdx3.json\\\\n}"
printf "${LOOM_STDERR-}" >&2
exit "${LOOM_EXIT:-0}"
"""


EMPTY_INPUTS = dict.fromkeys(
    "PL_EMBED_WHEEL PL_MODEL PL_OUTPUT PL_PRETTY PL_ENRICH "
    "PL_EXTRACT_FILE_HEADER PL_CONTENT_TYPE PL_CONTENT_TYPE_METHOD "
    "PL_MAX_SOURCE_METADATA_BYTES PL_OFFLINE PL_USE_LOCKFILE "
    "PL_ALLOW_BUILD PL_NO_BUILD_ISOLATION PL_BUILD_TIMEOUT".split(),
    "",
)


class _Result(NamedTuple):
    returncode: int
    output: str  # the step's stdout and stderr, as the runner would log them
    sbom_path: str | None
    loom_args: list[str]


def _generate_script(action_yml: Path) -> str:
    steps = yaml.safe_load(action_yml.read_text(encoding="utf-8"))["runs"]["steps"]
    return str(next(step["run"] for step in steps if step.get("id") == "generate"))


@pytest.fixture(name="generate")
def generate_fixture(
    stub_bin: "StubBin", tmp_path: Path, scripts_dir: Path
) -> Callable[..., _Result]:
    """Return ``generate(args, *, with_python, **env)``."""
    script = tmp_path / "generate.sh"
    script.write_text(_generate_script(scripts_dir.parent / "action.yml"), "utf-8")
    stub_bin.link("tee", "tr", "sed", "head", "basename", "mktemp", "rm")
    stub_bin.add("loom", LOOM_STUB)
    github_output = tmp_path / "github-output"
    args_file = tmp_path / "loom-args"
    workdir = tmp_path / "work"
    workdir.mkdir()
    stub_bin.cwd = workdir

    def run(args: str = "", *, with_python: bool = True, **env: str) -> _Result:
        if with_python:
            stub_bin.add("python", f'exec "{sys.executable}" "$@"\n')
        github_output.write_text("", encoding="utf-8")
        result = stub_bin.run(
            ["-eo", "pipefail", str(script)],
            GITHUB_ACTION_PATH=str(scripts_dir.parent),
            GITHUB_OUTPUT=str(github_output),
            LOOM_ARGS_FILE=str(args_file),
            PL_PROJECT_PATH=".",
            PL_ARGS=args,
            **{**EMPTY_INPUTS, **env},
        )
        written = github_output.read_text(encoding="utf-8").strip()
        sbom_path = written.removeprefix("sbom-path=") if written else None
        loom_args = (
            args_file.read_bytes().decode("utf-8").split("\0")[:-1]
            if args_file.exists()
            else []
        )
        return _Result(
            result.returncode, result.stdout + result.stderr, sbom_path, loom_args
        )

    return run


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


EMBED_STDOUT = "pitloom: embedded p-1.dist-info/sboms/p-1.spdx3.json into p-1.whl\\n"


def _make_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("p-1.dist-info/sboms/p-1.spdx3.json", "{}")


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
