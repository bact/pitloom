# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``sbom-name-invalid``: an SBOM base name (``sbom-basename``,
``--sbom-basename``) given with white space around it or the
``.spdx3.json`` every writer adds; the base name used is said. A value with
nothing left once both are taken off is refused (``config-invalid``,
``option-invalid``).

See also: :mod:`pitloom.core.file_names` (where it is said) and
:mod:`pitloom.messages.options` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The condition, after where the value was given.
_NOT_BARE: Final = (
    "%(got)s is not a bare file name (white space or a trailing .spdx3.json); "
    "using %(base_name)s"
)

#: A base name from a configuration file.
CONFIG_NAME_LINE: Final = Line(level="WARNING", template=f"%(config_key)s: {_NOT_BARE}")
#: A base name from the command line or a library caller.
OPTION_NAME_LINE: Final = Line(level="WARNING", template=f"%(option)s: {_NOT_BARE}")

SBOM_NAME_INVALID: Final = Message(
    code="sbom-name-invalid",
    condition="invalid",
    lines=(CONFIG_NAME_LINE, OPTION_NAME_LINE),
    summary="An SBOM base name (sbom-basename in a configuration file, "
    "--sbom-basename, a library caller's sbom_basename) has white space "
    "around it or ends in .spdx3.json (any case), which every writer adds "
    "itself. Said once per value and process.",
    did="Used the base name the line names (white space and one trailing "
    ".spdx3.json taken off): the SBOM file is named <value>.spdx3.json.",
    effect="none",
    actor="none",
    advice="Nothing to do: the file is named as intended. To silence the "
    "line, give the base name without white space and without .spdx3.json.",
    since="0.25.0",
)

ENTRIES: Final = (SBOM_NAME_INVALID,)
