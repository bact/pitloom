# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a directory named for an SBOM is, or is not: ``target-ambiguous`` (a
directory, or a file that is not a model, read for what it holds; with
``/git-page``, what a Git URL names; with ``/hf-url``, what a Hugging Face
URL names),
``project-or-model-not-found`` (neither a Python project nor an AI model
file), ``model-ambiguous`` (several AI model files, none named; with
``/over-cap``, too many files a model could be to look at) and
``project-not-found`` (a project asked for, none found; with
``/model-files``, model files found instead). After a Git URL's directory,
the last two name the subdirectories that hold a project.

See also: :mod:`pitloom.extract.model_target` (the one resolver of a path,
a directory or a directory and a file name to a project or a model).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

#: The release that first prints these codes.
_SINCE: Final = "0.23.4"
#: The release that first prints the 0.23.4 lines as reworded (subject
#: first, lower case, "directory").
_REWORDED_SINCE: Final = "0.25.0"

#: A file named with its folder whose name no model file has and that is
#: plainly not a model (``pyproject.toml``), or is missing or a link: the
#: folder decides.
NAMED_NOT_A_MODEL_LINE: Final = Line(
    level="INFO",
    template="FILE=%(file)s: not an AI model file; reading its directory",
    since=_REWORDED_SINCE,
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
    summary="The path named for an SBOM is a directory, or a file in it whose "
    "name no AI model file has and that is not one, or is missing (a Git URL "
    "of README.md), so it does not say by itself "
    "what the SBOM describes; Pitloom decided by the rule: a project config "
    "makes it a project's, else the directory's one AI model file is read.",
    did="Read what the line names: the directory, or its one model file. The "
    "SBOM describes that file, or the directory's project.",
    effect="none",
    actor="none",
    advice="the SBOM describes what the line names; to describe another file "
    "of the directory, name that file.",
    subject_key="FILE",
    since=_SINCE,
)

#: The release that first prints the Git URL lines.
_GIT_SINCE: Final = "0.25.0"

_GIT_PAGE_HEAD: Final = "URL=%(url)s: read as repository %(target)s"
#: A Git URL naming its repository alone, in another spelling (a page URL,
#: a trailing slash).
GIT_PAGE_LINE: Final = Line(level="INFO", template=_GIT_PAGE_HEAD)
#: A Git URL naming a branch, tag or commit of its repository.
GIT_PAGE_REF_LINE: Final = Line(
    level="INFO", template=f"{_GIT_PAGE_HEAD}, %(ref_kind)s %(ref)s"
)
#: A Git URL naming a folder of its repository.
GIT_PAGE_FOLDER_LINE: Final = Line(
    level="INFO", template=f"{_GIT_PAGE_HEAD}, directory %(path)s"
)
#: A Git URL naming a branch, tag or commit and a folder.
GIT_PAGE_REF_FOLDER_LINE: Final = Line(
    level="INFO", template=f"{_GIT_PAGE_HEAD}, %(ref_kind)s %(ref)s, directory %(path)s"
)
#: A Git URL that is not a repository's clone URL, read as the repository its
#: page names.
GIT_PAGE_NOT_REPO_LINE: Final = Line(
    level="INFO",
    template="URL=%(url)s: not a repository; read as repository %(target)s",
)
#: A Git URL of a folder's page that names a file.
GIT_PAGE_FILE_LINE: Final = Line(
    level="INFO",
    template="URL=%(url)s: %(path)s is a file, not a directory; read as the file named",
)
#: A Git URL of a file's page that names a folder.
GIT_PAGE_DIR_LINE: Final = Line(
    level="INFO",
    template="URL=%(url)s: %(path)s is a directory, not a file; reading it",
)
TARGET_AMBIGUOUS_GIT_PAGE: Final = Message(
    code="target-ambiguous/git-page",
    condition="ambiguous",
    lines=(
        GIT_PAGE_LINE,
        GIT_PAGE_REF_LINE,
        GIT_PAGE_FOLDER_LINE,
        GIT_PAGE_REF_FOLDER_LINE,
        GIT_PAGE_NOT_REPO_LINE,
        GIT_PAGE_FILE_LINE,
        GIT_PAGE_DIR_LINE,
    ),
    summary="A Git URL names more than a repository, or names it in another "
    "spelling: a web page of a repository (with a branch, tag or commit, a "
    "directory or a file), a URL that is not itself a repository's, or a page "
    "of a file that is a directory (or of a directory that is a file). Pitloom "
    "decided by its rule what the URL names.",
    did="Read what the line names: the repository, at the branch, tag or "
    "commit, and the directory or file, it names.",
    effect="none",
    actor="none",
    advice="the SBOM describes what the line names; to describe another "
    "version or directory, give its URL.",
    subject_key="URL",
    since=_GIT_SINCE,
)

