# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""File discovery, which lists the files a project's wheel would hold from
its static configuration, without a build: a discoverer that failed
(``file-discovery-unusable``), a list only a build can give
(``file-discovery-needs-build``) and two files that map to one wheel path
(``file-discovery-conflict``). Each is a ``WARNING``; the SBOM is written.

See also: :mod:`pitloom.messages.file_discovery` (the public names),
:mod:`pitloom.messages._metadata_say` (:func:`warn_discovery`) and
:mod:`pitloom.core._models_wheel_dispatch` (the dispatch).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._surface import Twins
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The tail of a line whose fallback is Hatchling's heuristic.
_HEURISTIC: Final = "; Hatchling heuristic used, file list may be inaccurate"
#: The condition of a line whose project has no [project] table.
_NO_PROJECT: Final = " and no [project] table; file discovery unsupported"
#: A build-backend no discoverer reads.
_NOT_AWARE: Final = "file discovery not backend-aware for build-backend %(backend)s"
#: What the user may pass, and why only for a trusted project.
_ALLOW_BUILD: Final = (
    "With --allow-build, Pitloom builds the wheel and lists the files the "
    "build wrote, which runs the project's build code: only for a project "
    "they trust."
)
#: What every discovery line leaves to the user.
_NO_RUN: Final = f"Do not pass --allow-build or edit the project for them; {ASK_FIRST}"
#: What the SBOM holds when discovery gives up.
_UNSUPPORTED: Final = (
    "With a fallback, listed the files the Hatchling heuristic finds, which "
    "may miss or add some; with none (no [project] table), listed no "
    "package files."
)


def _line(template: str) -> Line:
    """The ``WARNING`` line naming the project directory, then *template*."""
    return Line(level="WARNING", template=f"DIR=%(dir)s: {template}")


#: A discoverer that raised; the failure is its own.
FAILED_LINE: Final = _line("%(discoverer)s file discovery failed; %(error)s")
#: A discoverer failed, said above; the Hatchling heuristic follows.
FAILED_HEURISTIC_LINE: Final = _line(f"file discovery failed{_HEURISTIC}")
#: A discoverer failed, said above, and no [project] table to fall back on.
FAILED_NO_PROJECT_LINE: Final = _line(f"file discovery failed{_NO_PROJECT}")
#: A backend's static config that its discoverer could not introspect.
INTROSPECTION_LINE: Final = _line(
    f"%(discoverer)s static config failed introspection{_NO_PROJECT}"
)
#: setuptools found several top-level packages or modules.
PACKAGES_AMBIGUOUS_LINE: Final = _line(
    "setuptools package auto-discovery is ambiguous; %(error)s"
)

FILE_DISCOVERY_UNUSABLE: Final = Message(
    code="file-discovery-unusable",
    condition="unusable",
    lines=(
        FAILED_LINE,
        FAILED_HEURISTIC_LINE,
        FAILED_NO_PROJECT_LINE,
        INTROSPECTION_LINE,
        PACKAGES_AMBIGUOUS_LINE,
    ),
    summary="A build backend's file discoverer failed on the project's static "
    "configuration: its own error (in a downloaded repository its type "
    "only), static config it could not introspect, or setuptools finding "
    "several top-level packages or modules where it expects one. The lines "
    "after the failure say which fallback followed.",
    did=_UNSUPPORTED,
    effect="thinner",
    actor="user",
    advice="Tell the user that the SBOM's file list comes from a fallback, or "
    "lists no package files, and the discoverer's failure, as the line says. "
    "A setuptools project names packages or py_modules explicitly in "
    f"pyproject.toml or setup.cfg. {_ALLOW_BUILD} {_NO_RUN}",
    subject_key="DIR",
    since=_SINCE,
)

