# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""What the Hatchling build hook (:mod:`pitloom.plugins.hatch`) says about
its own run: a build it makes no SBOM for (``hook-no-effect``, after
:data:`~pitloom.messages.HOOK_STEP_FRAME`) and the SBOM it staged (a
summary, which carries the hook's prefix as a literal: a summary takes no
frame).

See also: :mod:`pitloom.messages._build` (the hook's staging directory,
``temp-dir-unwritable``) and :mod:`pitloom.messages._config` (its
``datetime-unpinned``).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._frames import HOOK_PREFIX
from pitloom.messages._summary import Summary
from pitloom.messages._types import Line, Message

_SINCE: Final = "0.25.0"
_SKIPPING: Final = "; skipping SBOM generation"

#: ``enabled = false`` in the hook's table.
HOOK_DISABLED_LINE: Final = Line(level="INFO", template=f"disabled{_SKIPPING}")
#: A build target other than the wheel (an sdist).
HOOK_NOT_WHEEL_LINE: Final = Line(
    level="INFO", template=f"target %(target)s is not 'wheel'{_SKIPPING}"
)
#: An editable wheel.
HOOK_EDITABLE_LINE: Final = Line(
    level="INFO",
    template="build variant 'editable' skipped; its wheel does not hold the "
    "project's files",
)

HOOK_NO_EFFECT: Final = Message(
    code="hook-no-effect",
    condition="no-effect",
    lines=(HOOK_DISABLED_LINE, HOOK_NOT_WHEEL_LINE, HOOK_EDITABLE_LINE),
    summary="The Hatchling build hook ran for a build it makes no SBOM for: "
    "its table [tool.hatch.build.hooks.pitloom] sets enabled = false, the "
    "build target is not the wheel (an sdist: PEP 770 places an SBOM in a "
    "wheel's .dist-info/sboms/ only), or the wheel is an editable one, which "
    "holds a .pth file, not the project's files the SBOM would list.",
    did="Staged no SBOM for this build; the build goes on.",
    effect="none",
    actor="none",
    advice="Nothing to fix: the build is one the hook leaves alone. For an "
    "SBOM in the wheel, the user builds a regular (not editable) wheel with "
    "the hook enabled; mention it only when they ask why the wheel or sdist "
    "holds no SBOM.",
    since=_SINCE,
)

#: The SBOM staged for the wheel.
HOOK_SBOM_STAGED: Final = Summary(
    template=f"{HOOK_PREFIX}staged SBOM %(path)s (%(number)s fragment(s)); "
    "Hatchling will inject it into .dist-info/sboms/ in the wheel",
    meaning="The build hook made the wheel's SBOM and staged it under the "
    "file name shown, with the number of [tool.pitloom.fragment] files "
    "merged into it; Hatchling places it in the wheel's .dist-info/sboms/ "
    "(PEP 770).",
    topic="build",
)

ENTRIES: Final = (HOOK_NO_EFFECT,)

SUMMARIES: Final = (HOOK_SBOM_STAGED,)
