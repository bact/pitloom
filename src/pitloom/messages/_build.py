# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What ``--allow-build`` says about the build it runs, each after
:data:`~pitloom.messages.BUILD_FRAME` (``Build: ``): ``build-code-unsafe``
(a real build runs the project's own code), ``build-failed``,
``build-timeout`` and ``build-processes-unsafe`` (processes the build left
running); and what any surface says about a temporary directory of its own
(``temp-dir-unwritable``) and a signal that ends Pitloom (``interrupted``).

See also: :mod:`pitloom.messages._build_say` (the helpers),
:mod:`pitloom.core._models_wheel_build_and_read` (the build) and
:mod:`pitloom.core.build_signals` (the signals).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"

_RUNS: Final = (
    "DIR=%(dir)s: --allow-build runs a PEP 517 build for up to %(seconds)s "
    "seconds (--build-timeout), which executes the project's build code "
    "(build-backend %(backend)s, "
)
_NO_MODULE: Final = "no discovery module for it) "
_STATIC_FAILED: Final = "its static discovery failed) "
_ISOLATED: Final = "in an isolated build environment"
_SHARED: Final = "in Pitloom's own environment (no build isolation)"

#: A build for a backend no discoverer reads, in a build environment of its
#: own.
UNSAFE_NO_MODULE_LINE: Final = Line(
    level="WARNING", template=f"{_RUNS}{_NO_MODULE}{_ISOLATED}"
)
#: A build after the backend's own discoverer failed, isolated.
UNSAFE_STATIC_FAILED_LINE: Final = Line(
    level="WARNING", template=f"{_RUNS}{_STATIC_FAILED}{_ISOLATED}"
)
#: A build for a backend no discoverer reads, in Pitloom's environment
#: (``--no-build-isolation``).
UNSAFE_NO_MODULE_SHARED_LINE: Final = Line(
    level="WARNING", template=f"{_RUNS}{_NO_MODULE}{_SHARED}"
)
#: A build after the backend's own discoverer failed, in Pitloom's
#: environment.
UNSAFE_STATIC_FAILED_SHARED_LINE: Final = Line(
    level="WARNING", template=f"{_RUNS}{_STATIC_FAILED}{_SHARED}"
)

#: A real build about to run.
BUILD_CODE_UNSAFE: Final = Message(
    code="build-code-unsafe",
    condition="unsafe",
    lines=(
        UNSAFE_NO_MODULE_LINE,
        UNSAFE_STATIC_FAILED_LINE,
        UNSAFE_NO_MODULE_SHARED_LINE,
        UNSAFE_STATIC_FAILED_SHARED_LINE,
    ),
    summary="--allow-build lists a project's files by running a real PEP 517 "
    "build of its wheel, which executes the project's own build code (its "
    "build backend and any script the backend runs) with the user's "
    "rights, for up to --build-timeout seconds. Said before each build: "
    "for a build backend no file discoverer of Pitloom reads, or after the "
    "backend's own discoverer failed; in a fresh, isolated build "
    "environment, or in Pitloom's own with --no-build-isolation.",
    did="Ran the build and read the file list from the wheel it wrote.",
    effect="none",
    actor="user",
    advice="Tell the user Pitloom ran the project's own build code, as "
    "--allow-build asks; run it only on a project they trust. Do not pass "
    "--allow-build for them on a project they have not chosen to build; "
    f"{ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

#: No interpreter to run the build with.
BUILD_INTERPRETER_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: no Python interpreter to run PyPA build with; not built",
)
#: A build that exited with an error.
BUILD_EXIT_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: the build exited with code %(exit_code)s; last "
    "output: %(output)s",
)
#: A build that wrote no wheel, or several.
BUILD_WHEEL_COUNT_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: the build wrote %(number)s wheels, not one",
)
#: A wheel with nothing in it but its ``.dist-info``.
BUILD_EMPTY_WHEEL_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: the built wheel holds no file outside .dist-info; "
    "read as a failed discovery",
)
#: A build that could not start, or a wheel that could not be read.
BUILD_UNUSABLE_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: the build could not run or its wheel could not be "
    "read; %(failure)s",
)

