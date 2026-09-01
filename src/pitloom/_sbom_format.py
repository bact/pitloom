# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""SBOM format detection (from raw bytes) and each format's recommended
file extension.

Independent of PEP 770/wheel-embedding mechanics -- see also
:mod:`pitloom._embed_wheel`, which locates an *embedded* SBOM's bytes but
delegates format detection here; both `verify-wheel` and `validate-wheel`
(`pitloom.cli.commands.verify_wheel`/`validate_wheel`) use this module.
"""

from __future__ import annotations

import json

from pitloom.export.spdx3_json import SPDX3_JSONLD_EXTENSION


def _looks_like_spdx3_jsonld(data: bytes) -> bool:
    """Sniff whether *data* is an SPDX 3 JSON-LD document.

    Unlike :func:`pitloom._embed_wheel._looks_like_pitloom_sbom`, this
    doesn't check for a Pitloom-authored ``Tool``/``SoftwareAgent`` -- it
    only checks the generic JSON-LD shape (``@context`` + ``@graph``) so a
    third-party (non-Pitloom) SPDX3 SBOM embedded via ``--sbom`` is also
    recognized.
    """
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    return (
        isinstance(doc, dict)
        and "@context" in doc
        and isinstance(doc.get("@graph"), list)
    )


#: Recommended file extension per detected SBOM format. Only one exporter
#: (SPDX3 JSON-LD) exists today -- kept as a small dict, not a plugin
#: registry, so a future format just adds an entry rather than needing new
#: infrastructure.
#:
#: Reference for the full convention (artifact `foo-1.0.0.tar.gz` ->
#: SBOM `foo-1.0.0.tar.gz.<ext>`), for when a new format/detector lands:
#:   CycloneDX JSON    .cdx.json
#:   CycloneDX XML     .cdx.xml
#:   SPDX tag:value    .spdx
#:   SPDX JSON         .spdx.json
#:   SPDX XML          .spdx.xml
#:   SPDX YAML         .spdx.yml (or .yaml)
#:   SPDX RDF/XML      .spdx.rdf
#:   SPDX 3 JSON       .spdx3.json
#:   SPDX 3 RDF/XML    .spdx3.rdf
_RECOMMENDED_EXTENSIONS: dict[str, str] = {"spdx3-jsonld": SPDX3_JSONLD_EXTENSION}

#: Formats `validate-wheel` has a registered schema/SHACL validator for.
#: Derived from `_RECOMMENDED_EXTENSIONS` rather than listed separately --
#: every format recognized here has a validator today, so a second,
#: independently-maintained collection would only risk drifting out of
#: sync with the first. If a future format needs an extension convention
#: without content validation (or vice versa), split this back into its
#: own explicit literal rather than letting the two silently diverge.
_VALIDATED_FORMATS: frozenset[str] = frozenset(_RECOMMENDED_EXTENSIONS)


def _detect_sbom_format(data: bytes) -> str | None:
    """Return a short format id for *data*, or ``None`` if unrecognized."""
    if _looks_like_spdx3_jsonld(data):
        return "spdx3-jsonld"
    return None
