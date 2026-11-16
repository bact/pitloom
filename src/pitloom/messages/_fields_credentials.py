# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The values the lines of a refused or accepted URL credential name: the
element and the field that hold it, the fingerprint that accepts it, and a
setting that accepts it or sets the mode.

See also: :mod:`pitloom.messages._fields` (every field, these included) and
:mod:`pitloom.messages._url_credentials` (the lines).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pitloom.messages._field_tables import SETTING
from pitloom.messages._field_type import Field
from pitloom.messages._field_writers import entity_text, free_text, plain_text

#: A fingerprint of a URL-typed value: ``sha256:`` and at least 16 lower-case
#: hex digits of the SHA-256 of the value as serialised. The one spelling:
#: :data:`pitloom.core.credential_policy.FINGERPRINT_RE` compiles it.
FINGERPRINT: Final = r"sha256:[0-9a-f]{16,64}"

#: The fields of a URL credential's lines.
CREDENTIAL_FIELDS: Final[Mapping[str, Field]] = MappingProxyType(
    {
        "element": Field(
            r".+",
            entity_text,
            "<element>",
            "the SBOM element that holds the value (for a fingerprint that "
            "matches nothing, the SBOM's SpdxDocument), by its spdxId, a URL's "
            "credentials masked; in quotes, escaped, when it holds a control "
            "character",
            free=True,
        ),
        "fingerprint": Field(
            FINGERPRINT,
            plain_text,
            "<fingerprint>",
            "`sha256:` and the first hex digits of the SHA-256 of the value as "
            "the SBOM writes it: what --accept-url-credential takes",
        ),
        "pointer": Field(
            r".+",
            free_text,
            "<pointer>",
            "the field of the element that holds the value, as an RFC 6901 "
            "JSON pointer into it (`/software_downloadLocation`, "
            "`/externalRef/0/locator/0`); for a statement Pitloom writes, on "
            "into it (`/statement/metadata/<key>`, "
            "`/statement/fields/<field>/note`), or into the comment's provenance "
            "line (`/comment/<field>/note`), a part no JSON pointer resolves "
            "on the element; in quotes, escaped, when it holds a control "
            "character",
            free=True,
        ),
        "setting": Field(
            SETTING,
            plain_text,
            "<setting>",
            "a [tool.pitloom] setting as the file names it "
            "(`accept-url-credentials`, `url-credentials`)",
        ),
    }
)
