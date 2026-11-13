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
adds it to :data:`FAMILY_TOPICS`; a test fails until it does. Moving a family
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
        "files": "Files and text",
        "pypi": "PyPI",
        "network": "Network",
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
            "input-not-found",
            "model-ambiguous",
            "project-not-found",
            "project-or-model-not-found",
            "target-ambiguous",
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
        KeyError: The code's family is not in :data:`FAMILY_TOPICS`.
    """
    return FAMILY_TOPICS[code.partition("/")[0]]
