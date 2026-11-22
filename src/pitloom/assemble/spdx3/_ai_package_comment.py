# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``comment`` of a model's ``ai_AIPackage``: the facts SPDX 3.0.1 has
no property for, one line each.

See also: :mod:`pitloom.assemble.spdx3._ai_package` (the package) and
:func:`pitloom.core.model_parameters.with_parameter_count_note` (the
parameter-count line, always first).
"""

from __future__ import annotations

from pitloom.core.ai_metadata import AiModelFormatInfo, AiModelMetadata, cap_model_name
from pitloom.core.model_parameters import with_parameter_count_note

#: The line naming the tool that wrote the model file, as the file names it.
WRITING_TOOL_LINE = "Model file written by: %s"
#: The line listing the model's known biases, ``"; "``-joined.
KNOWN_BIASES_LINE = "Known biases: %s"


def writing_tool_line(info: AiModelFormatInfo) -> str | None:
    """The :data:`WRITING_TOOL_LINE` of *info*'s writing tool and its
    version (white-space runs one space, so it stays one line; capped as a
    model name is), or ``None`` when the file names no tool."""
    named = " ".join(
        " ".join((text or "").split())
        for text in (info.writing_tool, info.writing_tool_version)
    ).strip()
    return WRITING_TOOL_LINE % cap_model_name(named) if named else None


def package_comment(ai_model: AiModelMetadata, has_count: bool) -> str | None:
    """The comment of *ai_model*'s package before provenance appends its
    own: the parameter-count note when *has_count*, the writing tool, then
    the known biases; ``None`` with none of them."""
    biases = ai_model.usage.known_biases
    lines = [
        writing_tool_line(ai_model.format_info),
        KNOWN_BIASES_LINE % "; ".join(biases) if biases else None,
    ]
    return with_parameter_count_note(
        "\n".join(line for line in lines if line) or None, has_count
    )
