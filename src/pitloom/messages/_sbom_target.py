# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a folder named for an SBOM is, or is not: ``target-ambiguous`` (a
folder, or a file that is not a model, read for what it holds),
``project-or-model-not-found`` (neither a Python project nor an AI model
file), ``model-ambiguous`` (several AI model files, none named) and
``project-not-found`` (a project asked for, none found; with
``/model-files``, model files found instead).

See also: :mod:`pitloom.extract.model_target` (the one resolver of a path,
a folder or a folder and a file name to a project or a model).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The release that first prints these codes.
_SINCE: Final = "0.24.0"

#: A file named with its folder that is plainly not a model
#: (``pyproject.toml``): the folder decides.
NAMED_NOT_A_MODEL_LINE: Final = Line(
    level="INFO", template="FILE=%(file)s: not an AI model file; reading its folder"
)
#: A folder with no project config and one model file, for whichever SBOM
#: it holds.
NO_PROJECT_ONE_MODEL_LINE: Final = Line(
    level="INFO",
    template="FILE=%(file)s: no Python project; reading this AI model file",
)
#: A folder with one model file, for a model SBOM.
ONE_MODEL_LINE: Final = Line(
    level="INFO", template="FILE=%(file)s: the one AI model file; reading it"
)
TARGET_AMBIGUOUS: Final = Message(
    code="target-ambiguous",
    condition="ambiguous",
    lines=(NAMED_NOT_A_MODEL_LINE, NO_PROJECT_ONE_MODEL_LINE, ONE_MODEL_LINE),
    summary="The path named for an SBOM is a folder, or a file in it that is "
    "not an AI model (a Git URL of README.md), so it does not say by itself "
    "what the SBOM describes; Pitloom decided by the rule: a project config "
    "makes it a project's, else the folder's one AI model file is read.",
    did="Read what the line names: the folder, or its one model file. The "
    "SBOM describes that file, or the folder's project.",
    effect="none",
    actor="none",
    advice="the SBOM describes what the line names; to describe another file "
    "of the folder, name that file.",
    subject_key="FILE",
    since=_SINCE,
)

#: A folder with no project config and no model file of a supported format.
NO_SBOM_TARGET: Final = Message(
    code="project-or-model-not-found",
    condition="not-found",
    lines=(
        Line(
            level="ERROR",
            template="%(path)s: no Python project (pyproject.toml, setup.cfg or "
            "setup.py) and no AI model file of a supported format; name a "
            "project folder or a model file",
        ),
    ),
    summary="A folder named for an SBOM holds neither a Python project "
    "(pyproject.toml, setup.cfg or setup.py) nor, directly in it, an AI model "
    "file of a supported format.",
    did="Wrote no SBOM. Subfolders are not searched for a model file.",
    effect="not-written",
    actor="user",
    advice="Tell the user the folder has no project and no model file Pitloom "
    "reads. They name the project's folder, or the model file itself (its "
    "path, or for a Git URL the link to the file's page), and generate again. "
    "Do not guess a file or folder and generate for them; ask first, and with "
    "nobody to ask, report it only.",
    since=_SINCE,
)

#: One of the model files of a folder that holds several, said before the
#: refusal, one line each, in sorted order.
AMBIGUOUS_FILE_LINE: Final = Line(
    level="INFO", template="FILE=%(file)s: one of several AI model files"
)
#: The refusal of a folder that holds several model files.
AMBIGUOUS_ERROR_LINE: Final = Line(
    level="ERROR", template="%(path)s: several AI model files%(count)s; name one file"
)
MODEL_AMBIGUOUS: Final = Message(
    code="model-ambiguous",
    condition="ambiguous",
    lines=(AMBIGUOUS_FILE_LINE, AMBIGUOUS_ERROR_LINE),
    summary="A folder named for an AI model SBOM holds several AI model files "
    "(or too many files a model could be to look at), and no file was named: "
    "one SBOM describes one model.",
    did="Wrote no SBOM. One INFO line per model file found names it, in "
    "sorted order, before the error; a folder of more files a model could be "
    "than its cap is not read, said first in one over-cap WARNING instead.",
    effect="not-written",
    actor="user",
    advice="Tell the user which model files the folder holds, as the INFO "
    "lines name them. They name the one they want (its path, or for a Git URL "
    "the link to the file's page) and generate again, once per model. Do not "
    "pick a file and generate for them; ask first, and with nobody to ask, "
    "report it only.",
    subject_key="FILE",
    since=_SINCE,
)

#: A folder read as a Python project that holds no project config.
PROJECT_NOT_FOUND_LINE: Final = Line(
    level="ERROR",
    template="No pyproject.toml, setup.cfg, or setup.py found in %(path)s",
)
PROJECT_NOT_FOUND: Final = Message(
    code="project-not-found",
    condition="not-found",
    lines=(PROJECT_NOT_FOUND_LINE,),
    summary="A folder read as a Python project holds no project config "
    "(pyproject.toml, setup.cfg or setup.py).",
    did="Wrote no SBOM. Subfolders are not searched; for a Git URL whose "
    "folders below hold projects, the error names them after the line.",
    effect="not-written",
    actor="user",
    advice="Tell the user the folder holds no Python project, as the line "
    "names it. They name the project's folder (for a monorepo, the "
    "sub-project's folder the error names, if any) and generate again. Do "
    "not guess a folder and generate for them; ask first, and with nobody to "
    "ask, report it only.",
    since=_SINCE,
)

#: A folder whose project was asked for, holding no project config and
#: files whose names could be models (a Git URL only).
MODEL_FILES_LINE: Final = Line(
    level="ERROR",
    template="No pyproject.toml, setup.cfg, or setup.py found in %(path)s; it "
    "holds files that may be AI models (%(files)s): use 'loom model <url>' or "
    "'loom generate <url>'",
)
PROJECT_NOT_FOUND_MODEL_FILES: Final = Message(
    code="project-not-found/model-files",
    condition="not-found",
    lines=(MODEL_FILES_LINE,),
    summary="A project SBOM was asked for a folder of a Git URL that holds no "
    "Python project (pyproject.toml, setup.cfg or setup.py) but files whose "
    "names could be AI models.",
    did="Wrote no SBOM; no file was read. The error code is git.no-project.",
    effect="not-written",
    actor="user",
    advice="Tell the user the folder has no project but may hold AI models, "
    "as the line names them. For a model SBOM they run loom model or loom "
    "generate on the same URL (generate_git_sbom in the library). Do not run "
    "it for them; ask first, and with nobody to ask, report it only.",
    since=_SINCE,
)

ENTRIES: Final = (
    TARGET_AMBIGUOUS,
    NO_SBOM_TARGET,
    MODEL_AMBIGUOUS,
    PROJECT_NOT_FOUND,
    PROJECT_NOT_FOUND_MODEL_FILES,
)
