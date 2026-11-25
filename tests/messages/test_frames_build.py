# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The frames of a temporary directory's surface (``Build: ``, ``Git source:
``, ``Hugging Face source: ``, ``PyPI source: ``, ``AI model scan: ``, the
hook's): each allows exactly the codes said after it, a frame handed to the
temporary-directory helpers or a guarded activity is checked when it is
handed over (a cleanup or a signal handler would lose the error), and a
line of another code after one is not trusted.

See also: tests/messages/test_frames_codes.py (the Git and relay frames,
the ``emit`` sites) and tests/messages/test_frames.py (the table).
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import signal
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pitloom.core import build_signals, temp_dirs
from pitloom.core.build_signals import (
    BUILD_ACTIVITY,
    MODEL_SCAN_ACTIVITY,
    GuardedActivity,
    TerminationGuard,
    say_termination,
)
from pitloom.core.internal_error import InternalError
from pitloom.logging_config import configure_logging
from pitloom.messages import (
    BUILD_FRAME,
    BUILD_PREFIX,
    COMMAND_FRAME,
    FRAMES,
    GIT_FRAME,
    HF_FRAME,
    HOOK_PREFIX,
    HOOK_STEP_FRAME,
    MESSAGES,
    PYPI_FRAME,
    RELAY_FRAME,
    SCAN_FRAME,
    Frame,
    emit,
    trusted_message,
)
from pitloom.messages._archive_members_say import (
    _KINDS as MEMBER_KIND_ENTRIES,  # the entry each kind says
)
from pitloom.messages._options import (
    BUILD_NO_EFFECT_LINE,
    OPTION_NO_EFFECT,
    STALE_FINGERPRINT_LINE,
)
from pitloom.messages.build import (
    ACTIVITIES,
    HOOK_SBOM_STAGED,
    INTERRUPTED,
    INTERRUPTED_DURING_LINE,
    TEMP_DIR_UNWRITABLE,
    TERMINATION_SIGNALS,
)
from pitloom.messages.config import CLOCK_LINE, DATETIME_UNPINNED
from pitloom.messages.files import OVER_CAP
from pitloom.messages.models import LIBRARY_MISSING
from tests._message_drift import SAMPLES, source_modules
from tests.messages.test_frames_codes import (
    PASS_THROUGH,
    _emitted,
    _module_of,
    _resolve,
)

pytestmark = pytest.mark.platform  # temporary directories, signals

_LOG = logging.getLogger("pitloom.test_frames_build")
_TEMP = TEMP_DIR_UNWRITABLE.code

#: Each frame of a surface with a temporary directory, its codes and levels.
_TABLE: dict[Frame, tuple[frozenset[str], frozenset[str]]] = {
    BUILD_FRAME: (
        frozenset(
            {
                "archive-member-conflict",
                "archive-member-invalid",
                "archive-member-unsafe",
                "build-code-unsafe",
                "build-failed",
                "build-processes-unsafe",
                "build-timeout",
                "interrupted",
                "library-missing",
                _TEMP,
            }
        ),
        frozenset({"WARNING", "INFO"}),
    ),
    HF_FRAME: (frozenset({_TEMP}), frozenset({"WARNING"})),
    PYPI_FRAME: (frozenset({_TEMP}), frozenset({"WARNING"})),
    SCAN_FRAME: (frozenset({"interrupted", _TEMP}), frozenset({"WARNING"})),
    HOOK_STEP_FRAME: (
        frozenset({"hook-no-effect", _TEMP}),
        frozenset({"WARNING", "INFO"}),
    ),
}

#: The helpers that take the frame of a temporary directory.
_TEMP_API = frozenset(
    {
        "registered_temp_dir",
        "remove_temp_dir",
        "rmtree_quietly",
        "temp_dir",
        "warn_if_left_behind",
    }
)


def _frame_notes() -> Callable[..., list[str]]:
    """``frame_notes`` of the reference helper, loaded from its file (the
    ``scripts`` folder is no package, and ``pytest`` does not put the
    repository root on ``sys.path``)."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "message_reference"
    spec = importlib.util.spec_from_file_location(
        "message_reference_frames", path / "frames.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("Callable[..., list[str]]", module.frame_notes)


def test_each_frame_names_its_codes_and_levels() -> None:
    for frame, (codes, levels) in _TABLE.items():
        assert (frame.codes, frame.levels) == (codes, levels), frame.template
        assert all(code in MESSAGES for code in codes)
    assert BUILD_FRAME.render({}) == BUILD_PREFIX == "Build: "


def _printed(frame: Frame, code: str) -> list[tuple[str, bool]]:
    """Each line of *code*, printed after *frame*, and whether the frame
    allows it at that line's level."""
    message = MESSAGES[code]
    found = []
    for line in message.lines:
        text = line.render({n: SAMPLES[n] for n in line.fields})
        printed = f"{line.level}: {frame.render({})}{text} [{code}]"
        found.append((printed, frame.allows(code, line.level)))
    return found


