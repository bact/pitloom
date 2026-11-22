# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The licence a GGUF file states: ``general.license``, else
``general.license.name``.

See also: :mod:`pitloom.extract.ai_model.gguf` (the reader).
"""

from __future__ import annotations

from typing import Any

from pitloom.extract._license import warn_unless_expression
from pitloom.extract._license_classify import is_vague_license_value, is_weak_licence
from pitloom.extract.ai_model._stated_text import stated_text

_GGUF_LICENSE_KEY = "general.license"
_GGUF_LICENSE_NAME_KEY = "general.license.name"


def read_gguf_license(
    fields: dict[str, Any], source: str, provenance: dict[str, str]
) -> str | None:
    """Return ``general.license`` (an SPDX expression by the GGUF spec), if
    it is a non-blank string; a value of another type stays in
    ``properties`` only. One that is no SPDX expression (``llama3.1``) is
    text, with a ``WARNING:``. With no ``general.license``, or a placeholder
    (``other``, ``custom``, ``N/A``, ``NOASSERTION``, ...),
    ``general.license.name`` (the licence's name: free text, no field
    warning) stands in; ``general.license.link`` is not read. A placeholder
    pointing elsewhere (``other``, ``custom``, ``N/A``: not
    ``NOASSERTION``/``UNKNOWN``, which say "not known") with no name is no
    licence, as on the Hub."""
    license_expr = stated_text(fields.get(_GGUF_LICENSE_KEY))
    name = stated_text(fields.get(_GGUF_LICENSE_NAME_KEY))
    # llama.cpp's converter writes a card's ``license: other`` with its
    # ``license_name`` as ``general.license.name``: a placeholder (``other``,
    # ``NOASSERTION``, ...) gives way to it; ``NONE`` is a statement and stays.
    weak = is_weak_licence(license_expr)
    vague = not weak and is_vague_license_value(license_expr)
    if license_expr and not vague and not (name and weak):
        warn_unless_expression(license_expr, _GGUF_LICENSE_KEY)
        provenance["license"] = f"{source} | Field: {_GGUF_LICENSE_KEY}"
        return license_expr
    if not name:
        return None
    provenance["license"] = f"{source} | Field: {_GGUF_LICENSE_NAME_KEY}"
    return name
