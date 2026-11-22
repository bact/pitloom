# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the Hatchling build hook says about its own run, through the real
hook: a build it makes no SBOM for (``hook-no-effect``, three lines checked in
order: disabled, not a wheel, editable) and the SBOM it staged (a summary with
no code). Also the hook's step frame, and that the command line and the
library say none of these lines.

See also: tests/messages/test_frames_build.py (the frame table) and
tests/messages/test_config_hook.py (the hook's configuration lines).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from pitloom.__main__ import main
from pitloom.assemble import generate_project_sbom
from pitloom.core.config import read_pitloom_config
from pitloom.core.creation import CreationMetadata
from pitloom.logging_config import CODE_ATTR, configure_logging
from pitloom.messages import (
    HOOK_FRAME,
    HOOK_PREFIX,
    HOOK_STEP_FRAME,
    MESSAGES,
    say_summary,
    trusted_message,
)
from pitloom.messages.build import (
    HOOK_DISABLED_LINE,
    HOOK_EDITABLE_LINE,
    HOOK_NO_EFFECT,
    HOOK_NOT_WHEEL_LINE,
    HOOK_SBOM_STAGED,
)
from tests._message_drift import SAMPLES
from tests.extract.conftest import (
    make_hook,
    write_pyproject,
    write_pyproject_with_pitloom_config,
)

pytestmark = pytest.mark.platform

_CODE = "hook-no-effect"
_START = f"INFO: {HOOK_PREFIX}"
_DISABLED = f"{_START}disabled; skipping SBOM generation [{_CODE}]"
_EDITABLE = (
    f"{_START}build variant 'editable' skipped; its wheel does not hold the "
    f"project's files [{_CODE}]"
)
_STAGED_START = f"{_START}staged SBOM"


def _not_wheel(target: str) -> str:
    """The line for a build target the hook skips, *target* as printed."""
    return f"{_START}target {target} is not 'wheel'; skipping SBOM generation [{_CODE}]"


def _run(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    config: dict[str, Any] | None = None,
    target: str = "wheel",
    variant: str = "standard",
    table: str = "",
) -> list[str]:
    """The lines the hook printed on stderr for one build."""
    write_pyproject_with_pitloom_config(root, table)
    hook = make_hook(str(root), config or {}, target_name=target)
    build_data: dict[str, Any] = {}
    hook.initialize(variant, build_data)
    hook.finalize(variant, build_data, "")
    return capsys.readouterr().err.splitlines()


def _said(err: list[str], code: str | None) -> list[str]:
    """The lines of *err* that end in ``[code]`` (or hold no code at all)."""
    if code is None:
        return [ln for ln in err if not ln.endswith("]")]
    return [ln for ln in err if ln.endswith(f"[{code}]")]


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned time, so the hook adds no ``datetime-unpinned`` line."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")


# --- each condition says its one line ----------------------------------------


@pytest.mark.parametrize(
    ("build", "line"),
    [
        pytest.param({"config": {"enabled": False}}, _DISABLED, id="disabled"),
        pytest.param({"target": "sdist"}, _not_wheel("sdist"), id="sdist"),
        pytest.param({"variant": "editable"}, _EDITABLE, id="editable"),
    ],
)
def test_each_skipped_build_says_one_coded_info_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    build: dict[str, Any],
    line: str,
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        err = _run(tmp_path, capsys, **build)
    assert err == [line]
    (record,) = caplog.records
    assert record.levelno == logging.INFO
    assert getattr(record, CODE_ATTR) == _CODE
    assert trusted_message(line) is HOOK_NO_EFFECT
    # The same text at another level, or in the error frame, is no line of it.
    text = line.removeprefix("INFO: ")
    assert trusted_message(f"WARNING: {text}") is None
    assert trusted_message(f"ERROR: {text}") is None


def test_the_entry_holds_the_three_lines_in_the_order_they_are_tried() -> None:
    assert HOOK_NO_EFFECT.lines == (
        HOOK_DISABLED_LINE,
        HOOK_NOT_WHEEL_LINE,
        HOOK_EDITABLE_LINE,
    )


