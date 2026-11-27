# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``input-not-found``: a path named for Pitloom to read does not exist, on
disk or in the repository a Git URL names. ``ERROR``: the read raises, or
the command stops. ``input-not-found/fragment``: a configured SBOM fragment
does not exist, a ``WARNING:`` naming it as configured (``FILE=``): the
merge goes on without it. ``input-not-found/hub``: a Hugging Face model
target the Hub knows no model for (and, spelt as an id, no local path).

See also: :mod:`pitloom.messages._input_not_found_say` (the helpers),
:mod:`pitloom.extract._model_named` (a model file named on its own),
:mod:`pitloom.extract.remote.git_target` and
:mod:`pitloom.extract.remote._git_folder` (a file or directory a Git URL names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._fragments import fragment_lines
from pitloom.messages._types import ASK_FIRST, Line, Message

#: The release that first prints ``input-not-found/fragment``, and each
#: ``input-not-found`` line: the code's lines of 0.23.4 were reworded.
_SINCE: Final = "0.25.0"

#: The file a Git URL names is no regular file of the repository at its
#: branch (gone, a directory, or out of the repository).
GIT_FILE_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="no file %(path)s in the repository at that branch",
    since=_SINCE,
)
#: The file a Git URL names is a symbolic link, which is not followed.
GIT_FILE_IS_LINK_LINE: Final = Line(
    level="ERROR",
    template="file %(path)s in the repository at that branch is a symbolic "
    "link; links are not followed",
    since=_SINCE,
)
#: The directory a Git URL names is no directory of the repository at its
#: branch.
GIT_FOLDER_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="no directory %(path)s in the repository at that branch",
    since=_SINCE,
)

#: A path named for Pitloom to read, of a kind of
#: :data:`~pitloom.messages._field_tables.INPUT_KINDS`, that does not exist.
INPUT_LINE: Final = Line(
    level="ERROR", template="%(input)s not found: %(path)s", since=_SINCE
)
#: The same, where something that is not a file is there.
INPUT_NOT_FILE_LINE: Final = Line(
    level="ERROR",
    template="%(input)s not found: %(path)s is not a file",
    since=_SINCE,
)
#: The same, where something that is not a directory is there.
INPUT_NOT_DIR_LINE: Final = Line(
    level="ERROR",
    template="%(input)s not found: %(path)s is not a directory",
    since=_SINCE,
)
#: A wheel pattern (a glob) that matches no wheel file.
NO_WHEEL_MATCH_LINE: Final = Line(
    level="ERROR",
    template="no wheel file matches %(path)s",
    since=_SINCE,
)
#: A wheel pattern nested too deeply for the standard library's ``glob`` to
#: expand (its recursion limit).
WHEEL_PATTERN_TOO_DEEP_LINE: Final = Line(
    level="ERROR",
    template="no wheel file matches %(path)s: the pattern nests too deeply "
    "to expand; name each wheel file without a pattern",
    since=_SINCE,
)
#: A fragments directory that holds no JSON file.
NO_FRAGMENT_FILE_LINE: Final = Line(
    level="ERROR",
    template="no JSON fragment file in %(path)s",
    since=_SINCE,
)
#: A project directory without the source or data directories ``loom id
#: generate`` reads when no ``PATH`` is given.
NO_ID_PATHS_LINE: Final = Line(
    level="ERROR",
    template="no source or data directory under %(path)s; pass PATH arguments",
    since=_SINCE,
)

