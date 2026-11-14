# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``text-malformed``: text Pitloom read holds lone surrogates, which no
UTF-8 output can hold. ``text-malformed/registry``: a name the ID registry
is to hold does, so it is left out (``WARNING``) or refused (``ERROR``).

See also: :mod:`pitloom.messages._text_malformed_warning` (the one helper
every site says it through) and
:func:`pitloom.core.untrusted_text.escape_lone_surrogates` (how each is
written).
"""

from __future__ import annotations

from typing import Final

from pitloom.messages._registry_file import REGISTRY_PREFIX
from pitloom.messages._types import ASK_FIRST, Line, Message

#: What every line says was done.
_WRITTEN: Final = "lone surrogates written as \\uXXXX"

#: Text read from a file, or an SBOM element named by its name.
FILE_LINE: Final = Line(level="WARNING", template=f"FILE=%(file)s: {_WRITTEN}")
#: Text read from a model file, its format named first.
MODEL_LINE: Final = Line(
    level="WARNING", template=f"FORMAT=%(format)s FILE=%(file)s: {_WRITTEN}"
)

TEXT_MALFORMED: Final = Message(
    code="text-malformed",
    condition="malformed",
    lines=(FILE_LINE, MODEL_LINE),
    summary="Text Pitloom read holds lone surrogates (U+D800 to U+DFFF), which "
    "UTF-8 cannot hold: a JSON or YAML \\ud800 escape in a file (a model's "
    "metadata, a model or dataset card, a Croissant document, an SBOM "
    "fragment), or a file name that is not UTF-8. For the SBOM itself, the "
    "line names the first element holding one, by its name.",
    did="Wrote each lone surrogate as the six characters \\udXXX, in the SBOM "
    "and in its provenance, and went on; said once per file (once per SBOM "
    "for element names).",
    effect="weaker",
    actor="user",
    advice="Tell the user which file (or element) holds lone surrogates, as "
    "the line says, and that the SBOM shows each as \\udXXX, not as the "
    "character the source meant. If the exact text matters, they correct the "
    "source (a proper escape, a UTF-8 file name) and generate again. Do not "
    f"rename or edit files for them; {ASK_FIRST}",
    subject_key="FILE",
    since="0.23.0",
)

#: Why the ID registry cannot hold a name, in each of its lines.
_UNENCODABLE: Final = "cannot be encoded as UTF-8 (lone surrogate)"
#: A name ``IdRegistry.register`` is given (a ``-e`` NAME, a library call).
REGISTRY_NAME_LINE: Final = Line(
    level="ERROR",
    template=f"{REGISTRY_PREFIX}%(registry_part)s %(value)s {_UNENCODABLE}",
)
#: An SBOM element whose key or ``spdxId`` an import or harvest leaves out.
REGISTRY_NAME_SKIPPED_LINE: Final = Line(
    level="WARNING", template=f"{REGISTRY_NAME_LINE.template}; skipped"
)
#: A file ``loom id generate`` leaves out of the index for its name.
REGISTRY_FILE_NAME_LINE: Final = Line(
    level="WARNING",
    template=f"{REGISTRY_PREFIX}FILE=%(file)s: name {_UNENCODABLE}; not indexed",
)

TEXT_MALFORMED_REGISTRY: Final = Message(
    code="text-malformed/registry",
    condition="malformed",
    lines=(REGISTRY_NAME_LINE, REGISTRY_NAME_SKIPPED_LINE, REGISTRY_FILE_NAME_LINE),
    summary="A name the ID registry is to hold holds lone surrogates (U+D800 "
    "to U+DFFF), which its UTF-8 file cannot hold: a file name that is not "
    "UTF-8 (loom id generate), the name or spdxId of an SBOM element (a "
    "\\ud800 escape; loom id import, or the registry update of a run), or "
    "a name given to IdRegistry.register (a -e NAME). The value is shown "
    "escaped.",
    did="Left it out: the file is not indexed, the element's id is not "
    "recorded, and the run goes on. As an ERROR (a name given to register "
    "it), nothing is registered: 'loom id generate' exits 1 and writes no "
    "registry; the library raises ValueError carrying the code.",
    effect="thinner",
    actor="user",
    advice="Tell the user which name the ID registry cannot hold, as the line "
    "shows it escaped, and that it has no pinned id. They rename the file to "
    "a UTF-8 name, or correct the SBOM or the name given, and run again. Do "
    f"not rename or edit files for them; {ASK_FIRST}",
    since="0.24.1",
)

ENTRIES: Final = (TEXT_MALFORMED, TEXT_MALFORMED_REGISTRY)
