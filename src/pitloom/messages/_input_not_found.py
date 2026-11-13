# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found``: a path named for Pitloom to read does not exist, on
disk or in the repository a Git URL names. ``ERROR``: the read raises, or
the command stops. ``input-not-found/fragment``: a configured SBOM fragment
does not exist, a ``WARNING:``: the merge goes on without it.

See also: :mod:`pitloom.messages._input_not_found_say` (the helpers),
:mod:`pitloom.extract._model_named` (a model file named on its own),
:mod:`pitloom.extract.remote.git_target` and
:mod:`pitloom.extract.remote._git_folder` (a file or folder a Git URL names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The release that first prints ``input-not-found/fragment``, and the lines
#: of ``input-not-found`` after its first four (a model file, a Git URL's
#: file or folder), which print since 0.23.4.
_SINCE: Final = "0.24.1"

#: A model file named on its own (a path, or a file of a folder) that does
#: not exist.
MODEL_FILE_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="Model file not found: %(path)s"
)
#: The file a Git URL names is no regular file of the repository at its
#: branch (gone, a folder, or out of the repository).
GIT_FILE_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="No file %(path)s in the repository at that branch."
)
#: The file a Git URL names is a symbolic link, which is not followed.
GIT_FILE_IS_LINK_LINE: Final = Line(
    level="ERROR",
    template="File %(path)s in the repository at that branch is a symbolic "
    "link; links are not followed.",
)
#: The folder a Git URL names is no folder of the repository at its branch.
GIT_FOLDER_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template="No folder %(path)s in the repository at that branch."
)

#: A path named for Pitloom to read, of a kind of
#: :data:`~pitloom.messages._fields.INPUT_KINDS`, that does not exist.
INPUT_LINE: Final = Line(level="ERROR", template="%(input)s not found: %(path)s")
#: The same, where something that is not a file is there.
INPUT_NOT_FILE_LINE: Final = Line(
    level="ERROR", template="%(input)s not found: %(path)s is not a file"
)
#: The same, where something that is not a directory is there.
INPUT_NOT_DIR_LINE: Final = Line(
    level="ERROR", template="%(input)s not found: %(path)s is not a directory"
)
#: A wheel pattern (a glob) that matches no wheel file.
NO_WHEEL_MATCH_LINE: Final = Line(
    level="ERROR", template="no wheel file matches %(path)s"
)
#: A fragments directory that holds no JSON file.
NO_FRAGMENT_FILE_LINE: Final = Line(
    level="ERROR", template="no JSON fragment file in %(path)s"
)
#: A project directory without the source or data directories ``loom id
#: generate`` reads when no ``PATH`` is given.
NO_ID_PATHS_LINE: Final = Line(
    level="ERROR",
    template="no source or data directory under %(path)s; pass PATH arguments",
)

INPUT_NOT_FOUND: Final = Message(
    code="input-not-found",
    condition="not-found",
    lines=(
        MODEL_FILE_NOT_FOUND_LINE,
        GIT_FILE_NOT_FOUND_LINE,
        GIT_FILE_IS_LINK_LINE,
        GIT_FOLDER_NOT_FOUND_LINE,
        INPUT_LINE,
        INPUT_NOT_FILE_LINE,
        INPUT_NOT_DIR_LINE,
        NO_WHEEL_MATCH_LINE,
        NO_FRAGMENT_FILE_LINE,
        NO_ID_PATHS_LINE,
    ),
    summary="A path named for Pitloom to read does not exist: a model file, "
    "wheel, sdist, project directory, configuration or SBOM file on disk "
    "(or something else is there: the line says it is not a file, or not a "
    "directory), the file or folder a Git URL names in the repository at its "
    "branch (a symbolic link there is not followed, so it counts as absent: "
    "its line says it is a link), or a pattern or directory that holds "
    "nothing of what was asked for. The lines for a model file and for a Git "
    f"URL's file or folder print since 0.23.4, the others since {_SINCE}.",
    did="Wrote no SBOM: the command exits 1, the library raises "
    "FileNotFoundError carrying the code, or ValueError carrying it for a "
    "fragments directory that holds no JSON file. A Git URL's error code is "
    "git.path-not-found.",
    effect="not-written",
    actor="user",
    advice="Tell the user which path was not found, as the line names it "
    "(for a Git URL, a path in the repository). They check the path, or the "
    "URL's branch and path, and run again. Do not guess another path or "
    "branch and run for them; ask first, and with nobody to ask, report it "
    "only.",
    since="0.23.4",
)

#: A configured fragment that does not exist; it is left out of the merge.
FRAGMENT_LINE: Final = Line(
    level="WARNING", template="SBOM fragment not found: %(path)s; not merged"
)
#: The same, for a fragment marked required: the merge fails after.
REQUIRED_FRAGMENT_LINE: Final = Line(
    level="WARNING",
    template="required SBOM fragment not found: %(path)s; the merge will fail",
)

INPUT_NOT_FOUND_FRAGMENT: Final = Message(
    code="input-not-found/fragment",
    condition="not-found",
    lines=(FRAGMENT_LINE, REQUIRED_FRAGMENT_LINE),
    summary="An SBOM fragment the project configures ([tool.pitloom.fragment]) "
    "does not exist.",
    did="Merged the SBOM without it. For a fragment marked required, the "
    "merge then fails with an ERROR: and no SBOM is written; 'loom fragment "
    "list' only reports it.",
    effect="thinner",
    actor="user",
    advice="Tell the user which fragment was not found, as the line names it. "
    "They create it (run the enrichment that writes it), fix its path in the "
    "configuration, or remove the entry, and run again. Do not edit the "
    "configuration for them; ask first, and with nobody to ask, report it "
    "only.",
    since=_SINCE,
)

ENTRIES: Final = (INPUT_NOT_FOUND, INPUT_NOT_FOUND_FRAGMENT)
