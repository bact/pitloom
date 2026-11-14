# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The page of the generated message reference that holds each family.

The reference (``docs/message-codes*.md`` and the skills'
``references/messages*.md``) is generated from the catalogue and split into
one page per topic, so no page nears the size limit. A family maps to exactly
one topic, and a family is never split across pages: its anchors stay together
and a code's page is derivable from the code. A catalogue PR that adds a family
adds it to :data:`FAMILY_TOPICS` and exports its entries, lines and helpers
from the topic's public module (``pitloom.messages.<topic>``, a hyphen spelt
``_``); a test fails until it does both. Moving a family
to another page changes its anchors: rewrite the links to it in the same PR.

The mapping is per family, not a field of :class:`~pitloom.messages.Message`,
so no constructor call has to set it.

See also: ``scripts/generate_message_reference.py`` (writes the pages).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

#: Topic slug -> page title, in the order the index lists the pages.
TOPIC_TITLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "models": "AI models",
        "model-fields": "Model fields",
        "targets": "Targets",
        "options": "Options",
        "files": "Files and text",
        "pypi": "PyPI",
        "network": "Network",
        "id-registry": "ID registry",
        "licences": "Licences",
    }
)

_TOPIC_FAMILIES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "models": (
            "lfs-pointer",
            "lfs-pointer-malformed",
            "library-missing",
            "library-unusable",
            "model-unreadable",
            "model-wrong-format",
            "reader-unsafe",
            "usage-unparseable",
            "usage-unusable",
        ),
        "model-fields": (
            "field-not-recordable",
            "hyperparameter-conflict",
            "model-field-conflict",
            "model-field-unreadable",
            "parameter-count-invalid",
        ),
        "targets": (
            "config-unsafe",
            "hf-url-invalid",
            "input-not-found",
            "model-ambiguous",
            "project-not-found",
            "project-or-model-not-found",
            "sbom-invalid",
            "sbom-wrong-format",
            "target-ambiguous",
            "target-wrong-format",
        ),
        "options": (
            "option-conflict",
            "option-invalid",
            "option-missing",
            "option-no-effect",
        ),
        "files": (
            "card-malformed",
            "dir-unlistable",
            "file-unreadable",
            "json-malformed",
            "over-cap",
            "temp-dir-unusable",
            "text-malformed",
        ),
        "pypi": (
            "digest-invalid",
            "file-ambiguous",
            "pypi-response-invalid",
            "pypi-url-invalid",
            "pypi-url-unusable",
            "release-file-not-found",
            "release-not-found",
            "release-unpinned",
            "release-unusable",
        ),
        "network": (
            "download-network-failed",
            "download-timeout",
            "offline-unusable",
            "query-no-effect",
            "url-moved",
            "url-unsafe",
        ),
        "id-registry": (
            "registry-malformed",
            "registry-unknown-key",
            "registry-unusable",
            "registry-wrong-format",
        ),
        "licences": ("license-relationship-invalid",),
    }
)

#: Family -> topic slug.
FAMILY_TOPICS: Final[Mapping[str, str]] = MappingProxyType(
    {
        family: topic
        for topic, families in _TOPIC_FAMILIES.items()
        for family in families
    }
)


def topic_of(code: str) -> str:
    """The topic slug of the page that holds *code* (``family[/variant]``).

    Raises:
        KeyError: The code's family is not in :data:`FAMILY_TOPICS`; the
            message says to map it in this module.
    """
    family = code.partition("/")[0]
    try:
        return FAMILY_TOPICS[family]
    except KeyError:
        raise KeyError(
            f"family {family!r} has no topic: map it in pitloom/messages/_topics.py"
        ) from None