@pytest.mark.parametrize(
    ("frame", "code"),
    [(f, c) for f, (codes, _) in _TABLE.items() for c in sorted(codes)],
    ids=lambda v: v if isinstance(v, str) else v.template.strip(": "),
)
def test_a_line_of_an_allowed_code_is_trusted_after_the_frame(
    frame: Frame, code: str
) -> None:
    """At a level the frame frames; at another (Ctrl-C's ``ERROR`` after
    ``Build: ``) it is not."""
    for printed, allowed in _printed(frame, code):
        assert (trusted_message(printed) is MESSAGES[code]) is allowed, printed


def test_an_over_cap_line_after_build_is_not_trusted_nor_said() -> None:
    (printed, allowed), *_ = _printed(BUILD_FRAME, OVER_CAP.code)
    assert not allowed and trusted_message(printed) is None
    over = OVER_CAP.lines[0]
    values: dict[str, Any] = {n: SAMPLES[n] for n in over.fields}
    with pytest.raises(InternalError):
        emit(_LOG, OVER_CAP, logging.WARNING, line=over, frame=BUILD_FRAME, **values)


def test_an_options_line_after_build_is_not_trusted() -> None:
    """Q2: ``option-no-effect`` keeps its two prefixes as literals; the
    build frame does not come before the code, so ``Build: Options:
    FINGERPRINT=...`` is no line Pitloom prints."""
    assert BUILD_NO_EFFECT_LINE.template.startswith(BUILD_FRAME.template)
    assert not BUILD_FRAME.allows(OPTION_NO_EFFECT.code, "WARNING")
    stale = STALE_FINGERPRINT_LINE.render(
        {n: SAMPLES[n] for n in STALE_FINGERPRINT_LINE.fields}
    )
    assert stale.startswith("Options: FINGERPRINT=")
    code = OPTION_NO_EFFECT.code
    assert trusted_message(f"WARNING: {stale} [{code}]") is OPTION_NO_EFFECT
    assert trusted_message(f"WARNING: Build: {stale} [{code}]") is None


def test_the_build_frame_also_trusts_the_scan_library_line() -> None:
    """Q4, accepted: a frame allows a code, not a line, so the model scan's
    ``library-missing`` line reads as genuine after ``Build: `` too."""
    (scan, _err, _warn) = LIBRARY_MISSING.lines
    text = scan.render({n: SAMPLES[n] for n in scan.fields})
    line = f"WARNING: Build: {text} [library-missing]"
    assert trusted_message(line) is LIBRARY_MISSING


def test_a_hook_line_with_the_prefix_as_a_literal_is_not_framed() -> None:
    """``datetime-unpinned`` and the staged-SBOM summary carry the hook's
    prefix in their own text, so the step frame does not come before them:
    the prefix printed twice is no line the hook prints."""
    assert CLOCK_LINE.template.startswith(HOOK_PREFIX)
    assert HOOK_SBOM_STAGED.template.startswith(HOOK_PREFIX)
    assert not HOOK_STEP_FRAME.allows(DATETIME_UNPINNED.code, "INFO")
    code = DATETIME_UNPINNED.code
    assert trusted_message(f"INFO: {CLOCK_LINE.template} [{code}]") is (
        DATETIME_UNPINNED
    )
    twice = f"INFO: {HOOK_PREFIX}{CLOCK_LINE.template} [{code}]"
    assert trusted_message(twice) is None


_BAD_FRAMES = [
    pytest.param(RELAY_FRAME, id="relay"),  # another code, and values
    pytest.param(COMMAND_FRAME, id="error-only"),
    pytest.param(
        Frame(
            levels=frozenset({"WARNING"}),
            template="FILE=%(file)s: ",
            surface="a test",
            codes=frozenset({_TEMP}),
        ),
        id="takes-values",
    ),
]