#: A Hugging Face model URL spelt otherwise than the Hub's own.
HF_URL_REWRITE_LINE: Final = Line(
    level="INFO", template="URL=%(url)s: read as Hugging Face model %(target)s"
)
TARGET_AMBIGUOUS_HF_URL: Final = Message(
    code="target-ambiguous/hf-url",
    condition="ambiguous",
    lines=(HF_URL_REWRITE_LINE,),
    summary="A Hugging Face model URL spelt otherwise than "
    "https://huggingface.co/<owner>/<name> (hf.co, www.huggingface.co, "
    "http://, a scheme or host in another case). Pitloom decided by its "
    "rule which model it names.",
    did="Read the model the line names, from the Hub the run asks "
    "(https://huggingface.co unless HF_ENDPOINT names another).",
    effect="none",
    actor="none",
    advice="the SBOM describes the model the line names; to describe "
    "another, give its URL.",
    subject_key="URL",
    since=_GIT_SINCE,
)

#: What a directory with no project config holds none of.
_NO_PROJECT_HEAD: Final = (
    "%(path)s: no Python project (pyproject.toml, setup.cfg or setup.py)"
)
_NO_TARGET_HEAD: Final = (
    f"{_NO_PROJECT_HEAD} and no AI model file of a supported format"
)
#: The advice after a project's or a model's absence in a Git URL whose
#: subfolders hold a project: the repository read whole.
_SUBFOLDERS_WHOLE: Final = (
    "; Python projects are in subdirectories (%(folders)s); give the URL of one of them"
)
#: The same, a folder of the repository read.
_SUBFOLDERS_FOLDER: Final = (
    "; Python projects are in subdirectories (%(folders)s); Pitloom reads the "
    "directory in the URL only"
)
#: A Git URL's whole repository, neither a project nor a model, with
#: subfolders that hold a project.
NO_TARGET_HINT_LINE: Final = Line(
    level="ERROR", template=_NO_TARGET_HEAD + _SUBFOLDERS_WHOLE, since=_GIT_SINCE
)
#: The same for a folder of the repository the URL names.
NO_TARGET_FOLDER_HINT_LINE: Final = Line(
    level="ERROR", template=_NO_TARGET_HEAD + _SUBFOLDERS_FOLDER, since=_GIT_SINCE
)

#: A folder with no project config and no model file of a supported format.
NO_SBOM_TARGET: Final = Message(
    code="project-or-model-not-found",
    condition="not-found",
    lines=(
        Line(
            level="ERROR",
            template=f"{_NO_TARGET_HEAD}; name a project directory or a model file",
            since=_REWORDED_SINCE,
        ),
        NO_TARGET_HINT_LINE,
        NO_TARGET_FOLDER_HINT_LINE,
    ),
    summary="A directory named for an SBOM holds neither a Python project "
    "(pyproject.toml, setup.cfg or setup.py) nor, directly in it, an AI model "
    "file of a supported format.",
    did="Wrote no SBOM. Subdirectories are not searched for a model file; for a "
    "Git URL whose subdirectories hold a project, the line names them.",
    effect="not-written",
    actor="user",
    advice="Tell the user the directory has no project and no model file Pitloom "
    "reads. They name the project's directory, or the model file itself (its "
    "path, or for a Git URL the link to the file's page), and generate again. "
    f"Do not guess a file or directory and generate for them; {ASK_FIRST}",
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
    summary="A directory named for an AI model SBOM holds several AI model files, "
    "and no file was named: one SBOM describes one model.",
    did="Wrote no SBOM. One INFO line per model file found names it, in "
    "sorted order, before the error.",
    effect="not-written",
    actor="user",
    advice="Tell the user which model files the directory holds, as the INFO "
    "lines name them. They name the one they want (its path, or for a Git URL "
    "the link to the file's page) and generate again, once per model. Do not "
    f"pick a file and generate for them; {ASK_FIRST}",
    subject_key="FILE",
    since=_SINCE,
)

