# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A target given to a command that is not of the kind the command reads
(``target-wrong-format``: a Hugging Face model given to ``loom project``, a
file not named ``.whl`` given as a wheel), and a Hugging Face target that is
neither a Hub URL nor a model id (``hf-url-invalid``). ``ERROR`` only.

See also: :mod:`pitloom.cli.commands.project`,
:mod:`pitloom.core.wheel_dist_info` and
:mod:`pitloom.extract.remote.huggingface`.
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.1"

#: A Hugging Face model URL given to ``loom project``.
HUB_MODEL_NOT_PROJECT_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: a Hugging Face model, not a project; use 'loom model'",
)
#: A file given as a wheel that is not named ``.whl``.
NOT_A_WHEEL_LINE: Final = Line(level="ERROR", template="FILE=%(file)s: not a .whl file")

TARGET_WRONG_FORMAT: Final = Message(
    code="target-wrong-format",
    condition="wrong-format",
    lines=(HUB_MODEL_NOT_PROJECT_LINE, NOT_A_WHEEL_LINE),
    summary="The target given is not of the kind the command reads: a Hugging "
    "Face model given to 'loom project', or a file not named .whl given as a "
    "wheel ('loom wheel', 'embed-wheel', 'verify-wheel', 'validate-wheel').",
    did="Read nothing of it: the command exits 1; the library raises "
    "ValueError carrying the code (generate_project_sbom and "
    "generate_git_project_sbom for a Hugging Face model URL, "
    "generate_wheel_sbom for a file not named .whl).",
    effect="not-written",
    actor="caller",
    advice="The caller may run the command the line names, or give a wheel "
    "file (a built .whl), and run again.",
    since=_SINCE,
)

#: A Hugging Face target that is neither a Hub URL nor a model id.
HF_URL_LINE: Final = Line(
    level="ERROR",
    template="URL=%(url)s: not a valid Hugging Face URL or model ID",
)

HF_URL_INVALID: Final = Message(
    code="hf-url-invalid",
    condition="invalid",
    lines=(HF_URL_LINE,),
    summary="A Hugging Face target is neither a Hub model URL "
    "(https://huggingface.co/<owner>/<name>) nor a model id (<owner>/<name>).",
    did="Read nothing and sent no request: 'loom model', 'loom project' and "
    "'loom generate' exit 1; generate, generate_model_sbom, "
    "generate_project_sbom, generate_git_project_sbom and read_huggingface "
    "raise ValueError carrying the code. An http(s) URL on huggingface.co or "
    "hf.co that is no Space or dataset is taken as a model URL, so a malformed one "
    "says this, not that a model file is not found.",
    effect="not-written",
    actor="user",
    advice="Tell the user the URL or id was not read, as the line gives it. "
    "They check it and run again. Do not guess another model and run for "
    "them; ask first, and with nobody to ask, report it only.",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (TARGET_WRONG_FORMAT, HF_URL_INVALID)
