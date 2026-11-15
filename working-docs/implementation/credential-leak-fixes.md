<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-15
-->

# Credential leak fixes

See also: [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the catalogue the new messages are in), PR 487.

What was built to stop URL credentials (user information, secret-named query
values, git passwords) reaching logs, tracebacks, stdout, git, SBOMs and ID
registry files, what was decided, and what is left.

## Root cause

Masking was per call site, so a forgotten site leaked, and the places that
decide where user information ends disagreed (masker, SBOM strip, registry
refusal, git splitter). Fixes act at the sinks and from one shared rule.

## Decisions (user)

- Credentials in user-written project data are STRIPPED from the SBOM with a
  catalogued `WARNING:` (`credentials-unsafe`), once per URL.
- Namespaces and registry keys with credentials are REFUSED, not masked.
- An id that holds credentials (a merged third-party fragment's) and every
  reference to it are stripped to the same new id; two ids that differ only
  by credentials are an error (`credentials-unsafe/id-collision`).
- Weak names (`code`, `session`, `ticket`, `sid`, `otp`) are KEPT in the
  SBOM, namespaces and keys, and masked in logs; the warning says they are
  kept (`credentials-unsafe`, "kept" line). `session_id` and `sessionid` are
  secrets. A `git@`-style account name on an ssh/git URL is kept and said.
- Plain `http://` with credentials: `credentials-unsafe/http-clear` warning,
  then proceed.
- System git credential helpers, `core.askPass` and `GIT_ASKPASS`/`SSH_ASKPASS`
  are reset only when the URL carries user information; a plain URL behaves
  like `git clone` with the user's own helper.

## Built

- **One rule** (`core/url_masking/_userinfo.py`): user information ends at
  the last `@` before the first `/`; a `?` or `#` before that `@` belongs to
  it only when the text before it reads as `user:password` (so
  `https://h?contact=me@x.org` stays a query). The masker, `strip_url_secrets`,
  `holds_url_credentials` and git's `split_credentials` use it
  (`split_userinfo`, `userinfo_end`); a differential test keeps the masker no
  weaker than the others.
- **Sinks**: the log handler masks every record (`msg`, `args`, tracebacks,
  `handleError`), so root and embedder handlers get masked text; `excerpt()`
  and `one_line()` mask before they cut; `kv_line` masks only a value that
  holds a URL; `InvalidURL` text is cut to its class.
- **SBOM**: `export/_spdx3_strip.py` strips the whole `@graph` at the one
  place every surface passes (`Spdx3JsonExporter.to_json`), including
  `pkg:` qualifier values; the dataset PURL is built from the stripped URL.
- **Registry**: `IdRegistry()`, `register()` and `-e` refuse a credentialed
  namespace or key (`id_registry/_credentials.py`); `id import` and harvest
  skip such an element with a warning. A `software_File` key is a file
  name, never refused as an scp-style address.
- **Git**: the user information is taken out of git's arguments and handed to
  it by an ephemeral per-origin helper that reads the child's environment
  (`clone`, `fetch`, `ls-remote`, `checkout` only); trace variables are
  scrubbed; reprs hide the password; a URL git would read differently from
  the masker is refused (`git.url-invalid`); a line break in a password is
  refused (`credentials-unsafe/git-line-break`). The password never reaches
  `.git/config`.
- **Names**: secret-named parameters include bracketed and double-encoded
  forms, joined words (`accesstoken`), and the `session_id` family; ordinary
  names (`sort_key`, `tokenizer`, `country_code`) are kept.

## Tracked, not fixed here

- A `/` or white space in a password; `@[::1]` hosts; `state=`; CloudFront
  `Policy=`; `;jsessionid=` path parameters; an scp-style `S3CRET@host:o/r`
  (no `user:`) is masked nowhere; a percent-encoded URL nested in a
  parameter outside a `pkg:` string.
- Third-party `warnings.warn` text and Hatchling's own traceback print the
  raw exception; the Action does not `::add-mask::` its source inputs.
- Namespace mixing seen in one SBOM: a registry namespace (`ids.example/ns`)
  beside `spdx.org/spdxdocs/demo-<uuid>` ids; unrelated to credentials.
- Not run: the `!f()` helper on Windows (Git for Windows ships the sh it
  needs; the real-git tests are POSIX-only), a SIGKILL during the clone
  itself, pyrefly from the worktree path (run from the repository root; the
  baseline is 11 errors in untouched files).
- `pitloom.loom` programs can now see `register()` raise for a credentialed
  key.
- 0.24.1 or 0.25.0 for this change, and the advisory framing, are the
  release decision.

## Verification

Planted `S3CRET`/`T0KEN` in project URLs, dependency URLs, namespaces and
keys, then ran every surface (CLI `-v`, library, hook, embed, merge, dataset
route, `-o -`): `tests/test_credential_surfaces.py`. Mutation testing of the
new rules was run by reviewers on 64 mutants; survivors have tests.
