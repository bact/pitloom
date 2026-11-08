# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What a folder named for an SBOM is not: ``project-or-model-not-found``
(neither a Python project nor an AI model file) and ``model-ambiguous``
(several AI model files, none named).

See also: :mod:`pitloom.extract.model_target` (the one resolver of a path,
a folder or a folder and a file name to a project or a model).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The release that first prints these codes.
_SINCE: Final = "0.24.0"

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
    "sorted order, before the error.",
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

ENTRIES: Final = (NO_SBOM_TARGET, MODEL_AMBIGUOUS)
