# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found``: a path named for Pitloom to read does not exist, on
disk or in the repository a Git URL names. ``ERROR`` only: the read raises.

See also: :mod:`pitloom.extract.model_target` (a model file named on its
own), :mod:`pitloom.extract.remote.git_target` and
:mod:`pitloom.extract.remote._git_folder` (a file or folder a Git URL names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: A model file named on its own (a path, or a file of a folder) that does
#: not exist.
MODEL_FILE_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="Model file not found: %(path)s"
)
#: The file a Git URL names is no regular file of the repository at its
#: branch (gone, a folder, or a link, which is not followed).
GIT_FILE_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="No file %(path)s in the repository at that branch."
)
#: The folder a Git URL names is no folder of the repository at its branch.
GIT_FOLDER_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="No folder %(path)s in the repository at that branch."
)

INPUT_NOT_FOUND: Final = Message(
    code="input-not-found",
    condition="not-found",
    lines=(
        MODEL_FILE_NOT_FOUND_LINE,
        GIT_FILE_NOT_FOUND_LINE,
        GIT_FOLDER_NOT_FOUND_LINE,
    ),
    summary="A path named for Pitloom to read does not exist: a model file on "
    "disk, or the file or folder a Git URL names in the repository at its "
    "branch (a link there is not followed, so it counts as absent).",
    did="Wrote no SBOM. A Git URL's error code is git.path-not-found.",
    effect="not-written",
    actor="user",
    advice="Tell the user which path was not found, as the line names it "
    "(for a Git URL, a path in the repository). They check the path, or the "
    "URL's branch and path, and run again. Do not guess another path or "
    "branch and run for them; ask first, and with nobody to ask, report it "
    "only.",
    since="0.24.0",
)

ENTRIES: Final = (INPUT_NOT_FOUND,)
