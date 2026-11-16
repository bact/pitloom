# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The ``credentials-unsafe`` family: a value Pitloom would persist is never
rewritten. ``credentials-unsafe/refused``: a URL-typed value of the SBOM
holds a credential, so no SBOM is written (``ERROR``);
``credentials-unsafe/accepted``: the user accepted such a value, by its
fingerprint or for every value, and the SBOM states it as written
(``WARNING``); ``credentials-unsafe``: a value that may be one only (a
``code`` parameter, an ``ssh`` user name), stated as written (``WARNING``).
``credentials-unsafe/registry``: an ID registry key, namespace or file entry
holds one, so it is refused (``ERROR``) or the element skipped
(``WARNING``).

See also: :mod:`pitloom.messages.url_credentials` (the helpers every site
says them through), :mod:`pitloom.messages._url_credentials_git` (the
family's Git variants) and
:func:`pitloom.core.url_masking.find_url_credentials` (what is found).
"""

from __future__ import annotations

from typing import Final

from pitloom.core.iri import NAMESPACE_CREDENTIALS
from pitloom.messages._types import ASK_FIRST, Line, Message

_SINCE: Final = "0.25.0"
#: The phrase of each refusal of a stored value, a namespace refusal's too
#: (what :func:`pitloom.core.url_masking.find_url_credentials` refuses).
_REFUSED: Final = NAMESPACE_CREDENTIALS
#: The options that accept a value that holds a credential: one by its
#: fingerprint, or every one. A line names each as a value, so a module that
#: defines the option does not hold the line's text.
ACCEPT_OPTION: Final = "--accept-url-credential"
ALLOW_OPTION: Final = "--allow-url-credentials"

#: A registry key the registry would store as written.
KEY_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_REFUSED}; an ID registry key is stored as "
    "written, so it is refused",
)
#: A document namespace the registry would store as written.
NAMESPACE_CREDENTIALS_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_REFUSED}; an ID registry namespace is stored as "
    "written, so it is refused",
)
#: An element whose key or id an import or harvest would store as written.
KEY_SKIPPED_LINE: Final = Line(
    level="WARNING",
    template=f"URL=%(url)s: {_REFUSED}; the ID registry stores an element's key "
    "and id as written, so the element is skipped",
)
#: A registry file's entry whose key or id holds one: the file is not loaded.
REGISTRY_FILE_REFUSED_LINE: Final = Line(
    level="ERROR",
    template=f"URL=%(url)s: {_REFUSED}; ID registry file %(file)s is not "
    "loaded; remove the entry",
)
#: A value the SBOM states as written that may be a credential only.
WEAK_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: holds a code, session, ticket, sid, otp or other "
    "_key parameter or an ssh user name; the SBOM states it as written",
)
#: The ``[tool.pitloom]`` key that accepts a value by its fingerprint, as the
#: Hatchling hook's refusal names it.
ACCEPT_SETTING: Final = "[tool.pitloom] accept-url-credentials"
#: How a library caller accepts every value, as an accepted line names it.
ALLOW_ARGUMENT: Final = "CredentialPolicy.allow_all"
#: The start of each refusal of one URL value of the SBOM: the value, the
#: element and field that hold it, and its fingerprint.
_REFUSED_HEAD: Final = (
    "URL=%(url)s: holds a credential (%(element)s %(pointer)s, %(fingerprint)s); "
    "remove it from the source, or accept this value "
)
#: One URL value of the SBOM that holds a credential, on the command line:
#: accepted with :data:`ACCEPT_OPTION`.
REFUSED_LINE: Final = Line(
    level="ERROR",
    template=f"{_REFUSED_HEAD}with %(option)s %(fingerprint)s",
)
#: The same in the Hatchling build hook, which reads ``pyproject.toml`` only:
#: accepted with :data:`ACCEPT_SETTING`.
REFUSED_CONFIG_LINE: Final = Line(
    level="ERROR",
    template=f"{_REFUSED_HEAD}by listing it in %(setting)s",
)
#: The same from the library (``loom.Run`` too): accepted by the
#: ``credentials`` argument.
REFUSED_LIBRARY_LINE: Final = Line(
    level="ERROR",
    template=f"{_REFUSED_HEAD}with credentials=CredentialPolicy("
    'accepted=["%(fingerprint)s"])',
)
#: The closing refusal, naming no URL.
REFUSED_COUNT_LINE: Final = Line(
    level="ERROR",
    template="%(number)s URL value(s) in the SBOM hold credentials; the SBOM is "
    "refused",
)
#: A value accepted by its fingerprint.
ACCEPTED_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: holds a credential that %(fingerprint)s accepts; "
    "the SBOM states it as written",
)
#: A value accepted by :data:`ALLOW_OPTION`.
ALLOWED_LINE: Final = Line(
    level="WARNING",
    template="URL=%(url)s: holds a credential; %(option)s keeps it as written",
)
CREDENTIALS_UNSAFE: Final = Message(
    code="credentials-unsafe",
    condition="unsafe",
    lines=(WEAK_LINE,),
    summary="A URL-typed value the SBOM states (a dependency's direct URL, a "
    "project URL, a download location) holds what may be a credential "
    "only: a query parameter named code, session, ticket, sid or otp, "
    "another whose name ends in _key, or a user name alone on an ssh or git "
    "URL (git@). Pitloom never rewrites a value: one that holds a "
    "credential is refused (credentials-unsafe/refused) unless the user "
    "accepts that value by its fingerprint; one that may be a credential "
    "only, common in example and OAuth URLs, is warned of instead.",
    did="Wrote the SBOM with the value as written; said once per value, "
    "shown masked. Nothing is removed or rewritten.",
    effect="none",
    actor="user",
    advice="Tell the user which value, as the line shows it, and that the "
    "SBOM states it as written. They check that the parameter or the ssh "
    "user name is no credential; if it is one, they remove it from the "
    "source and generate again, and rotate it, since a credential in a "
    "project's files is also in its history. "
    f"Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_REGISTRY: Final = Message(
    code="credentials-unsafe/registry",
    condition="unsafe",
    lines=(
        KEY_LINE,
        NAMESPACE_CREDENTIALS_LINE,
        KEY_SKIPPED_LINE,
        REGISTRY_FILE_REFUSED_LINE,
    ),
    summary="A key or namespace given to the ID registry (an external "
    "reference URL), or the key or id of an SBOM element it would record, "
    "holds a user name or password, a query parameter named like a secret "
    "or an access token (also percent-encoded in a PURL qualifier), or a "
    "query nested too deeply to read (a value with more than 16 ?) or a PURL "
    "qualifier encoded too deeply to read (still encoded after five "
    "decodes). The registry file stores a key, an id and its namespace as "
    "written.",
    did="Refused the key or namespace and stored nothing (error), or left the "
    "SBOM element out of the registry and wrote the rest (warning). A "
    "registry file with an entry holding one is not loaded at all and left "
    "as it is, and the run stops (error naming the file).",
    effect="thinner",
    actor="user",
    advice="Tell the user which value, as the line shows it. For an error, "
    "they give the value without the credential and run again; a credential "
    "typed on a command line is exposed in their shell history. For a "
    "warning, the value came from an SBOM ('loom id import'), the run's own "
    "data or their registry file: that element has no stable id (a new one "
    "is minted next run), and a credential in a shared SBOM, a project's "
    "files or a committed registry file is exposed, in its history too. "
    "For an error naming an ID registry file, they remove that entry from "
    "the file themselves and run again. "
    "Either way they should rotate it. Do "
    f"not edit their registry file; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_REFUSED: Final = Message(
    code="credentials-unsafe/refused",
    condition="unsafe",
    lines=(
        REFUSED_LINE,
        REFUSED_CONFIG_LINE,
        REFUSED_LIBRARY_LINE,
        REFUSED_COUNT_LINE,
    ),
    summary="A URL-typed value the SBOM would state (a dependency's direct "
    "URL, a download location, a PURL, an external reference's locator) "
    "holds a user name or password, a query parameter named like a secret, "
    "an access token's shape, an scp-style address with a password, or a "
    "query nested or encoded too deeply to read. An SBOM can be published, "
    "so it must not carry one. Each such value is one line naming the "
    "element and field that hold it and its fingerprint; the last line "
    "counts them and names no URL. Each line says how the surface that ran "
    "accepts the value: the command line's option, the build hook's "
    "[tool.pitloom] list, or the library's credentials argument.",
    did="Wrote no SBOM: the command exits 1 (the Action step fails), the "
    "build hook fails the build, and the library raises ValueError carrying "
    "the code; 'embed-wheel --sbom' embeds nothing and leaves the wheel as "
    "it is, and loom.Run writes no fragment. Nothing is removed or "
    "rewritten.",
    effect="not-written",
    actor="user",
    advice="Tell the user which value, as the line shows it, and where it "
    "is. First they remove the credential from the source and generate "
    "again; a credential in a project's files is also in its history, so "
    "they should consider it exposed and rotate it. Only once they have "
    "confirmed that one value is no secret (an example URL in a README) do "
    "they accept that value alone, the way the line gives with its "
    "fingerprint: --accept-url-credential, accept-url-credentials in "
    "[tool.pitloom] (also for the command line), or the library's "
    "credentials argument. Do not suggest --allow-url-credentials or "
    f"allow_all, which keep every such value. Do not edit their files; {ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

CREDENTIALS_UNSAFE_ACCEPTED: Final = Message(
    code="credentials-unsafe/accepted",
    condition="unsafe",
    lines=(ACCEPTED_LINE, ALLOWED_LINE),
    summary="A URL-typed value the SBOM states holds what reads as a "
    "credential, and the user accepted it: by its fingerprint "
    "(--accept-url-credential, accept-url-credentials in [tool.pitloom]) or "
    "for every value (--allow-url-credentials).",
    did="Wrote the SBOM with the value as written; said once per value, shown masked.",
    effect="none",
    actor="user",
    advice="Tell the user which value the SBOM states as written, as the "
    "line shows it, and that anyone who reads the SBOM reads it too. If it "
    "is a real credential, they remove it from the source, rotate it and "
    "drop the acceptance. Do not suggest --allow-url-credentials in place "
    "of a fingerprint. Do not edit their files or configuration; "
    f"{ASK_FIRST}",
    subject_key="URL",
    since=_SINCE,
)

ENTRIES: Final = (
    CREDENTIALS_UNSAFE,
    CREDENTIALS_UNSAFE_REGISTRY,
    CREDENTIALS_UNSAFE_REFUSED,
    CREDENTIALS_UNSAFE_ACCEPTED,
)
