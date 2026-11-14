# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file the usage scan does not read for its name: ``usage-unusable``.

The scan reads a file as Python only when its name ends in ``.py``, which is
the only extension Python's import system accepts. A name that differs only
in case (``RUN.PY``) is said once as a ``WARNING:``, when a model was found
for it to use.

See also: :mod:`pitloom.extract.scanner` (where it is said) and
:mod:`pitloom.messages._usage_unparseable` (a ``.py`` file that could not be
parsed).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import ASK_FIRST, Line, Message

USAGE_UNUSABLE: Final = Message(
    code="usage-unusable",
    condition="unusable",
    lines=(
        Line(
            level="WARNING",
            template="FILE=%(file)s: not scanned for usage; only a .py "
            "extension is read as Python",
        ),
    ),
    summary="A file whose extension is .py in other letter case (.PY) was not "
    "read for model usage: Python imports only a lower-case .py file.",
    did="Did not read it, and recorded no usage relationship from it, for any "
    "model. Said once per such file, and only when a model was found.",
    effect="thinner",
    actor="user",
    advice="Tell the user which file was not scanned. If it is a Python "
    "script that uses a model, they rename it to a lower-case .py extension "
    "and generate again; if it is not Python, it needs nothing. Do not "
    f"rename the file for them; {ASK_FIRST}",
    subject_key="FILE",
    since="0.22.1",
)

ENTRIES: Final = (USAGE_UNUSABLE,)
