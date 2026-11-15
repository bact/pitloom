<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-15
-->

# Credential leak fixes

See also: [message-catalogue-and-skills.md](../design/message-catalogue-and-skills.md)
(the catalogue the new messages are in),
[credential-detect-and-refuse.md](../design/credential-detect-and-refuse.md)
(the follow-up that replaces the strip with detect and refuse), PR 487.

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
  weaker than the others, except the gaps listed under "Tracked, not fixed
  here".
- **Sinks**: every record of the `pitloom` and `pitloom.*` loggers is masked
  (`msg`, `args`, tracebacks, `handleError`) on any handler at any level,
  root and embedder handlers included; records of third-party loggers are
  not covered; `excerpt()`
  and `one_line()` mask before they cut; `kv_line` masks only a value that
  holds a URL; `InvalidURL` text is cut to its class.
- **SBOM**: `export/_spdx3_strip.py` strips the whole `@graph` at the one
  place every surface passes (`Spdx3JsonExporter.to_json`), including
  `pkg:` qualifier values; the dataset PURL is built from the stripped URL.
- **Registry**: `IdRegistry()`, `register()` and `-e` refuse a credentialed
  namespace or key (`id_registry/_credentials.py`); `id import` and harvest
  skip such an element with a warning; `IdRegistry.load()` (and the re-read
  before a save) drops such an entry of the file with a warning
  (`ENTRY_DROPPED_LINE`, same code), so the next save writes the file
  without it; a credentialed namespace in the file is refused. A
  `software_File` key is a file name, never refused as an scp-style
  address.
- **Git**: the user information is taken out of git's arguments and handed to
  it by an ephemeral per-origin helper that reads the child's environment
  (`clone`, `fetch`, `ls-remote`, `checkout` only); trace variables are
  scrubbed; reprs hide the password; a URL git would read differently from
  the masker is refused (`git.url-invalid`); a line break in a password is
  refused (`credentials-unsafe/git-line-break`). The password never reaches
  `.git/config`, since git is never given it (the post-clone rewrite of
  `remote.origin.url` was removed as dead code).
- **Names**: secret-named parameters include bracketed and double-encoded
  forms, joined words (`accesstoken`), and the `session_id` family; ordinary
  names (`sort_key`, `tokenizer`, `country_code`) are kept.

## Tracked, not fixed here

- A `/` or white space in a password; `@[::1]` hosts; `state=`; CloudFront
  `Policy=`; `;jsessionid=` path parameters; an scp-style `S3CRET@host:o/r`
  (no `user:`) is masked nowhere; a percent-encoded URL nested in a
  parameter outside a `pkg:` string.
- Third-party `warnings.warn` text, Hatchling's own traceback and `urllib3`
  log lines print the raw text; the Action does not `::add-mask::` its source
  inputs; a line break in a password can split a traceback line so that its
  parts are not recognised.
- An `ssh` account name is kept with a "kept" warning even when it looks
  like a value (`ssh://abcdeftokenvalue@h`).
- A `?token=` value of a Git URL still reaches git's argv (visible in `ps`)
  and the clone's `.git/config`; only user information is kept off them.
- In free text (a description) a URL ends at white space, a quote or an
  angle bracket, so an apostrophe, quote, space, `<` or `>` in its user
  information is not read as part of it. This is a regression from round 4,
  which read such a password in prose; accepted because the same reading
  rewrote prose (`Open http://host:<port> ... mail a@b.org`), which is worse
  than a rare password with such a character in a description. A URL field
  (a project URL, a dependency URL, an id) reads it whole.
- An scp-style `user:password@host:path` is stripped only when the host has a
  `.` or the path a `/` or starts with `~`; `build:42@ci:linux` and
  `meeting-10:30@room:notes.txt` are left as written, so such a password with
  a dotless host and a slashless path is not stripped.
- A qualifier value of a PURL is encoded again as many times as it was
  decoded to show the credentials (at least once); other encodings inside it
  are unchanged.
- A non-secret parameter value with more than 16 `?` is read as a secret
  (removed from an SBOM, masked in a message), so a crafted query cannot
  nest the reading without limit.
- `loom verify-wheel` with a path 1000 directories deep fails in the standard
  library's `glob.glob` (`cli/commands/utils.py`): exit 1, nothing leaks.
- A weak name nested in a weak name (`?code=1?session=2`,
  `?ticket=1?q=2?sort_key=X`) makes `holds_url_credentials` true, so a registry key or namespace holding
  it is refused as a secret; the strip keeps it unchanged. The masker writes
  `code=***` and `neutral()` writes `code=******` for the nested span.
- A secret after an ampersand or semicolon that follows a nested secret
  moves into the earlier value (`?code=1?token=T&a=1` strips to
  `?code=1?a=1`). Existed before round 7; no leak, the kept value is wrong.
- The `credentials-unsafe/registry` summary does not mention the over-16 `?`
  case; its detail lines do.
- A password that starts with `?` or `#` right after `user:` is not stripped
  (`h:` before `?` is an empty port); the masker still hides it.
- The strip of `https://u:"@SECRET?x@h` leaves `SECRET?x@h` as a host; the
  masker hides it.
- A scp-style address with a password inside prose is not stripped; only a
  field that is one address is.