#: No static config the discoverer reads; the Hatchling heuristic follows.
NO_STATIC_HEURISTIC_LINE: Final = _line(
    f"no static %(discoverer)s config resolvable{_HEURISTIC}"
)
#: No static config and no [project] table: only a build lists the files.
NO_STATIC_LINE: Final = _line(
    f"no static %(discoverer)s config resolvable{_NO_PROJECT}"
)
#: A build-backend no discoverer reads; the Hatchling heuristic follows.
NOT_AWARE_LINE: Final = _line(f"{_NOT_AWARE}{_HEURISTIC}")
#: The same with no [project] table.
NOT_AWARE_NO_PROJECT_LINE: Final = _line(f"{_NOT_AWARE}{_NO_PROJECT}")
#: The same after --allow-build's build-and-read failed.
BUILD_FAILED_LINE: Final = _line(f"build-and-read failed and {_NOT_AWARE}{_HEURISTIC}")
#: The same with no [project] table.
BUILD_FAILED_NO_PROJECT_LINE: Final = _line(
    f"build-and-read failed and {_NOT_AWARE}{_NO_PROJECT}"
)
_UV_OVERRIDES: Final = (
    "[tool.uv.build-backend] overrides the heuristic cannot see; pass "
)
_REAL_BUILD: Final = " for an exact file list from a real build"
#: uv_build overrides the heuristic does not read, without --allow-build.
_UV_OVERRIDES_LINE: Final = _line(f"{_UV_OVERRIDES}--allow-build{_REAL_BUILD}")
#: The same, as each surface asks for a build (the hook never builds; it
#: reads a Hatchling project).
UV_OVERRIDES_LINES: Final = Twins.no_hook(
    cli=_UV_OVERRIDES_LINE,
    library=Line(
        level="WARNING",
        template=f"DIR=%(dir)s: {_UV_OVERRIDES}BuildOptions(allow=True){_REAL_BUILD}",
        since="0.25.0",
    ),
)
#: setup.py passes file-selection keywords imperatively.
IMPERATIVE_LINE: Final = _line(
    "setup.py passes %(kwargs)s imperatively; file list read from static "
    "config may be incomplete"
)
#: Flit's external-data with a version only importing the module gives.
FLIT_EXTERNAL_DATA_LINE: Final = _line(
    "no static version for [tool.flit.external-data] without running the "
    "module; external-data files left out"
)

FILE_DISCOVERY_NEEDS_BUILD: Final = Message(
    code="file-discovery-needs-build",
    condition="needs-build",
    lines=(
        NO_STATIC_HEURISTIC_LINE,
        NO_STATIC_LINE,
        NOT_AWARE_LINE,
        NOT_AWARE_NO_PROJECT_LINE,
        BUILD_FAILED_LINE,
        BUILD_FAILED_NO_PROJECT_LINE,
        *UV_OVERRIDES_LINES.members,
        IMPERATIVE_LINE,
        FLIT_EXTERNAL_DATA_LINE,
    ),
    summary="The project's wheel file list cannot be read from static "
    "configuration; only a build gives it: no static config the backend's "
    "discoverer reads, a build-backend no discoverer reads (the line names "
    "it as declared), uv_build overrides the heuristic does not read, a "
    "setup.py passing file-selection keywords as code, or Flit "
    "external-data with a version only importing the module gives.",
    did=f"{_UNSUPPORTED} A setup.py passing keywords as code keeps the list "
    "static config gives; Flit's external-data files are left out.",
    effect="weaker",
    actor="user",
    advice="Tell the user that the SBOM's file list may differ from what a "
    f"build would put in the wheel, and why, as the line says. {_ALLOW_BUILD} "
    f"{_NO_RUN}",
    subject_key="DIR",
    since=_SINCE,
)

#: Two source files that map to one path in the wheel.
WHEEL_PATH_LINE: Final = _line(
    "two files map to wheel path %(entry)s; kept %(kept)s, dropped %(dropped)s"
)

FILE_DISCOVERY_CONFLICT: Final = Message(
    code="file-discovery-conflict",
    condition="conflict",
    lines=(WHEEL_PATH_LINE,),
    summary="Two different source files of a setuptools project map to the "
    "same path in the wheel (overlapping package_dir entries, for "
    "instance), so a build would keep only one of them.",
    did="Listed the first file found for that path and left the other out.",
    effect="thinner",
    actor="user",
    advice="Tell the user which wheel path two files map to, which was kept "
    "and which dropped, as the line says. They fix the overlapping "
    f"package_dir or packages settings. {_NO_RUN}",
    subject_key="DIR",
    since=_SINCE,
)

ENTRIES: Final = (
    FILE_DISCOVERY_UNUSABLE,
    FILE_DISCOVERY_NEEDS_BUILD,
    FILE_DISCOVERY_CONFLICT,
)
