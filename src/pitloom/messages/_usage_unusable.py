# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A file the usage scan does not read for its name: ``usage-unusable``;
and the hint that the scan is off (:data:`USAGE_HINTS`, a summary).

The scan reads a file as Python only when its name ends in ``.py``, which is
the only extension Python's import system accepts. A name that differs only
in case (``RUN.PY``) is said once as a ``WARNING:``, when a model was found
for it to use.

See also: :mod:`pitloom.extract.scanner` (where it is said) and
:mod:`pitloom.messages._usage_unparseable` (a ``.py`` file that could not be
parsed).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._summary import Summary
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

#: The setting a project's hint names: its own configuration.
USAGE_SETTING_PROJECT: Final = "scan-model-usage = true"
#: The setting a wheel's hint names: a wheel reads no configuration
#: implicitly, so the setting needs one named.
USAGE_SETTING_WHEEL: Final = (
    "scan-model-usage = true in a --config file or pitloom_config"
)


#: What the hint says the scan records, after the setting.
_HINT_START: Final = "Found %(number)s AI model file(s); pass --scan-model-usage"
_HINT_END: Final = "to also record which Python files reference them."
_HINT_MEANING: Final = (
    "Models were found and the usage scan is off: it reads every Python file "
    "for references to them only on request. Said once per run."
)

#: The hint of a project, a sdist or an installed environment.
USAGE_HINT_PROJECT: Final = Summary(
    template=f"{_HINT_START} (or set {USAGE_SETTING_PROJECT}) {_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
#: The hint of a wheel.
USAGE_HINT_WHEEL: Final = Summary(
    template=f"{_HINT_START} (or set {USAGE_SETTING_WHEEL}) {_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)

#: The usage hint, by the setting it names.
USAGE_HINTS: Final[Mapping[str, Summary]] = MappingProxyType(
    {
        USAGE_SETTING_PROJECT: USAGE_HINT_PROJECT,
        USAGE_SETTING_WHEEL: USAGE_HINT_WHEEL,
    }
)

SUMMARIES: Final = (USAGE_HINT_PROJECT, USAGE_HINT_WHEEL)
