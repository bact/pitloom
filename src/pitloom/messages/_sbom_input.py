# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An SBOM Pitloom was given to read (``embed-wheel --sbom``, ``loom id
import``) that it cannot use: one named as SPDX 3 that is another format
(``sbom-wrong-format``), or one whose content fails a check
(``sbom-invalid``). ``ERROR`` only: nothing is written.

An SBOM that is not UTF-8, not valid JSON or not a JSON object says
``file-unreadable/not-utf8`` and ``json-malformed``, read ``for the SBOM``.

See also: :mod:`pitloom._sbom_format` and :mod:`pitloom._embed_generate`
(the ``--sbom`` reader), :mod:`pitloom.id_registry._sbom_read`.
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

_SINCE: Final = "0.24.1"

#: A file named ``.spdx3.json`` whose content is not SPDX 3 JSON-LD.
NOT_SPDX3_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: named .spdx3.json but not SPDX 3 JSON-LD",
)

SBOM_WRONG_FORMAT: Final = Message(
    code="sbom-wrong-format",
    condition="wrong-format",
    lines=(NOT_SPDX3_LINE,),
    summary="An SBOM given to embed or to import into an ID registry is named "
    "as SPDX 3 JSON-LD (.spdx3.json) but holds another format (a CycloneDX "
    "document, say).",
    did="Wrote nothing: no wheel is changed and no ID registry written; the "
    "command exits 1, the library raises ValueError carrying the code.",
    effect="not-written",
    actor="user",
    advice="Tell the user which file is named as SPDX 3 but is not, as the "
    "line names it. They give the right file, or rename it to match its "
    "format, and run again. Do not rename or convert the file for them; ask "
    "first, and with nobody to ask, report it only.",
    subject_key="FILE",
    since=_SINCE,
)

#: An SBOM that fails ``spdx3-validate`` before it is embedded.
SBOM_NOT_VALID_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: SBOM is not valid; no wheel was written",
)
#: An SBOM whose ``@graph`` is not a list.
SBOM_GRAPH_NOT_LIST_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: SBOM @graph is not a list"
)
#: An SBOM whose ``@graph`` holds something that is not an object.
SBOM_GRAPH_ELEMENT_LINE: Final = Line(
    level="ERROR",
    template="FILE=%(file)s: SBOM @graph holds an element that is not an object",
)

SBOM_INVALID: Final = Message(
    code="sbom-invalid",
    condition="invalid",
    lines=(SBOM_NOT_VALID_LINE, SBOM_GRAPH_NOT_LIST_LINE, SBOM_GRAPH_ELEMENT_LINE),
    summary="An SBOM given to read is JSON but not a valid SPDX 3 document: "
    "its @graph is not a list of objects ('embed-wheel --sbom', 'loom id "
    "import'; checked before the format, whatever the file is named), or "
    "spdx3-validate refuses it ('embed-wheel --sbom --validate'; its own "
    "lines before say why).",
    did="Wrote nothing: no wheel is changed, no ID is imported. The command "
    "exits 1; the library (embed_wheel_sbom with sbom_path, "
    "IdRegistry.import_sbom) raises ValueError carrying the code for an "
    "@graph that is not a list of objects.",
    effect="not-written",
    actor="user",
    advice="Tell the user which SBOM is not valid, and what the validator "
    "reported. They fix or regenerate it and run again. Do not edit the SBOM "
    "for them; ask first, and with nobody to ask, report it only.",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (SBOM_WRONG_FORMAT, SBOM_INVALID)
