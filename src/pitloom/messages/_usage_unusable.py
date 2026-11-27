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
from pitloom.messages._surface import Twins
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

#: The target a usage hint is for: a project (a sdist or an installed
#: environment too), whose own configuration is read, or a wheel, which
#: reads a configuration only when one is named.
USAGE_TARGET_PROJECT: Final = "project"
USAGE_TARGET_WHEEL: Final = "wheel"

#: What the hint says the scan records, after the setting.
_HINT_START: Final = "Found %(number)s AI model file(s); "
_HINT_END: Final = " to also record which Python files reference them."
_HINT_MEANING: Final = (
    "Models were found and the usage scan is off: it reads every Python file "
    "for references to them only on request. Said once per run, naming the "
    "flag, the library parameter (the ConfigOverrides field for "
    "embed_wheel_sbom()) or the [tool.pitloom] key of the surface that runs."
)
#: How each surface turns the scan on.
_PASS_FLAG: Final = "pass --scan-model-usage"
_SET_PARAMETER: Final = "set scan_model_usage=True"
#: The same where settings are ``ConfigOverrides`` fields
#: (``embed_wheel_sbom()``).
_SET_OVERRIDE: Final = "set ConfigOverrides.scan_model_usage=True"
_SETTING: Final = "scan-model-usage = true"

#: A project's hint (a sdist or an installed environment too) on each
#: surface: the project's own configuration is read.
USAGE_HINT_PROJECT_CLI: Final = Summary(
    template=f"{_HINT_START}{_PASS_FLAG} (or set {_SETTING}){_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
USAGE_HINT_PROJECT_LIBRARY: Final = Summary(
    template=f"{_HINT_START}{_SET_PARAMETER} (or set {_SETTING}){_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
USAGE_HINT_PROJECT_OVERRIDES: Final = Summary(
    template=f"{_HINT_START}{_SET_OVERRIDE} (or set {_SETTING}){_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
USAGE_HINT_PROJECT_HOOK: Final = Summary(
    template=f"{_HINT_START}set {_SETTING} in [tool.pitloom]{_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
#: A wheel's hint: a wheel reads a configuration only when one is named.
USAGE_HINT_WHEEL_CLI: Final = Summary(
    template=f"{_HINT_START}{_PASS_FLAG} (or set {_SETTING} in a --config file)"
    f"{_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)
USAGE_HINT_WHEEL_LIBRARY: Final = Summary(
    template=f"{_HINT_START}{_SET_PARAMETER} (or set it in pitloom_config){_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)

USAGE_HINT_WHEEL_OVERRIDES: Final = Summary(
    template=f"{_HINT_START}{_SET_OVERRIDE} (or set it in pitloom_config){_HINT_END}",
    meaning=_HINT_MEANING,
    topic="models",
)

#: The hint, by target, worded for each surface.
USAGE_HINTS: Final[Mapping[str, Twins[Summary]]] = MappingProxyType(
    {
        USAGE_TARGET_PROJECT: Twins(
            cli=USAGE_HINT_PROJECT_CLI,
            library=USAGE_HINT_PROJECT_LIBRARY,
            hook=USAGE_HINT_PROJECT_HOOK,
            overrides=USAGE_HINT_PROJECT_OVERRIDES,
        ),
        # The hook reads its own project, never a wheel.
        USAGE_TARGET_WHEEL: Twins.no_hook(
            cli=USAGE_HINT_WHEEL_CLI,
            library=USAGE_HINT_WHEEL_LIBRARY,
            overrides=USAGE_HINT_WHEEL_OVERRIDES,
        ),
    }
)

SUMMARIES: Final = (
    USAGE_HINT_PROJECT_CLI,
    USAGE_HINT_PROJECT_LIBRARY,
    USAGE_HINT_PROJECT_OVERRIDES,
    USAGE_HINT_PROJECT_HOOK,
    USAGE_HINT_WHEEL_CLI,
    USAGE_HINT_WHEEL_LIBRARY,
    USAGE_HINT_WHEEL_OVERRIDES,
)
