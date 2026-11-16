---
Created: 2026-11-16
Last-Modified: 2026-11-16
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# A URL value refused for a credential

See also: [messages-network.md](messages-network.md) (the
`credentials-unsafe` codes, generated from the catalogue),
[id-registry.md](id-registry.md) (the ID registry's own refusals).

From 0.25.0, Pitloom never rewrites a value it writes: an SBOM whose
URL-typed field holds a credential is refused, and nothing is removed.

## What is read, what is refused

- **Read**: URL-typed fields only, each as a whole value: a download
  location, a home page, a PURL (its qualifiers decoded), an external
  reference's locator, an element id or namespace, and the notes of
  Pitloom's own provenance (annotation and `Metadata provenance:` comment).
  A name, a description, README text or any other prose is never read.
- **Refused** (`ERROR:`, exit 1): a user name and password
  (`https://user:pass@host`), a query parameter named like a secret
  (`token=`, `api_key=`, `password=`, ...), an access token's shape
  (`ghp_...`, `glpat-...`, `hf_...`, `AKIA...`), an scp-style address with
  a password, or a query nested or encoded too deeply to read.
- **Warned only** (`WARNING: ... [credentials-unsafe]`, exit 0): a `code`,
  `session`, `ticket`, `sid` or `otp` parameter, another ending in `_key`
  that names no kind of secret key (`sort_key`; `api_key` is refused), or
  an `ssh` user name alone (`git@`). The SBOM states it as written;
  relay the line.

Every surface that writes an SBOM checks it: `loom generate`, `project`,
`wheel`, `model`, `env`, `enrich`, `merge`, `embed-wheel` (its `--sbom
FILE` too), the Hatchling build hook (the build fails) and the library
(`ValueError` carrying the code).

## The lines

One line per value, then a count; no SBOM is written:

```text
ERROR: loom project: URL=https://***:***@h.example/x: holds a credential (<element id> /software_downloadLocation, sha256:<16 hex>); remove it from the source, or accept this value with --accept-url-credential sha256:<16 hex> [credentials-unsafe/refused]
ERROR: loom project: 1 URL value(s) in the SBOM hold credentials; no SBOM is written [credentials-unsafe/refused]
```

The URL is masked (`***`); the parentheses name the element and the field
(an RFC 6901 pointer into it) and the value's fingerprint, the SHA-256 of
the whole field value. Never try to recover the masked part.

## What to tell the user, in order

1. **Which value and where**: the URL as the line shows it, the element and
   the field. You may point to where it likely comes from (a
   `[project.urls]` entry, a dependency's direct URL, a fragment) by
   reading their files; do not edit them.
2. **It is exposed**: a credential in a project's files is also in its
   history, and in any SBOM, log or build output already shared. They
   should treat it as exposed and rotate it, then remove it from the source
   and generate again.
3. **Only once the user confirms that this value is no secret** (an example
   URL in documentation, a placeholder), offer to accept that value alone:
   re-run with `--accept-url-credential sha256:<hex>` copied from its line
   (repeatable, one per value), or list it in `pyproject.toml`:
   `[tool.pitloom] accept-url-credentials = ["sha256:<hex>"]` (ask before
   editing the file). The build hook reads the `pyproject.toml` list only;
   `loom merge` and `embed-wheel --sbom FILE` read the flag only. Later runs then print
   `WARNING: ... [credentials-unsafe/accepted]`: expected, relay it once.
4. **Never suggest `--allow-url-credentials`**: it keeps every such value,
   present and future. If the user asks for it by name, say so and that a
   fingerprint is the narrower choice. In `[tool.pitloom]` it is ignored
   (`WARNING: allow-url-credentials: CLI only; ignored in [tool.pitloom]
   [config-unsafe/cli-only]`).

A fingerprint that matches no value of the SBOM prints `WARNING: Options:
FINGERPRINT=sha256:<hex>: matches no URL of this SBOM [option-no-effect]`
(the value changed or is gone): suggest removing that entry.

**Non-interactive** (no way to ask): report the `ERROR:` lines as printed
and the rotate advice, and stop. Do not accept a fingerprint, re-run with
a flag or edit a file.