#: A build that gave no wheel to read.
BUILD_FAILED: Final = Message(
    code="build-failed",
    condition="build-failed",
    lines=(
        BUILD_INTERPRETER_LINE,
        BUILD_EXIT_LINE,
        BUILD_WHEEL_COUNT_LINE,
        BUILD_EMPTY_WHEEL_LINE,
        BUILD_UNUSABLE_LINE,
    ),
    summary="The --allow-build build gave no wheel to read: no Python "
    "interpreter to run PyPA build with, the build exited with an error "
    "(its last line of output shown, a credential in it masked), it wrote "
    "no wheel or several, its wheel holds no file outside .dist-info, or "
    "the build could not start or its wheel could not be read (the reason "
    "shown). A build cut off by --build-timeout is build-timeout; PyPA "
    "build not installed is library-missing.",
    did="Went on without the build: the file discovery line that follows "
    "says which fallback listed the files.",
    effect="weaker",
    actor="user",
    advice="Tell the user the build failed and why, as the line says, and "
    "that the file list comes from the fallback the next line names. They "
    "fix the build (python -m build --wheel in the project shows its whole "
    "output) and run again, or drop --allow-build. Do not change the "
    f"project or run its build for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

_TIMED_OUT: Final = (
    "DIR=%(dir)s: the build timed out after %(seconds)s seconds (--build-timeout); "
)
#: A build stopped at its deadline, every process of it gone.
BUILD_TIMED_OUT_LINE: Final = Line(
    level="WARNING", template=f"{_TIMED_OUT}its process tree was stopped"
)
#: The same, a process of it perhaps still running.
BUILD_TIMED_OUT_UNCONFIRMED_LINE: Final = Line(
    level="WARNING",
    template=f"{_TIMED_OUT}could not confirm its process tree stopped",
)

#: A build that did not end within --build-timeout.
BUILD_TIMEOUT: Final = Message(
    code="build-timeout",
    condition="timeout",
    lines=(BUILD_TIMED_OUT_LINE, BUILD_TIMED_OUT_UNCONFIRMED_LINE),
    summary="The --allow-build build ran longer than --build-timeout allows "
    "(a slow build, or one waiting for the network or for input). Its "
    "process tree was stopped; on the second line Pitloom could not "
    "confirm every process of it ended.",
    did="Went on without the build: the file discovery line that follows "
    "says which fallback listed the files.",
    effect="weaker",
    actor="user",
    advice="Tell the user the build was stopped at the time limit. They run "
    "again with a larger --build-timeout for a slow build, or check that "
    "the build does not wait for input; after the second line, processes "
    "of the build may still run, and they check for them. Do not raise "
    f"the limit or stop processes for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

_LEFT: Final = "the build left processes running (process group %(process_group)s); "

#: Processes the build left, killed.
PROCESSES_KILLED_LINE: Final = Line(level="INFO", template=f"{_LEFT}killed")
#: Processes the build left, perhaps still running.
PROCESSES_UNCONFIRMED_LINE: Final = Line(
    level="WARNING", template=f"{_LEFT}could not confirm they stopped"
)

#: Processes that outlived the build (POSIX).
BUILD_PROCESSES_UNSAFE: Final = Message(
    code="build-processes-unsafe",
    condition="unsafe",
    lines=(PROCESSES_KILLED_LINE, PROCESSES_UNCONFIRMED_LINE),
    summary="The build ended and left processes it started still running in "
    "its process group (a backend's background helper): third-party code "
    "that would go on writing into the build's directory. POSIX only.",
    did="Killed them before removing the build's directory (the INFO: line); "
    "on the WARNING: line, could not confirm they stopped. The build's "
    "result is read as usual.",
    effect="none",
    actor="user",
    advice="Tell the user only of the WARNING: line: processes the build "
    "started may still be running, in the process group the line names; "
    "they check and stop them. The INFO: line needs nothing. Do not stop "
    f"processes for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A temporary directory left behind.
TEMP_DIR_LEFT_LINE: Final = Line(
    level="WARNING",
    template="DIR=%(dir)s: could not be fully removed; left in the system "
    "temp directory",
)

#: A temporary directory Pitloom could not remove.
TEMP_DIR_UNWRITABLE: Final = Message(
    code="temp-dir-unwritable",
    condition="unwritable",
    lines=(TEMP_DIR_LEFT_LINE,),
    summary="A temporary directory Pitloom made (a download, a Git checkout, "
    "a build, a copy of a model file, the build hook's staged SBOM) could "
    "not be fully removed: a file in it still open (Windows), or no "
    "permission to remove it. The line names the directory by its name, "
    "not its path: it is in the system temp directory. The prefix says "
    "which step made it.",
    did="Left what remained; the run goes on and its output is unchanged.",
    effect="none",
    actor="user",
    advice="Tell the user a temporary directory was left behind, as the line "
    "names it; they delete it from the system temp directory once nothing "
    f"uses it. Do not delete files for them; {ASK_FIRST}",
    subject_key="DIR",
    since=_SINCE,
)

_EXITING: Final = "%(activity)s; exiting after cleanup"
#: A signal while the activity ran.
INTERRUPTED_DURING_LINE: Final = Line(
    level="WARNING", template=f"received %(signal)s during {_EXITING}"
)
#: A signal after the activity, while its result was in use.
INTERRUPTED_AFTER_LINE: Final = Line(
    level="WARNING", template=f"received %(signal)s after {_EXITING}"
)
#: Ctrl-C.
INTERRUPTED_ERROR_LINE: Final = Line(level="ERROR", template="interrupted")

#: Pitloom asked to stop.
INTERRUPTED: Final = Message(
    code="interrupted",
    condition="interrupted",
    lines=(INTERRUPTED_DURING_LINE, INTERRUPTED_AFTER_LINE, INTERRUPTED_ERROR_LINE),
    summary="Pitloom was asked to stop. The WARNING: lines: a termination "
    "signal (SIGTERM, SIGHUP, or SIGBREAK for Ctrl-Break) came while a "
    "build or the copy of a model file out of a wheel ran, or after it "
    "while its temporary directories were in use; the process then ends by "
    "that signal (exit status 143 for SIGTERM). The ERROR: line: Ctrl-C "
    "(exit status 130).",
    did="Stopped the run (a build or a model file copy, when one was running), "
    "removed its temporary directories and wrote no SBOM.",
    effect="not-written",
    actor="user",
    advice="Tell the user the run was stopped before it wrote an SBOM. They "
    f"run it again when ready. Do not run it again for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (
    BUILD_CODE_UNSAFE,
    BUILD_FAILED,
    BUILD_TIMEOUT,
    BUILD_PROCESSES_UNSAFE,
    TEMP_DIR_UNWRITABLE,
    INTERRUPTED,
)
