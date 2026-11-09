# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``config-unsafe``: the ``[tool.pitloom]`` settings of a project fetched
from a Git URL, which Pitloom does not apply: the repository is untrusted.

See also: :func:`pitloom.assemble.generate_git_project_sbom` and
:mod:`pitloom.cli.commands._remote` (the two routes that say it).
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
    since="0.24.0",
)

ENTRIES: Final = (CONFIG_UNSAFE,)
