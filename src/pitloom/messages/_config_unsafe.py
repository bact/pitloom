# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``config-unsafe``: the ``[tool.pitloom]`` settings of a project fetched
from a Git URL, which Pitloom does not apply: the repository is untrusted;
``config-unsafe/build-code``: the settings of its build configuration that
would have a file discovery run the repository's own code.

See also: :func:`pitloom.assemble.generate_git_project_sbom` and
:mod:`pitloom.cli.commands._remote` (the two routes that say the first),
:func:`pitloom.core._models_wheel_clone.warn_build_code_ignored` (the second).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: Said when no ``--config`` (``pitloom_config=``) is given.
CONFIG_UNSAFE_REMOTE_LINE: Final = Line(
    level="INFO",
    template="Git source: the repository's own [tool.pitloom] settings are "
    "ignored (untrusted); --config or pitloom_config= applies",
)

CONFIG_UNSAFE: Final = Message(
    code="config-unsafe",
    condition="unsafe",
    lines=(CONFIG_UNSAFE_REMOTE_LINE,),
    summary="The [tool.pitloom] settings of a project fetched from a Git URL, "
    "if it has any, are not applied: they could point Pitloom at files, a "
    "registry or the network as the repository chooses, and the repository "
    "is untrusted.",
    did="Did not apply them: the run uses Pitloom's defaults, or the settings "
    "of --config (pitloom_config= in the library) when given, which also "
    "silences this line.",
    effect="none",
    actor="none",
    advice="the SBOM is generated with the defaults; settings the user trusts "
    "go in a file they pass with --config.",
    since="0.23.4",
)

CONFIG_UNSAFE_BUILD_CODE: Final = Message(
    code="config-unsafe/build-code",
    condition="unsafe",
    lines=(
        Line(
            level="WARNING",
            template="FILE=%(file)s: build-time code of the downloaded "
            "repository is not run; %(settings)s ignored",
        ),
    ),
    summary="The build configuration of a project fetched from a Git URL "
    "names Python code of the repository that listing the wheel's files "
    "would run: a Hatchling metadata hook, a setuptools cmdclass or attr "
    "version, a PDM build hook (pdm_build.py or custom-hook) or "
    "run-setuptools. The repository is untrusted, so that code is not run. "
    "The line names the file that holds the settings and the settings "
    "ignored.",
    did="Ignored those settings: no code of the repository ran, and the "
    "wheel's files were listed from the rest of the build configuration, "
    "which may miss a file that code would add.",
    effect="weaker",
    actor="user",
    advice="Tell the user that the repository's build configuration names "
    "code that Pitloom does not run on a downloaded repository, so the file "
    "list may miss what it would add. To have it, they clone the repository, "
    "review that code, and generate from the local copy. Do not clone or run "
    "that code for them; ask first, and with nobody to ask, report it only.",
    subject_key="FILE",
    since="0.23.4",
)

ENTRIES: Final = (CONFIG_UNSAFE, CONFIG_UNSAFE_BUILD_CODE)
