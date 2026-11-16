---
Created: 2026-11-16
Last-Modified: 2026-11-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Credentials in URLs

An SBOM can be published, so Pitloom does not put a credential in one. When a
URL field of the SBOM would hold a credential, Pitloom **refuses**: it names
each value, writes no SBOM and exits 1. It never rewrites a value, so what an
SBOM states is what the source said.

This page covers what is refused, how to fix it, how to accept a value you
know is no secret, and what is not detected. See also [Dependency
sources](dependency-sources.md#credentials-in-a-url) (where project and
dependency URLs come from), [Loom ID registry keys](id-registry-keys.md#credentials-in-a-key)
(the same rule for a registry) and [Git URLs](git-urls.md) (the credential in
a URL you give to fetch).

## What is refused

A value of a [field read](#fields-read) is refused when it holds:

- user information in a URL (`https://user:password@host/x`, `https://token@host/x`),
  after any scheme (`s3:/user:pw@host/x`, `ftp://...`);
- a query or fragment parameter named like a secret (`token`, `access_token`,
  `api_key`, `client_key`, `password`, `secret`, `signature`, `key`,
  `session_id`), also percent-encoded in a PURL qualifier;
- an access token's shape anywhere in it (GitHub, GitLab, Slack, Hugging Face,
  AWS key id, PyPI, npm, OpenAI, Anthropic and Google API key prefixes);
- an scp-style address with a password (`alice:password@host:o/r`; a dotless
  host such as `build:42@ci:linux` counts);
- a query nested too deeply to read (more than 16 `?`), or a PURL qualifier
  still encoded after five decodes.

A value is read past an invisible format character (a zero-width space, a byte
order mark) and inside one pair of `<>` or quotes, as a client reads it.

A parameter named `code`, `session`, `ticket`, `sid` or `otp`, another that
ends in `_key` and is no kind of secret key (`sort_key`), and a user name alone
on an `ssh` or `git` URL (`ssh://git@github.com/o/r`) may hold a credential
only. These are **warned of, not refused**: the SBOM states them as written, and
the warning shows the value masked, once.

## Fields read

Only the fields below are read, each as one whole value, wherever the element
that holds them stands in the document (a nested `ExternalRef` or
`NamespaceMap` too). A field of this list is read for every SBOM Pitloom writes:
project, wheel, environment, model, Git and PyPI targets, a fragment, a merge
and an SBOM embedded in a wheel.

| Field | Read as |
| :--- | :--- |
| `software_downloadLocation`, `software_homePage`, `software_packageUrl`, `software_contentIdentifierValue`, `locator`, `identifierLocator`, `expandedlicensing_seeAlso`, `build_configSourceUri`, `build_buildType`, `security_locator` | A URL, a PURL or an scp-style address |
| `identifier`, when its `externalIdentifierType` is `packageUrl` or `urlScheme` | The same |
| `locationHint` | The same, but a value that is only scp-shaped is a file path (`meet-10:30@ab:c.json`), not refused |
| `spdxId`, `@id`, `externalSpdxId`, `namespace` | An identifier Pitloom or a merged document stores: a URL or an access token anywhere in it counts, and so does any `ssh` user name |
| The note of Pitloom's own provenance: an annotation's `fields.<field>.note`, a `Note:` segment of a `Metadata provenance:` comment line | A URL, a PURL or an scp-style address (a dependency's direct reference, `foo @ https://host/x.whl`, is stated there whole) |

## What is not read

Prose. A README, a description, a licence text, a comment line that is not
Pitloom's provenance line, a name or a summary is never refused, even when it
shows a URL with a password or a token. A README example must not block a
build, and finding secrets in prose is a secret scanner's job. Pitloom's log
lines and `-v` details do mask a credential they print (`https://***:***@host`,
`ghp_***`); that is display only.

## What you see

For each value, one `ERROR:` line: the value (masked), the element and the
field (an RFC 6901 pointer into it) that hold it, and a fingerprint. Then one
count, and exit status 1. The ID registry file, if any, is left as it was.

```text
ERROR: loom project: URL=https://example.org/?token=***: holds a credential (https://spdx.org/spdxdocs/demo-48d6...#Package-1 /software_downloadLocation, sha256:34973142468d1a90); remove it from the source, or accept this value with --accept-url-credential sha256:34973142468d1a90 [credentials-unsafe/refused]
ERROR: loom project: 1 URL value(s) in the SBOM hold credentials; no SBOM is written [credentials-unsafe/refused]
```

A value stated in two places is one line, at the first place it stands. The
message codes are in [Network](message-codes-network.md#credentials-unsaferefused).

## Fixing it

Remove the credential from the source (the `pyproject.toml` URL, the
dependency's direct reference, the model card) and generate again. Use `.netrc`,
a credential helper or an environment variable instead. A credential that was in
a project's files is also in its history: treat it as exposed and rotate it.

## Accepting one value

When a value is no secret (an example URL, a public demo token), accept that
value alone, by the fingerprint its `ERROR:` line prints: `sha256:` and 16
lowercase hex digits of the SHA-256 of the whole field value as it stands in
the SBOM. The fingerprint never shows the credential. A longer prefix (up to 64
digits) is accepted too; uppercase is not.

```bash
loom project . --accept-url-credential sha256:34973142468d1a90
```

```toml
[tool.pitloom]
accept-url-credentials = ["sha256:34973142468d1a90"]
```

The flag is repeatable and adds to the `pyproject.toml` list, never replaces
it. An accepted value is stated as written, with one `WARNING:` per value, so
anyone who reads the SBOM reads it too. An accepted fingerprint that matches no
value of the run is warned of too (`matches no URL of this SBOM`). A fingerprint
that is not `sha256:` and 16 to 64 lowercase hex digits is an error that does
not quote it, as a credential may have been pasted by mistake.

`setup.cfg` cannot hold the list; use the flag or a `--config` TOML file.

## Accepting every value

`--allow-url-credentials` (CLI and library) accepts every value of the run, each
with a `WARNING:`. Use it as a last resort. It has no `[tool.pitloom]` key
on purpose: a setting made once for an example URL would later let a real token
through unseen. An `allow-url-credentials` key in `[tool.pitloom]` is ignored,
with `WARNING: allow-url-credentials: CLI only; ignored in [tool.pitloom]`.

## By surface

| Surface | A refusal | Accept one value | Accept every value |
| :--- | :--- | :--- | :--- |
| CLI (`loom project`, `generate`, `wheel`, `model`, `env`, `enrich`, `embed-wheel`, `merge`) | `ERROR:` lines, exit 1, no SBOM (not to stdout with `-o -` either) | `--accept-url-credential`, `accept-url-credentials` | `--allow-url-credentials` |
| Hatchling build hook | The build fails | `accept-url-credentials` in `[tool.pitloom]` | None |
| Python API | `ValueError` carrying the code `credentials-unsafe/refused` | `credentials=CredentialPolicy(accepted=...)` or `PitloomConfig(accept_url_credentials=...)` | `CredentialPolicy(allow_all=True)` |
| `loom.Run` | Refused when the run ends: no fragment is written | `credentials=` as above | as above |
| GitHub Action | The step fails | `args: '--accept-url-credential sha256:...'`, or `accept-url-credentials` in the project's or the `config` file's `[tool.pitloom]` | `args: '--allow-url-credentials'` |

- `embed-wheel --sbom FILE` checks the file it is given: it is embedded
  unchanged, or refused and the wheel left as it was. Only the flags (or
  `credentials=` through `ConfigOverrides`) apply to it; a `pyproject.toml`
  list does not, since the SBOM is not Pitloom's own.
- `loom merge` and `generate_merged_sbom()` check the merged SBOM.

```python
from pitloom import generate_project_sbom
from pitloom.core.credential_policy import CredentialPolicy

sbom = generate_project_sbom(
    ".", credentials=CredentialPolicy(accepted=["sha256:34973142468d1a90"])
)
```

## ID registry

A registry stores a key, an id and its namespace as written, so the same rule
holds there. `IdRegistry.register()`, the `-e` option of `loom id generate` and
a credentialed `--namespace` are refused. A registry file that already holds a credentialed key
or `spdxId`, or a credentialed namespace, is not loaded at all and is left as it
is: `IdRegistry.load()` and `IdRegistry.rebase()` raise, naming the file and the
value (masked), and you remove the entry yourself. `loom id import` and a run's
harvest skip such an SBOM element with a warning (it gets a new id next run).
See [Credentials in a key](id-registry-keys.md#credentials-in-a-key).

## Not detected

Pitloom reads the shapes above; these are not detected, so keep such
credentials out of URLs:

- A `/` in a password (`https://u:p/w@host/x`), and a password that starts with
  `?` or `#` right after `user:`.
- An scp-style address whose user is a bare token (`TOKEN@host:o/r`).
- `state=` and `Policy=` query parameters.
- A percent-encoded URL nested in another URL, other than in a `pkg:` PURL
  qualifier (`?next=https%3A%2F%2Fu%3Ap%40h`).
- A value wrapped in `<>` twice (`<<https://u:pw@host/x>>`), or a direct
  reference's URL wrapped in `<>` (`foo @ <https://u:pw@host/x>`).
- An access token followed by `;` or `#` in a PURL qualifier, and a token with
  a variation selector (U+FE0F) inside it.
- An old Slack workspace or bot token without the digit groups (`xoxa-`,
  `xoxr-`): a documentation word fits its shape.
- A token inside prose, a README or a description: see [What is not
  read](#what-is-not-read).
- An `ssh` user name that looks like a value (`ssh://abcdeftokenvalue@host`) is
  warned of, not refused.
- A file name in a URL field that is scp-shaped (`meet-10:30@ab:c.txt`) is
  refused: accept its fingerprint.
- Logs that are not Pitloom's own: a third-party library's warning, a
  Hatchling traceback and `urllib3` lines are not masked, and a line break in a
  password can split a traceback line so that its parts are not recognised.
- The GitHub Action does not `::add-mask::` its source inputs.
- A `?token=` value of a Git URL still reaches `git`'s command line (visible to
  other users in `ps`) and the clone's `.git/config`; only user information
  (`https://user:token@host`) is kept off them.

Pitloom is not a secret scanner. A credential that no rule here matches, or
that stands in prose, is written to the SBOM as it is in the source.
