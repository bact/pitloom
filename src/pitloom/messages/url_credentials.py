# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` messages: the one ``WARNING:`` for a URL stripped
of its credentials or holding one the SBOM keeps, and the errors for a
registry value that holds some, or a registry file's entry dropped for one.

See also: :mod:`pitloom.messages._url_credentials` (the entries) and
:mod:`pitloom.messages.url_credentials_git` (the Git variants).
"""

from __future__ import annotations

import logging

from pitloom.core.url_masking import (
    is_whole_url,
    keeps_url_credential,
    masked_given_path,
)
from pitloom.messages._emit import CodedValueError, emit
from pitloom.messages._url_credentials import (
    CREDENTIALS_UNSAFE,
    CREDENTIALS_UNSAFE_ID_COLLISION,
    CREDENTIALS_UNSAFE_REGISTRY,
    ENTRY_DROPPED_LINE,
    ID_COLLISION_LINE,
    KEPT_LINE,
    KEY_LINE,
    KEY_SKIPPED_LINE,
    NAMESPACE_CREDENTIALS_LINE,
    STRIPPED_KEPT_LINE,
    STRIPPED_LINE,
    UNREMOVED_LINE,
)

__all__ = [
    "CREDENTIALS_UNSAFE",
    "CREDENTIALS_UNSAFE_ID_COLLISION",
    "CREDENTIALS_UNSAFE_REGISTRY",
    "id_collision_error",
    "registry_key_credentials_error",
    "registry_namespace_credentials_error",
    "warn_registry_entry_credentials_dropped",
    "warn_registry_key_credentials_skipped",
    "warn_url_credential_kept",
    "warn_url_credential_unremoved",
    "warn_url_credentials_stripped",
]


def _once(url: str) -> str:
    return f"{CREDENTIALS_UNSAFE.code}:{url}"


def warn_url_credentials_stripped(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log*, once per *url* and process, that *url*
    is stated without its credentials. *url* is given as
    :func:`~pitloom.core.url_masking.strip_url_secrets` shows it (what is
    removed masked, what is kept as written), so the line names a kept
    value only when *url* holds one."""
    line = (
        STRIPPED_KEPT_LINE
        if keeps_url_credential(url, whole=is_whole_url(url))
        else STRIPPED_LINE
    )
    emit(log, CREDENTIALS_UNSAFE, logging.WARNING, line=line, once=_once(url), url=url)


def warn_url_credential_kept(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log*, once per *url* and process, that *url*
    (shown masked) holds a value the SBOM keeps that may be a credential
    (:func:`~pitloom.core.url_masking.keeps_url_credential`)."""
    emit(
        log,
        CREDENTIALS_UNSAFE,
        logging.WARNING,
        line=KEPT_LINE,
        once=f"{_once(url)}:kept",
        url=masked_given_path(url),
    )


def warn_url_credential_unremoved(log: logging.Logger, value: str) -> None:
    """The one ``WARNING:`` on *log*, once per *value* and process (two
    values that mask alike are said each), that *value* (shown masked)
    holds a credential
    (:func:`~pitloom.core.url_masking.holds_url_credentials`) the SBOM strip
    does not remove, so the SBOM states it as written."""
    emit(
        log,
        CREDENTIALS_UNSAFE,
        logging.WARNING,
        line=UNREMOVED_LINE,
        once=f"{_once(value)}:unremoved",
        url=masked_given_path(value),
    )


def warn_registry_key_credentials_skipped(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that an SBOM element with the registry
    key or id *url* (masked here) is left out of the ID registry."""
    shown = masked_given_path(url)
    emit(
        log,
        CREDENTIALS_UNSAFE_REGISTRY,
        logging.WARNING,
        line=KEY_SKIPPED_LINE,
        once=f"{CREDENTIALS_UNSAFE_REGISTRY.code}:{shown}",
        url=shown,
    )


def warn_registry_entry_credentials_dropped(log: logging.Logger, url: str) -> None:
    """The one ``WARNING:`` on *log* that the entry of a registry file whose
    key or id is *url* (masked here) is dropped from the ID registry."""
    shown = masked_given_path(url)
    emit(
        log,
        CREDENTIALS_UNSAFE_REGISTRY,
        logging.WARNING,
        line=ENTRY_DROPPED_LINE,
        once=f"{CREDENTIALS_UNSAFE_REGISTRY.code}:{shown}",
        url=shown,
    )


def registry_key_credentials_error(url: str) -> CodedValueError:
    """The error for a registry key *url* that holds credentials, shown
    masked."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY, line=KEY_LINE, url=masked_given_path(url)
    )


def registry_namespace_credentials_error(namespace: str) -> CodedValueError:
    """The error for a registry *namespace* that holds credentials, shown
    masked."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_REGISTRY,
        line=NAMESPACE_CREDENTIALS_LINE,
        url=masked_given_path(namespace),
    )


def id_collision_error(url: str) -> CodedValueError:
    """The error for an element id *url* that is another's once its
    credentials are removed, shown masked."""
    return CodedValueError(
        CREDENTIALS_UNSAFE_ID_COLLISION,
        line=ID_COLLISION_LINE,
        url=masked_given_path(url),
    )
