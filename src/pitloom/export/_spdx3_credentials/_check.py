# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The check of an SBOM's credential findings against a run's
:class:`~pitloom.core.credential_policy.CredentialPolicy`: warn of each
(``warn`` mode) or refuse the SBOM (``refuse`` mode), an accepted or weak
value said more quietly, a stale accepted fingerprint warned of.

See also: :mod:`pitloom.export._spdx3_credentials._find` (the findings) and
:mod:`pitloom.messages.url_credentials` (the lines said).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pitloom.core.credential_policy import full_fingerprint
from pitloom.export._spdx3_credentials._find import (
    GraphFinding,
    element_name,
    find_graph_credentials,
)
from pitloom.messages.url_credentials import (
    refused_error,
    say_accepted,
    say_refused,
    say_stale_fingerprint,
    say_weak,
    say_written,
)

if TYPE_CHECKING:
    from pitloom.core.credential_policy import CredentialPolicy

__all__ = ["check_graph_credentials"]


def check_graph_credentials(
    graph: list[dict[str, Any]], policy: CredentialPolicy, *, every_string: bool = False
) -> None:
    """Warn of, or refuse, each value of a read field of *graph* that holds
    a credential *policy* does not accept by its fingerprint: in the
    ``warn`` mode (``policy.refuse`` false) one ``WARNING:`` per distinct
    value, the SBOM written as it is; in the ``refuse`` mode one ``ERROR:``
    per distinct value, in graph order, then the error. A value accepted by
    its fingerprint is stated as written with a quieter ``WARNING:`` in
    either mode; a weak one (a parameter of a weak name, an ``ssh`` account
    name) is only warned of. An accepted fingerprint that matches no value
    found is warned of too. *graph* is never changed.

    *every_string* is for an SBOM Pitloom did not write and states as
    written (``embed-wheel --sbom``): its keys need not be the compact names
    of :data:`URL_FIELDS` (an expanded IRI, a prefixed key, a value object,
    an ``@context``), so every string in it is read too, as a whole URL
    value: a string that is not a URL holds no finding.

    Raises:
        pitloom.messages.CodedValueError: ``credentials-unsafe/refused``, in
            the ``refuse`` mode only; its text and ``args`` name no URL, and
            it has no context.
    """
    findings = find_graph_credentials(graph, every_string=every_string)
    unaccepted: list[GraphFinding] = []
    for item in findings:
        if item.finding.weak:
            say_weak(item.shown)
        elif policy.accepts_value(item.value):
            say_accepted(item.shown, item.fingerprint)
        else:
            unaccepted.append(item)
    _warn_stale(policy, findings, _document_name(graph))
    if not policy.refuse:
        for item in unaccepted:
            say_written(item.shown, item.element, item.pointer, item.fingerprint)
        return
    if unaccepted:
        for item in unaccepted:
            say_refused(item.shown, item.element, item.pointer, item.fingerprint)
        raise refused_error(len(unaccepted)) from None


def _document_name(graph: list[dict[str, Any]]) -> str:
    """The SBOM *graph* is, as a stale fingerprint's line names it: its
    ``SpdxDocument``'s id, masked; without one, its first element's."""
    document = next(
        (e for e in graph if isinstance(e, dict) and e.get("type") == "SpdxDocument"),
        graph[0] if graph and isinstance(graph[0], dict) else {},
    )
    return element_name(document)


def _warn_stale(
    policy: CredentialPolicy, findings: list[GraphFinding], document: str
) -> None:
    """Warn of each fingerprint *policy* accepts for this SBOM (not one it
    inherits) that is a prefix of no value's full fingerprint among
    *findings* (the values a run could need to accept); *document* names
    the SBOM."""
    digests = [full_fingerprint(item.value) for item in findings]
    for entry in sorted(policy.accepted):
        if not any(digest.startswith(entry) for digest in digests):
            say_stale_fingerprint(entry, document)