#: The refusal of a folder with more files whose names could be models than
#: the cap: none was read, so none is known to be one.
OVER_CAP_ERROR_LINE: Final = Line(
    level="ERROR",
    template="%(path)s: more than %(limit)s files that could be AI models, none "
    "read; name one file",
)
MODEL_AMBIGUOUS_OVER_CAP: Final = Message(
    code="model-ambiguous/over-cap",
    condition="ambiguous",
    lines=(OVER_CAP_ERROR_LINE,),
    summary="A directory named for an AI model SBOM holds more files whose names "
    "could be AI models than its cap, and no file was named: which of "
    "them are models is not known, and one SBOM describes one model.",
    did="Wrote no SBOM; no file of the directory was read, said first in one "
    "over-cap WARNING.",
    effect="not-written",
    actor="user",
    advice="Tell the user the directory holds too many files that could be "
    "models for Pitloom to look at. They name the one model file they want "
    "(its path, or for a Git URL the link to the file's page), or a directory "
    "holding only it, and generate again. Do not pick a file and generate for "
    f"them; {ASK_FIRST}",
    since=_SINCE,
)

#: A folder read as a Python project that holds no project config.
PROJECT_NOT_FOUND_LINE: Final = Line(
    level="ERROR", template=_NO_PROJECT_HEAD, since=_REWORDED_SINCE
)
#: A Git URL's whole repository with no project config, with subfolders that
#: hold a project.
PROJECT_HINT_LINE: Final = Line(
    level="ERROR",
    template=PROJECT_NOT_FOUND_LINE.template + _SUBFOLDERS_WHOLE,
    since=_GIT_SINCE,
)
#: The same for a folder of the repository the URL names.
PROJECT_FOLDER_HINT_LINE: Final = Line(
    level="ERROR",
    template=PROJECT_NOT_FOUND_LINE.template + _SUBFOLDERS_FOLDER,
    since=_GIT_SINCE,
)
PROJECT_NOT_FOUND: Final = Message(
    code="project-not-found",
    condition="not-found",
    lines=(PROJECT_NOT_FOUND_LINE, PROJECT_HINT_LINE, PROJECT_FOLDER_HINT_LINE),
    summary="A directory read as a Python project holds no project config "
    "(pyproject.toml, setup.cfg or setup.py).",
    did="Wrote no SBOM. Subdirectories are not searched; for a Git URL whose "
    "subdirectories hold a project, the line names them (git.no-project).",
    effect="not-written",
    actor="user",
    advice="Tell the user the directory holds no Python project, as the line "
    "names it. They name the project's directory (for a monorepo, the "
    "sub-project's directory the error names, if any) and generate again. Do "
    f"not guess a directory and generate for them; {ASK_FIRST}",
    since=_SINCE,
)

#: A folder whose project was asked for, holding no project config and
#: files whose names could be models (a Git URL only).
MODEL_FILES_LINE: Final = Line(
    level="ERROR",
    template=f"{_NO_PROJECT_HEAD}; it holds files that may be AI models "
    "(%(files)s): use 'loom model <url>' or 'loom generate <url>'",
    since=_REWORDED_SINCE,
)
PROJECT_NOT_FOUND_MODEL_FILES: Final = Message(
    code="project-not-found/model-files",
    condition="not-found",
    lines=(MODEL_FILES_LINE,),
    summary="A project SBOM was asked for a directory of a Git URL that holds no "
    "Python project (pyproject.toml, setup.cfg or setup.py) but files whose "
    "names could be AI models.",
    did="Wrote no SBOM; no file was read. The error code is git.no-project.",
    effect="not-written",
    actor="user",
    advice="Tell the user the directory has no project but may hold AI models, "
    "as the line names them. For a model SBOM they run loom model or loom "
    "generate on the same URL (generate_git_sbom in the library). Do not run "
    f"it for them; {ASK_FIRST}",
    since=_SINCE,
)

ENTRIES: Final = (
    TARGET_AMBIGUOUS,
    TARGET_AMBIGUOUS_GIT_PAGE,
    TARGET_AMBIGUOUS_HF_URL,
    NO_SBOM_TARGET,
    MODEL_AMBIGUOUS,
    MODEL_AMBIGUOUS_OVER_CAP,
    PROJECT_NOT_FOUND,
    PROJECT_NOT_FOUND_MODEL_FILES,
)