@pytest.mark.parametrize("frame", _BAD_FRAMES)
def test_the_temp_dir_helpers_refuse_a_frame_before_doing_anything(
    frame: Frame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On entry: no directory made, nothing removed. A check left to the
    removal would run in a cleanup, where the error is lost."""
    done: list[object] = []

    def mkdtemp(prefix: str) -> str:
        done.append(prefix)
        return str(tmp_path / prefix)

    monkeypatch.setattr(temp_dirs, "tempfile", SimpleNamespace(mkdtemp=mkdtemp))
    monkeypatch.setattr(temp_dirs, "rmtree", lambda *a, **k: done.append(a))
    with pytest.raises(InternalError), temp_dirs.temp_dir("t-", frame=frame):
        pass
    with pytest.raises(InternalError):
        temp_dirs.registered_temp_dir(TerminationGuard(), "t-", frame=frame)
    for removal in (temp_dirs.remove_temp_dir, temp_dirs.warn_if_left_behind):
        with pytest.raises(InternalError):
            removal(tmp_path, frame=frame)
    assert not done


@pytest.mark.parametrize(
    ("frame", "name"),
    [
        (BUILD_FRAME, "the scan"),  # no line names it
        (GIT_FRAME, "the build"),  # no interrupted line after it
        (HF_FRAME, "the build"),
        (RELAY_FRAME, "the build"),
        (COMMAND_FRAME, "the build"),
    ],
    ids=["name", "git", "hf", "relay", "error-only"],
)
def test_a_guarded_activity_is_refused_when_made(frame: Frame, name: str) -> None:
    with pytest.raises(InternalError):
        GuardedActivity(frame, name)


# pylint: disable-next=protected-access
_NO_ACTIVITY = build_signals._NO_ACTIVITY


@pytest.mark.parametrize(
    "activity",
    [BUILD_ACTIVITY, MODEL_SCAN_ACTIVITY, _NO_ACTIVITY],
    ids=["build", "scan", "none"],
)
@pytest.mark.parametrize("in_hold", [True, False], ids=["during", "after"])
def test_the_signal_line_of_each_activity_is_coded_and_trusted(
    activity: GuardedActivity, in_hold: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    """Said through the handler's own path, called directly."""
    configure_logging()
    say_termination(signal.Signals.SIGTERM, activity, in_hold)
    (line,) = capsys.readouterr().err.splitlines()
    when = "during" if in_hold else "after"
    assert line == (
        f"WARNING: {activity.prefix}received SIGTERM {when} {activity.name}; "
        "exiting after cleanup [interrupted]"
    )
    assert trusted_message(line) is INTERRUPTED


@pytest.mark.parametrize("name", TERMINATION_SIGNALS)
def test_every_signal_and_activity_is_a_value_of_the_line(name: str) -> None:
    for activity in ACTIVITIES:
        text = INTERRUPTED_DURING_LINE.render({"signal": name, "activity": activity})
        assert trusted_message(f"WARNING: {text} [interrupted]") is INTERRUPTED
    assert {BUILD_ACTIVITY.name, MODEL_SCAN_ACTIVITY.name, _NO_ACTIVITY.name} == set(
        ACTIVITIES
    )


def _keyword(node: ast.Call, name: str) -> ast.expr | None:
    return next((kw.value for kw in node.keywords if kw.arg == name), None)


def _callee(node: ast.Call) -> str | None:
    func = node.func
    return getattr(func, "id", getattr(func, "attr", None))


def _hands_temp_api(node: ast.Call) -> bool:
    """A call of a temp-directory helper, or one handing it on
    (``weakref.finalize``, ``functools.partial``)."""
    if _callee(node) in _TEMP_API:
        return True
    return _callee(node) in {"finalize", "partial"} and any(
        isinstance(a, ast.Name) and a.id in _TEMP_API for a in node.args
    )


def _frame_of(node: ast.expr, rel: str) -> object:
    """The frame a module-level name of *rel* stands for; ``None`` for a
    literal ``None``."""
    if isinstance(node, ast.Constant) and node.value is None:
        return None
    return _resolve(node, _module_of(rel))


#: The archive-member listers (pitloom.core.archive_member_names): a frame
#: handed to one (fourth argument) frames every archive-member code.
_MEMBER_LISTERS = frozenset({"archive_members", "file_members", "zip_file_members"})
#: The codes a lister says.
_MEMBER_CODES = frozenset(m.code for m, _, _ in MEMBER_KIND_ENTRIES.values())
#: The lister module hands its own *frame* parameter on.
_MEMBER_PASS_THROUGH = frozenset({("core/archive_member_names.py", "frame")})


def _member_said_at(node: ast.Call, rel: str) -> list[tuple[object, str]] | None:
    """The frame and codes of a call handing a frame to an archive-member
    lister or to ``warn_archive_member`` (that kind's code); ``None`` for
    any other call, or a frame handed on."""
    callee = _callee(node)
    if callee in _MEMBER_LISTERS:
        frame = node.args[3] if len(node.args) > 3 else _keyword(node, "frame")
    elif callee == "warn_archive_member":
        frame = _keyword(node, "frame")
    else:
        return None
    if frame is None or (rel, ast.unparse(frame)) in _MEMBER_PASS_THROUGH:
        return None
    codes = sorted(_MEMBER_CODES)
    if callee == "warn_archive_member":
        kind = _resolve(node.args[1], _module_of(rel))
        assert isinstance(kind, str), f"{rel}:{node.lineno}"
        codes = [MEMBER_KIND_ENTRIES[kind][0].code]
    return [(_frame_of(frame, rel), code) for code in codes]


def _said_at(node: ast.Call, rel: str) -> list[tuple[object, str]] | None:
    """The frame a call says codes after, and the codes: a
    :class:`GuardedActivity` made with it (``interrupted``), an ``emit``
    with it, a temporary directory handed it (``temp-dir-unwritable``) or
    an archive-member lister (:func:`_member_said_at`); ``None`` for any
    other call, a frame handed on (:data:`PASS_THROUGH`) or ``None``."""
    where = f"{rel}:{node.lineno}"
    if _callee(node) == "GuardedActivity":
        name = node.args[1]
        assert isinstance(name, ast.Constant) and name.value in ACTIVITIES, where
        return [(_frame_of(node.args[0], rel), INTERRUPTED.code)]
    members = _member_said_at(node, rel)
    if members is not None:
        return members
    frame = _keyword(node, "frame")
    emits = _callee(node) == "emit" and frame is not None
    if not (emits or _hands_temp_api(node)):
        return None
    assert frame is not None, f"{where}: no frame"
    if (rel, ast.unparse(frame)) in PASS_THROUGH:
        return None
    code = _emitted(node, _module_of(rel))[0].code if emits else _TEMP
    return [(_frame_of(frame, rel), code)]


def _said_after_each_frame() -> dict[Frame, set[str]]:
    """The codes said after each frame (:func:`_said_at`), each frame a
    module's own name."""
    said: dict[Frame, set[str]] = defaultdict(set)
    for rel, tree in source_modules():
        calls = (n for n in ast.walk(tree) if isinstance(n, ast.Call))
        said_at = (_said_at(n, rel) or [] for n in calls)
        for found, code in (pair for pairs in said_at for pair in pairs):
            if found is not None:
                assert isinstance(found, Frame), (rel, code)
                said[found].add(code)
    return said


def test_every_code_a_frame_allows_is_said_after_it() -> None:
    """Each frame naming its codes, but the relay frame (a drift test walks
    the readers for it): the codes it allows are exactly those said after
    it, so a narrow frame never strips a code and a wide one trusts no
    line nothing prints."""
    said = _said_after_each_frame()
    checked = [f for f in FRAMES if f.codes is not None and f is not RELAY_FRAME]
    assert len(checked) == 6
    for frame in checked:
        assert frozenset(said[frame]) == frame.codes, frame.template


def test_no_model_reader_logs_at_error() -> None:
    """Q18: the relay frame frames ``WARNING`` lines only, as no reader
    under ``extract/ai_model`` logs at ``ERROR``."""
    assert RELAY_FRAME.levels == {"WARNING"}
    walked = 0
    for rel, tree in source_modules():
        if not rel.startswith("extract/ai_model/"):
            continue
        walked += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert _callee(node) not in {"error", "exception", "critical"}, rel
            elif isinstance(node, ast.Attribute):
                assert node.attr not in {"ERROR", "CRITICAL", "FATAL"}, rel
    assert walked >= 10


@pytest.mark.parametrize("code", sorted(_TABLE[BUILD_FRAME][0] | {_TEMP}), ids=str)
def test_the_reference_names_each_frame_a_code_is_printed_after(code: str) -> None:
    message = MESSAGES[code]
    notes = _frame_notes()(message, ("ERROR", "WARNING", "INFO"))
    for frame in _TABLE:
        named = any(n.startswith(f"`{frame.shown}<text>`") for n in notes)
        assert named is any(frame.allows(code, lv) for lv in message.levels)
