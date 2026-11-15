# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The detector of credentials in a URL-typed value Pitloom stores or
publishes as written: each URL credential, scp-style password and access
token found, never a rewritten value.

See also: :mod:`pitloom.core.url_masking._hits` (what is found) and
:mod:`pitloom.core.url_masking._mask` (the masker, which hides every
finding). Standard library only.

What the detector reads: a URL-typed field (a namespace, an element id, a
registry key, a project or dependency URL, a requirement string, a PURL) as
one whole value. Prose (a description, a comment, a name, README text) is
out of scope: a value that is not, as a whole, a URL, a requirement with a
direct reference, an scp-style address or a PURL has no finding, whatever
URL or token it mentions (``see https://u:pw@h/x``, ``key AKIA...``,
``build:42@ci:linux now``). Finding secrets in prose is a secret scanner's
job; a refusal there would block builds on README examples. Masking for
display (a log line, a message) reads free text too: that is
:func:`~pitloom.core.url_masking.masked_given_path`, never a refusal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pitloom.core.url_masking._hits import FindingKind, iter_hits, normalised
from pitloom.core.url_masking._mask import masked_given_path

__all__ = ["Finding", "find_url_credentials", "holds_url_credentials"]


@dataclass(frozen=True)
class Finding:
    """A credential found in a text. Its ``repr`` leaves out :attr:`view`."""

    #: What was found.
    kind: FindingKind
    #: The URL, address, token or qualifier as found (decoded, for a PURL
    #: qualifier at a depth): it holds the credential, so it is never
    #: printed.
    view: str = field(repr=False)
    #: The same masked: what a message may print.
    shown: str
    #: Whether it may be a credential only (a weak name, an accepted account
    #: name): told, never refused.
    weak: bool = False


def find_url_credentials(
    text: str, *, scp: bool = True, account: bool = False, embedded: bool = False
) -> tuple[Finding, ...]:
    """Each credential found in *text*, a URL-typed value read as a whole
    (this module's docstring; what is found:
    :mod:`pitloom.core.url_masking._hits`), in order, once each. With *scp*
    false a value that is an scp-style address has no finding (a file name
    such as ``meet-10:30@ab:c.txt``). With *account*, an account name on an
    ``ssh`` or ``git`` URL (``git@``,
    :func:`~pitloom.core.url_masking.is_account_name`) is weak, as in an
    SBOM; else it is a credential, as in a namespace. With *embedded*, for
    an identifier Pitloom stores (an ID registry key, id or namespace),
    never prose, a URL or an access token anywhere in *text* is read too
    (``urn:x:https://u:p@h``). The time is linear in *text*."""
    found: dict[Finding, None] = {}
    # One view holds many hits (a URL with many secret parameters): each
    # view is masked once.
    masked: dict[str, str] = {}
    # A value read once normalised (a format character or an enclosing pair
    # dropped) is held as written; what is shown is masked as read.
    whole = text if normalised(text) != text.strip() else None
    for hit in iter_hits(text, scp=scp, account=account, embedded=embedded):
        shown = hit.shown
        if shown is None:
            shown = masked.get(hit.view)
            if shown is None:
                shown = masked[hit.view] = masked_given_path(hit.view)
        view = hit.view if whole is None else whole
        found.setdefault(Finding(hit.kind, view, shown, hit.weak))
    return tuple(found)


def holds_url_credentials(
    text: str, *, scp: bool = True, account: bool = False, embedded: bool = False
) -> bool:
    """Whether *text*, a URL-typed value read as a whole (a registry key, a
    namespace), holds a credential: a finding of
    :func:`find_url_credentials` (with the same *scp*, *account* and
    *embedded*) that is not weak. A weak name (``code``, ``session``...)
    alone is none."""
    found = find_url_credentials(text, scp=scp, account=account, embedded=embedded)
    return any(not finding.weak for finding in found)
