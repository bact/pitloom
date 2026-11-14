# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``json-malformed``: a JSON document Pitloom was given to read (a
Croissant document, PyPI's release metadata, an SBOM to embed or import, an
ID registry file) does not parse, or its top level is no object. ``ERROR``
only: the read raises.

See also: :func:`pitloom.extract._extract_utils.fetch_json` (a Croissant
document), :mod:`pitloom.extract.remote._http_fetch` (PyPI's JSON API),
:func:`pitloom._sbom_format.refuse_unusable_given_sbom` (an SBOM to embed
or to import into an ID registry), :mod:`pitloom.id_registry._format` (an
ID registry file).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._types import Line, Message

#: The release that first prints the entry, for a Croissant document.
_SINCE: Final = "0.23.0"
#: The release that first prints it for PyPI's release metadata.
_SINCE_PYPI: Final = "0.24.0"
#: The release that first prints it for an SBOM to embed or import, and for
#: an ID registry file.
_SINCE_SBOM: Final = "0.24.1"

#: A document the JSON parser refused.
NOT_JSON_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not valid JSON %(use)s; %(failure)s"
)
#: A document whose top level is an array, a string, a number or a literal.
NOT_OBJECT_LINE: Final = Line(
    level="ERROR", template="FILE=%(file)s: not a JSON object %(use)s"
)

JSON_MALFORMED: Final = Message(
    code="json-malformed",
    condition="malformed",
    lines=(NOT_JSON_LINE, NOT_OBJECT_LINE),
    summary="A JSON document Pitloom was given to read does not parse, or "
    "its top level is not an object; the line says which document by what it "
    "was read for: a Croissant document, PyPI's release metadata, or an SBOM "
    "given to embed or to import into an ID registry, or an ID registry file. "
    f"The lines print since {_SINCE} for a Croissant document, {_SINCE_PYPI} "
    f"for PyPI's release metadata and {_SINCE_SBOM} for an SBOM and an ID "
    "registry file.",
    did="Read nothing of it: the call raises ValueError carrying the code "
    "(for PyPI's release metadata, RemoteSourceError, code "
    "pypi.response-invalid), and a command exits 1. For a Croissant "
    "document, the dataset declaration (loom.add_dataset with croissant=, or "
    "read_croissant) fails; for PyPI's release metadata of a PyPI URL, no "
    "SBOM is written; for an SBOM to embed, no wheel is changed; for one to "
    "import, the ID registry is not written; for an ID registry file, no "
    "registry and no SBOM is written, and the file is left as it is.",
    effect="not-written",
    actor="user",
    advice="Tell the user which document is not valid JSON, or not a JSON "
    "object, and what the parser reported, as the line says. They fix or "
    "replace a local file (for an SBOM, generate it again; for an ID "
    "registry, restore it from version control: deleting it loses every id "
    "it pins) and run again; "
    "PyPI's answer is not theirs to fix, so they retry later. Do not edit, "
    "regenerate or replace the document for them; ask first, and with nobody "
    "to ask, report it only.",
    subject_key="FILE",
    since=_SINCE,
)

ENTRIES: Final = (JSON_MALFORMED,)