INPUT_NOT_FOUND: Final = Message(
    code="input-not-found",
    condition="not-found",
    lines=(
        GIT_FILE_NOT_FOUND_LINE,
        GIT_FILE_IS_LINK_LINE,
        GIT_FOLDER_NOT_FOUND_LINE,
        INPUT_LINE,
        INPUT_NOT_FILE_LINE,
        INPUT_NOT_DIR_LINE,
        NO_WHEEL_MATCH_LINE,
        WHEEL_PATTERN_TOO_DEEP_LINE,
        NO_FRAGMENT_FILE_LINE,
        NO_ID_PATHS_LINE,
        # Said again when a run re-reads its ID registry file to save.
        Line(level="WARNING", template=INPUT_LINE.template, since=_SINCE),
        Line(level="WARNING", template=INPUT_NOT_FILE_LINE.template, since=_SINCE),
    ),
    summary="A path named for Pitloom to read does not exist: a model file, "
    "wheel, sdist, project directory, configuration, ID registry or SBOM file, "
    "or a PATH given to 'loom id generate' to index, on disk "
    "(or something else is there: the line says it is not a file, or not a "
    "directory), the file or directory a Git URL names in the repository at its "
    "branch (a symbolic link there is not followed, so it counts as absent: "
    "its line says it is a link), or a pattern or directory that holds "
    "nothing of what was asked for (or a wheel pattern nested too deeply to "
    "expand: its line says so).",
    did="Wrote nothing: no SBOM is written; for 'loom id', the ID registry "
    "is not written; for 'loom embed-wheel', no wheel is changed; a check "
    "('loom fragment validate', 'loom verify-wheel', 'loom validate-wheel') "
    "checks nothing. The command exits 1 (the Action step fails), the build "
    "hook fails the build, and the library raises FileNotFoundError carrying "
    "the code (IdRegistry.generate for a path to index that is not there), "
    "ValueError for a fragments directory that holds no JSON file, "
    "or RemoteSourceError (code git.path-not-found) for a Git URL's file or "
    "directory. As a WARNING, an ID registry file was gone (or no longer a "
    "file) when a run whose SBOM is already built read it again to save "
    "the ids it added: nothing is saved and the SBOM stands.",
    effect="not-written",
    actor="user",
    advice="Tell the user which path was not found, as the line names it "
    "(for a Git URL, a path in the repository). They check the path, or the "
    "URL's branch and path, and run again. Do not guess another path or "
    f"branch and run for them; {ASK_FIRST}",
    since="0.23.4",
)

#: A configured fragment that does not exist: it is left out of the merge,
#: or, marked required, the merge fails after
#: (:func:`~pitloom.messages._fragments.fragment_lines`).
FRAGMENT_LINE, REQUIRED_FRAGMENT_LINE = fragment_lines("SBOM fragment not found")

INPUT_NOT_FOUND_FRAGMENT: Final = Message(
    code="input-not-found/fragment",
    condition="not-found",
    lines=(FRAGMENT_LINE, REQUIRED_FRAGMENT_LINE),
    summary="An SBOM fragment the project configures ([tool.pitloom.fragment]) "
    "does not exist.",
    did="Merged the SBOM without it, and wrote it (the build hook builds the "
    "wheel). For a fragment marked required, the merge then fails with "
    "fragment-missing and no SBOM is written: the command exits 1, the hook "
    "fails the build, the library raises FragmentMergeError. 'loom fragment "
    "list' lists it with EXISTS=false, and exits 1 for a required one.",
    effect="thinner",
    actor="user",
    advice="Tell the user which fragment was not found, as the line names it. "
    "They create it (run the enrichment that writes it), fix its path in the "
    "configuration, or remove the entry, and run again. Do not edit the "
    f"configuration for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: What a line of ``input-not-found/hub`` ends in: a private model is read
#: with a token (huggingface_hub's ``HF_TOKEN``, else its stored login).
_HUB_TOKEN_ACTION: Final = (
    "if it is private, set HF_TOKEN to a token with access, or run 'hf auth login'"
)
#: A target spelt as a Hugging Face model id (``owner/name``) that is no
#: local path either: *url* is the model's page on the Hub asked.
HUB_ID_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="target not found: %(path)s is no local path, and the Hugging "
    f"Face Hub knows no model %(url)s; {_HUB_TOKEN_ACTION}",
)
#: A Hugging Face model URL the Hub knows no model at.
HUB_URL_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: the Hugging Face Hub knows no such model; "
    f"{_HUB_TOKEN_ACTION}",
)

INPUT_NOT_FOUND_HUB: Final = Message(
    code="input-not-found/hub",
    condition="not-found",
    lines=(HUB_ID_NOT_FOUND_LINE, HUB_URL_NOT_FOUND_LINE),
    summary="A Hugging Face model id (owner/name, no local path) or Hub "
    "model URL names no model the Hub lets this run read: model_info() "
    "said not found, or no model can have the id. Without a token the Hub "
    "answers so for a private model too; a gated model is found.",
    did="Fetched no file and wrote no SBOM: the command exits 1 (the Action "
    "step fails); generate and generate_model_sbom raise RemoteSourceError "
    "(huggingface.repository-not-found) carrying the code. Other Hub "
    "failures warn (download-network-failed, download-timeout).",
    effect="not-written",
    actor="user",
    advice="Tell the user no local path or Hugging Face model was found, "
    "as the line names it. They check the path or the model id, or, for a "
    "private model, set HF_TOKEN or run 'hf auth login', and run again. Do "
    f"not guess another model and run for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (INPUT_NOT_FOUND, INPUT_NOT_FOUND_FRAGMENT, INPUT_NOT_FOUND_HUB)
