# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The installed environment ``loom env`` could not read:
``environment-unreadable``. ``pipdeptree --json`` lists what is installed;
when it fails to run, exits with an error, or prints what is not its flat
``--json`` list, no SBOM is written. What it printed is third-party text:
the ``output`` field masks a credential in it, cuts it and escapes it.

See also: :mod:`pitloom.messages._environment_say` (the errors),
:mod:`pitloom.extract.env` (where they are raised) and
:mod:`pitloom.messages.dependencies` (the public names).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: What ``loom env`` runs, as its lines name it.
_PIPDEPTREE: Final = "pipdeptree"

#: ``pipdeptree`` exited with an error: its last line of output.
EXITED_LINE: Final = Line(
    level="ERROR",
    template=f"{_PIPDEPTREE} exited with code %(exit_code)s; last output: %(output)s",
)
#: ``pipdeptree`` could not be started (no interpreter at the path).
NOT_RUN_LINE: Final = Line(
    level="ERROR", template=f"could not run {_PIPDEPTREE}; %(failure)s"
)
#: ``pipdeptree`` printed what is not JSON.
NOT_JSON_LINE: Final = Line(
    level="ERROR", template=f"{_PIPDEPTREE} output is not JSON; %(failure)s"
)
#: ``pipdeptree`` printed JSON that is not its flat ``--json`` list.
SHAPE_LINE: Final = Line(
    level="ERROR",
    template=f"{_PIPDEPTREE} output is not its --json list: %(why)s",
)

#: Why a JSON output is not the flat list (:data:`SHAPE_LINE`'s ``why``):
#: a closed table, one per check.
NOT_A_LIST: Final = "expected a JSON list"
NO_PACKAGE_KEY: Final = "expected 'package' with a string 'key' per node"
NO_DEPENDENCY_KEY: Final = "expected 'dependencies' entries with a string 'key'"
SHAPE_PROBLEMS: Final = (NOT_A_LIST, NO_PACKAGE_KEY, NO_DEPENDENCY_KEY)

#: What :data:`EXITED_LINE` says when ``pipdeptree`` printed nothing.
NO_OUTPUT: Final = "(no output)"

ENVIRONMENT_UNREADABLE: Final = Message(
    code="environment-unreadable",
    condition="unreadable",
    lines=(EXITED_LINE, NOT_RUN_LINE, NOT_JSON_LINE, SHAPE_LINE),
    summary="'loom env' (the library: generate_env_sbom) could not read the "
    "installed environment: pipdeptree, which lists it, exited with an error "
    "(the line shows its last line of output: most often 'No module named "
    "pipdeptree' when it is not installed in the interpreter Pitloom runs "
    "under), could not be started, or printed what is not its flat --json "
    "list (a pipdeptree too old or too new, or a wrapper printing other "
    "text).",
    did="Wrote no SBOM: the command exits 1; the library raises RuntimeError "
    "carrying the code.",
    effect="not-written",
    actor="user",
    advice="Tell the user what pipdeptree reported. Most often it is not "
    "installed where Pitloom runs: they install it there (pip install "
    "pipdeptree) and run again. Do not install it for them; ask first, and "
    "with nobody to ask, report it only.",
    since="0.25.0",
)


ENTRIES: Final = (ENVIRONMENT_UNREADABLE,)