- A `_key` parameter name outside the listed kinds (`api`, `access`,
  `secret`, `signing`, `subscription`, ...) is kept with a "kept" warning.
- Log masking covers `pitloom` and `pitloom.*` records made through the record
  factory; third-party loggers, `logging.makeLogRecord`, an `extra` key, the
  exception object in `exc_info` and output before `configure_logging` are not.
- Other changes of the 0.24.x line keep `since` 0.24.1, and the skills' floor
  `pitloom >= 0.24.1` stays until the release is cut.
- The user-facing list is "Known gaps" in `docs/dependency-sources.md`.
- Namespace mixing seen in one SBOM: a registry namespace (`ids.example/ns`)
  beside `spdx.org/spdxdocs/demo-<uuid>` ids; unrelated to credentials.
- Not run: the `!f()` helper on Windows (Git for Windows ships the sh it
  needs; the real-git tests are POSIX-only), a SIGKILL during the clone
  itself, pyrefly from the worktree path (run from the repository root; the
  baseline is 11 errors in untouched files).
- `pitloom.loom` programs can now see `register()` raise for a credentialed
  key.
- The advisory framing is the release decision; the change ships as 0.25.0
  (catalogue `since` 0.25.0).

## URL field vs free text

One scanner served two jobs with conflicting rules, so round 5 made the
mode explicit (`whole=` on `strip_url_secrets`, `holds_url_credentials`,
`keeps_url_credential`, `find_urls`; `free_text=` on `userinfo_end`; no default).

- **URL field** (`whole=True`): the value *is* one URL or address. Read as
  `urllib`/git read it: no quote, `<`, `>`, backtick or space ends anything,
  nothing is trimmed from its end, a user information may hold any RFC 3986
  character (`o'brien:pw@h`). A special scheme (`http`, `https`, `ftp`, `ws`,
  `wss`, `file`) is also read after `:/`, `:\\`, `:///`. An address
  `user:password@host:path` loses its password.
- **Free text** (`whole=False`): prose or JSON that holds URLs. The
  authority ends hard at white space, a quote, `<`, `>` or a backtick before
  the last `@` is looked for, so `http://host:port ... mail a@b.org` is
  byte-identical. A password with such a character is a known gap.
- **Masker** (`masked_given_path`, `sanitize_url_credentials`): always the
  widest reading (fail closed): it may hide a host, never a password.
- **Empty port**: `h:` before `?` is a host (`https://h:?x=a@b`), so the strip,
  refusal and Git split leave it; the masker still hides `u:?pw@h`. Gap: a
  password that starts with `?` or `#` right after `user:` is not stripped.

Call sites and their mode:

| Site | Mode |
|------|------|
| `export/_spdx3_strip._stripped_text` (every string of the graph) | `is_whole_url(text)` decides: a string that is one URL or address is a field, else free text |
| `core/purl.strip_purl_secrets`, `build_generic_purl` (qualifier value, decoded to a fixed point) | `is_whole_url(value)` |
| `export/_spdx3_strip._kept_urls`, `messages/url_credentials` (kept warning) | as the strip |
| `core/iri.namespace_problem`, `id_registry/_credentials` (namespace, key, element id) | field (`whole=True`) |
| `extract/remote/_git_credentials` (`split_userinfo`) | field |
| masker call sites (logs, `kv_line`, `ERROR:` lines, path checks) | masker |

Name rules: a name the masker masks is removed from an SBOM, or weak (kept
and told as kept). A `_key` name that is no kind of secret key (`sort_key`)
is weak. A name after a second `?` is a parameter; a secret's value is read
whole.

## Verification

Planted `S3CRET`/`T0KEN` in project URLs, dependency URLs, namespaces and
keys, then ran every surface (CLI `-v`, library, hook, embed, merge, dataset
route, `-o -`): `tests/test_credential_surfaces.py`. Mutation testing of the
new rules was run by reviewers on 64 mutants; survivors have tests.

Round 5 review items, each with a regression test that fails without the
fix:

1. Unbounded nesting of `?` in a query: `MAX_QUERY_MARKS` bounds it
   (`test_a_query_with_a_thousand_question_marks_is_read_without_nesting`);
   `masked_text` never raises, so an error or a log line whose masking fails
   is a fixed text (`test_the_log_text_of_a_failing_masker_is_a_fixed_text`,
   `test_a_url_that_cannot_be_masked_never_prints_raw`).
2. The same URL in a project's `[project.urls]` no longer fails `generate`
   or `project` (`tests/test_credential_deep_query_surfaces.py`).
3. A PEP 508 `name@URL` with no space is read as a direct reference
   (`test_a_pep_508_direct_reference_reads_its_url_as_a_field[no-space]`).
4. A string that only looks like an scp address is not rewritten
   (`test_a_string_that_only_looks_like_an_address_is_not_rewritten`).
5. Punctuation after a direct reference's URL in prose is kept
   (`...[comma]`, `...[full-stop]`).
6. A secret nested after a weak name's value (`?code=1?token=T`) is removed:
   `iter_params(..., weak=False)` from the strip
   (`test_a_secret_nested_after_a_weak_value_is_removed`).
7. A removal for nesting is said as such: the warning's condition ends "or a
   query nested too deeply to read".