@pytest.mark.parametrize(
    ("target", "printed"),
    [
        pytest.param("sd\nist\x1b[31m", "'sd\\nist\\x1b[31m'", id="control"),
        pytest.param("sdist [over-cap]", "sdist [over-cap]", id="fake-code"),
    ],
)
def test_a_hostile_target_name_stays_on_one_line_with_the_real_code_last(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    printed: str,
) -> None:
    (line,) = _run(tmp_path, capsys, target=target)
    assert line == _not_wheel(printed)
    assert "\x1b" not in line and "\n" not in line
    assert line.endswith(f" [{_CODE}]")
    assert trusted_message(line) is HOOK_NO_EFFECT


# --- the negative sides of each condition and of their order -----------------


def test_an_enabled_wheel_build_says_none_of_the_three_and_staged_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    err = _run(tmp_path, capsys)
    assert _said(err, _CODE) == []
    staged = [ln for ln in err if ln.startswith(_STAGED_START)]
    assert len(staged) == 1
    # Not the editable wheel's line, nor a wheel target's "not a wheel".
    assert "skipping SBOM generation" not in "\n".join(err)


@pytest.mark.parametrize(
    ("config", "target", "variant", "line"),
    [
        pytest.param(
            {"enabled": False}, "sdist", "editable", _DISABLED, id="disabled-first"
        ),
        pytest.param({}, "sdist", "editable", _not_wheel("sdist"), id="target-first"),
    ],
)
def test_the_checks_are_tried_in_order_and_only_the_first_that_holds_speaks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    config: dict[str, Any],
    target: str,
    variant: str,
    line: str,
) -> None:
    assert _run(tmp_path, capsys, config=config, target=target, variant=variant) == [
        line
    ]


# --- the staged SBOM is a summary --------------------------------------------


def test_the_staged_sbom_line_is_a_summary_with_no_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="pitloom"):
        err = _run(tmp_path, capsys)
    (line,) = [ln for ln in err if ln.startswith(_STAGED_START)]
    assert line == (
        f"{_STAGED_START} 'testpkg-0.1.0.spdx3.json' (0 fragment(s)); Hatchling "
        "will inject it into .dist-info/sboms/ in the wheel"
    )
    assert not line.endswith("]")
    assert trusted_message(line) is None
    (record,) = [r for r in caplog.records if r.getMessage() == line[len("INFO: ") :]]
    assert record.levelno == logging.INFO
    assert getattr(record, CODE_ATTR, None) is None


@pytest.mark.parametrize(
    ("basename", "written"),
    [
        pytest.param("my sbom's name", '"my sbom\'s name.spdx3.json"', id="space"),
        pytest.param("it's", '"it\'s.spdx3.json"', id="apostrophe"),
    ],
)
def test_the_staged_file_name_is_quoted_by_the_path_writer(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    basename: str,
    written: str,
) -> None:
    err = _run(tmp_path, capsys, table=f'[tool.pitloom]\nsbom-basename = "{basename}"')
    (line,) = [ln for ln in err if ln.startswith(_STAGED_START)]
    assert line.startswith(f"{_STAGED_START} {written} (0 fragment(s));")


def test_the_staged_summary_escapes_a_hostile_name_and_counts_fragments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The hook's own file names are safe; the summary does not rely on it."""
    configure_logging()
    say_summary(
        logging.getLogger("pitloom"),
        HOOK_SBOM_STAGED,
        path="a b\n'c\x1b[0m",
        number=2,
    )
    (line,) = capsys.readouterr().err.splitlines()
    assert line.startswith(f'{_STAGED_START} "a b\\n\'c\\x1b[0m" (2 fragment(s));')
    assert "\x1b" not in line
    assert trusted_message(line) is None


# --- the frames --------------------------------------------------------------


