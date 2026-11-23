# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Why a text cannot be a document namespace: the closed problem texts.

A leaf module (no Pitloom imports), so the message catalogue can quote the
texts without importing :mod:`pitloom.core.iri`, which raises through the
catalogue.

See also: :func:`pitloom.core.iri.namespace_problem`.
"""

from __future__ import annotations

__all__ = [
    "NAMESPACE_CHARACTER",
    "NAMESPACE_CREDENTIALS",
    "NAMESPACE_EMPTY",
    "NAMESPACE_FRAGMENT",
    "NAMESPACE_PROBLEMS",
    "NAMESPACE_RELATIVE",
]

#: Why a text cannot be a document namespace (its problem reads after
#: ``namespace``).
NAMESPACE_EMPTY = "is empty"
NAMESPACE_FRAGMENT = "must not contain '#'"
NAMESPACE_RELATIVE = (
    "is not an absolute IRI (a scheme is needed, as in https://example.org/ns)"
)
NAMESPACE_CHARACTER = "has a character an IRI cannot hold"
NAMESPACE_CREDENTIALS = (
    "holds user information, a secret query value or an access token, or a "
    "query nested or encoded too deeply to read"
)
NAMESPACE_PROBLEMS = (
    NAMESPACE_EMPTY,
    NAMESPACE_FRAGMENT,
    NAMESPACE_RELATIVE,
    NAMESPACE_CHARACTER,
    NAMESPACE_CREDENTIALS,
)
