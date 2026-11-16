---
Created: 2026-11-16
Last-Modified: 2026-11-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# A URL value that holds a credential

See also: [messages-url-credentials.md](messages-url-credentials.md) (the
`credentials-unsafe` codes, generated from the catalogue),
[id-registry.md](id-registry.md) (the ID registry's own lines).

Pitloom never rewrites a value it writes. A URL-typed field of the SBOM that
holds a credential is, by default (the `warn` mode), **written into the SBOM
as it is**, with one `WARNING: ... [credentials-unsafe/written]` per value
and exit 0. In the `refuse` mode (`[tool.pitloom] url-credentials =
"refuse"`, `--refuse-url-credentials`, the library's
`CredentialPolicy(refuse=True)`) it is one `ERROR: ...
[credentials-unsafe/refused]` per value, no SBOM, exit 1.

## What is read, what is found

- **Read**: URL-typed fields only, each as a whole value: a download
  location, a home page, a PURL (its qualifiers decoded), an external
  reference's locator, an identifier, an element id or namespace (also read
  percent-decoded), a field that refers to another element by id
  (`createdBy`, `suppliedBy`, `from`, `to`, `subject`, ...), and every string
  of Pitloom's own provenance (annotation statement and `Metadata
  provenance:` comment). A name, a description, README text or any other
  prose is never read. A file given to `embed-wheel --sbom` is the
  exception: every string of it is read as a whole value (a `name` that is
  a credentialed URL counts; a sentence holding one does not).
- **A credential** (`written` or `refused`, by mode): a user name and
  password (`https://user:pass@host`), a query parameter named like a secret
  (`token=`, `api_key=`, `password=`, ...), an access token's shape
  (`ghp_...`, `glpat-...`, `hf_...`, `AKIA...`), an scp-style address with
  a password, or a query nested or encoded too deeply to read.
- **Warned only, in either mode** (`WARNING: ... [credentials-unsafe]`,
  exit 0): a `code`, `session`, `ticket`, `sid` or `otp` parameter, another
  ending in `_key` that names no kind of secret key (`sort_key`; `api_key`
  is a credential), or an `ssh` user name alone (`git@`). The SBOM states
  it as written; relay the line.

Every surface that writes an SBOM checks it: `loom generate`, `project`,
`wheel`, `model`, `env`, `enrich`, `merge`, `embed-wheel` (its `--sbom
FILE` too), the Hatchling build hook (the build goes on in `warn`, fails in
`refuse`) and the library (`ValueError` carrying the code in `refuse`).

## The lines

`warn` (default): one line per value; the SBOM is written. Each line ends
with how the surface that ran turns the `refuse` mode on (here the command
line's; the hook says `[tool.pitloom] url-credentials = "refuse"`, the
library `credentials=CredentialPolicy(refuse=True)`):

```text
WARNING: URL=https://***:***@h.example/x: holds a credential (<element id> /software_downloadLocation, sha256:<16 hex>); the SBOM states it as written; remove it from the source, or refuse such values with --refuse-url-credentials [credentials-unsafe/written]
```

`refuse`: one line per value, then a count; no SBOM is written. Each line
ends with how the surface that ran accepts the value:

```text
ERROR: loom project: URL=https://***:***@h.example/x: holds a credential (<element id> /software_downloadLocation, sha256:<16 hex>); remove it from the source, or accept this value with --accept-url-credential sha256:<16 hex> [credentials-unsafe/refused]
ERROR: loom project: 1 URL value(s) in the SBOM hold credentials; the SBOM is refused [credentials-unsafe/refused]
```

The URL is masked (`***`); the parentheses name the element and the field
(an RFC 6901 pointer into it) and the value's fingerprint, the SHA-256 of
the whole field value. Never try to recover the masked part.

## What to tell the user, in order

1. **Which value and where**: the URL as the line shows it, the element and
   the field. You may point to where it likely comes from (a
   `[project.urls]` entry, a dependency's direct URL, a fragment) by
   reading their files; do not edit them.
2. **It is exposed**: for a `written` line, the credential is now in the
   SBOM file just written, so do not publish or share that SBOM. A
   credential in a project's files is also in its history, and in any SBOM,
   log or build output already shared. They should treat it as exposed and
   rotate it, then remove it from the source and generate again.
3. **Offer the `refuse` mode for CI** (for a `written` line): `[tool.pitloom]
   url-credentials = "refuse"` in `pyproject.toml` (`setup.cfg`:
   `[tool:pitloom] url-credentials = refuse`), or `--refuse-url-credentials`
   on the command line, or `url-credentials: refuse` as an input of the
   GitHub Action. Ask before editing the file.
4. **Only once the user confirms that this value is no secret** (an example
   URL in documentation, a placeholder), offer to accept that value alone,
   with the fingerprint from the line. On the command line: re-run with
   `--accept-url-credential sha256:<hex>` (repeatable, one per value), or
   list it in `pyproject.toml`: `[tool.pitloom] accept-url-credentials =
   ["sha256:<hex>"]` (`setup.cfg`: `[tool:pitloom]`, one per line; ask before
   editing the file); the Action takes them as its `accept-url-credentials`
   input (comma or line separated). The build hook reads that list (it has no flag); a
   library caller passes `credentials=CredentialPolicy(accepted=["sha256:<hex>"])`.
   `loom merge` and `embed-wheel --sbom FILE` read the flags only. Later runs
   then print `WARNING: ... [credentials-unsafe/accepted]` instead (both
   modes): expected, relay it once.
5. **Never suggest turning the `refuse` mode off** to get past a refusal;
   accepting one value by its fingerprint is the narrow choice.

A fingerprint that matches no value of the SBOM prints `WARNING: Options:
FINGERPRINT=sha256:<hex>: matches no URL of the SBOM <element>
[option-no-effect]` (the value changed or is gone): suggest removing that
entry.

**Non-interactive** (no way to ask): report the `WARNING:` or `ERROR:` lines
as printed, that a written SBOM holds the credential, and the rotate advice,
and stop. Do not accept a fingerprint, re-run with a flag or edit a file.