def test_the_step_frame_allows_exactly_its_two_codes_at_two_levels() -> None:
    assert HOOK_STEP_FRAME.codes == frozenset({_CODE, "temp-dir-unwritable"})
    assert HOOK_STEP_FRAME.levels == frozenset({"WARNING", "INFO"})
    assert HOOK_STEP_FRAME.template == HOOK_PREFIX == HOOK_FRAME.template
    assert HOOK_STEP_FRAME.allows(_CODE, "INFO")
    assert not HOOK_STEP_FRAME.allows(_CODE, "ERROR")
    assert not HOOK_STEP_FRAME.allows("over-cap", "INFO")


def test_an_error_line_stays_the_error_frames_and_takes_no_hook_code() -> None:
    assert HOOK_FRAME.levels == frozenset({"ERROR"}) and HOOK_FRAME.codes is None
    assert not HOOK_FRAME.allows(_CODE, "INFO")


def test_a_line_of_another_code_after_the_hook_prefix_is_not_trusted() -> None:
    """At ``WARNING`` and ``INFO`` the step frame names its codes; the error
    frame, which comes before any code's ``ERROR`` line, is the other's."""
    over = MESSAGES["over-cap"]
    seen = set()
    for shape in over.lines:
        text = shape.render({n: SAMPLES[n] for n in shape.fields})
        assert trusted_message(f"{shape.level}: {text} [over-cap]") is over
        framed = trusted_message(f"{shape.level}: {HOOK_PREFIX}{text} [over-cap]")
        assert (framed is over) is (shape.level == "ERROR"), shape.level
        seen.add(shape.level)
    assert seen - {"ERROR"}
    # The hook's own text with a code its frame does not allow.
    assert (
        trusted_message(f"{_START}disabled; skipping SBOM generation [over-cap]")
        is None
    )


# --- only the hook says these lines ------------------------------------------


def _project(root: Path) -> Path:
    """A Hatchling project the command line and the library can read."""
    root.mkdir()
    write_pyproject(root)
    (root / "testpkg").mkdir()
    (root / "testpkg" / "__init__.py").write_text("", encoding="utf-8")
    return root


def test_the_command_line_says_none_of_the_hook_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _project(tmp_path / "p")
    out = tmp_path / "sbom.spdx3.json"
    argv = ["loom", "project", str(root), "-o", str(out), "--offline"]
    monkeypatch.setattr(sys, "argv", argv)
    assert main() == 0
    err = capsys.readouterr().err
    assert HOOK_PREFIX not in err
    assert f"[{_CODE}]" not in err and "staged SBOM" not in err


def test_the_library_says_none_of_the_hook_lines(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _project(tmp_path / "p")
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        generate_project_sbom(
            root,
            output_path=tmp_path / "sbom.spdx3.json",
            creation_metadata=CreationMetadata(),
            offline=True,
        )
    assert all(getattr(r, CODE_ATTR, None) != _CODE for r in caplog.records)
    assert not [r for r in caplog.records if "staged SBOM" in r.getMessage()]
    assert not [
        r
        for r in caplog.records
        if r.levelno >= logging.INFO and HOOK_PREFIX in r.getMessage()
    ]


# --- the hook's error frame and its DEBUG line --------------------------------


def test_an_error_line_said_while_the_sbom_is_made_carries_the_hook_frame(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def noisy(*args: Any, **kwargs: Any) -> Any:
        logging.getLogger("pitloom.probe").error("nested failure")
        return read_pitloom_config(*args, **kwargs)

    monkeypatch.setattr("pitloom.plugins.hatch.read_pitloom_config", noisy)
    assert f"ERROR: {HOOK_PREFIX}nested failure" in _run(tmp_path, capsys)


def test_the_debug_line_names_the_build_variant(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PITLOOM_DEBUG", "1")
    write_pyproject_with_pitloom_config(tmp_path, "")
    hook = make_hook(str(tmp_path), {}, target_name="sdist")
    with caplog.at_level(logging.DEBUG, logger="pitloom"):
        hook.initialize("standard", {})
    assert f"{HOOK_PREFIX}build variant 'standard'" in caplog.messages
