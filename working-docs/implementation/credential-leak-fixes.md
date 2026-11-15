<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-16
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
- A qualifier value of a PURL is encoded again exactly as many times as it
  was decoded to show the credentials (none for a value stripped as
  written: `a%2Bb.zip` stays, PR 1); other encodings inside it are
  unchanged.
- A non-secret parameter value with more than 16 `?` is read as a secret
  (removed from an SBOM, masked in a message), so a crafted query cannot
  nest the reading without limit.
- `loom verify-wheel` with a path 1000 directories deep fails in the standard
  library's `glob.glob` (`cli/commands/utils.py`): exit 1, nothing leaks.
- Fixed by the detector (PR 1, "Detector sweep" below): a weak name nested
  in a weak name (`?code=1?session=2`) made `holds_url_credentials` true.
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
- Every unreleased catalogue entry says `since` 0.25.0 (the last tag is
  v0.24.0; the release ships as 0.25.0). Release decision: the skills'
  `pitloom >= 0.24.x` floors are not raised here; the release cut does.
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
- The SBOM strip (live until PR 2) does not remove what it does not read:
  `s3:/u:p@h/x`, `hf:/datasets/x?token=`, `git+ssh:/h/x?token=`,
  `hf:\\h?access_token=` (its URL start knows only `http`, `https`, `ftp`,
  `ws`, `wss`, `file` after `:/`), an scp-style address nested in a query
  value or a PURL subpath, a `?private_token=` PURL qualifier and a token in
  a URL path. Not widened (PR 2 deletes the strip): each such value the
  detector refuses is said once, masked, as stated as written
  (`credentials-unsafe`, "which the SBOM states as written"); a token in a
  URL path inside free text (a provenance comment) is not (batch-6 item
  (a) below). The strip reads a value as the detector does
  (`normalised`: past format characters, which go from a stripped value,
  and inside one enclosing `<>` or quote pair).
- For PR 2 (from the batch-5 re-check), not fixed here: (a) a token
  followed by `;` or `#` in a PURL qualifier (`pkg:pypi/x@1?type=AIza<35>;x`)
  gets no finding, though the masker and the registry catch it; (b) a
  value wrapped twice (`<<https://u:S3CRET@h/x>>`,
  `pkg @ <https://u:S3CRET@h/x>`) is stripped by the strip while the
  detector is silent (one-pair rule); (c) `kv_line` reads a value whole
  only when it starts with a URL; after `<`, a BOM or a space it falls back
  to line mode (stdout values are paths only today); (d) masking twice
  differs from masking once for
  `pkg:pypi/x@1?vcs_url=ssh://git:S3\tCRET@h/x` (no leak).
- For PR 2 (from the batch-6 check), not fixed here: (a) a requirement
  such as `foo @ https://e.example/h/ghp_<36>` reaches the SBOM's
  provenance comment and annotation silently: the detector does not read a
  token in a URL path inside free text and the strip never removes a
  token, so "each such value is said once" is false for this case; PR 2
  refuses the dependency field before any derived text is written. (b)
  U+FE0F (a variation selector) is `Mn`, not `Cf`: inside a token it
  splits the token; the detector and the masker agree where it ends. (c)
  Once the strip removes something from a value it drops every format
  character of the value, prose included (a zero-width joiner in emoji or
  Indic text is lost); documented in `docs/dependency-sources.md`. (d)
  Warnings built from JSON annotation statements come out garbled
  (`URL=https://***:***@e.example/h"}},"kind":"fields","schema":`,
  `URL=u200bhttps://...`); older. (e) Two mutants survive and look
  equivalent: `end - start > 1` read as `>= 1` in `split_enclosed` (a
  one-character value cannot be a pair), and the kept line's once-key
  suffix `:kept` dropped (a kept URL is never one the strip changed, so it
  never shares the stripped line's key).
- Token shapes: the a8425fb5 AWS rows (`AKIAT0KEN12345678901`, `0` and `1`
  outside base32) are none on purpose, unlike every other earlier row,
  which the drift test keeps found; `test.pypi.org` macaroons are read from
  the version-2 macaroon layout (`AgE` + location), not from a published
  rule (UNCERTAIN beyond the two locations checked).
- `_check_id_collisions` compares element ids only: a reference to an id
  that is no element of the graph can strip onto an existing element's id
  silently. PR 2 deletes the strip.
- For PR 3 (Git hardening), not this PR: a Git password holding `%00`
  raises a bare `ValueError`, not a `RemoteSourceError` (no leak;
  `_git_credentials.py:164`, `_git_run.py:324`, `_git_run.py:425`); the
  `-c credential.<origin>.helper` key takes a host holding `=`, white space
  or `!` unchecked (it could not run a helper); the environment scrub passes
  `GIT_SSL_NO_VERIFY`, `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`,
  `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG` and
  `GIT_EXEC_PATH`.

## URL field vs free text

One scanner served two jobs with conflicting rules, so round 5 made the
mode explicit: `whole=` on `strip_url_secrets`, `keeps_url_credential` and
`find_urls`, `free_text=` on `userinfo_end`, no default. The detector
(`find_url_credentials`, `holds_url_credentials`, PR 1) has no mode: it
reads a URL-typed value as a whole only.

- **URL field** (`whole=True` for the strip): the value *is* one URL or
  address. Read as `urllib`/git read it: no quote, `<`, `>`, backtick or
  space ends anything, nothing is trimmed from its end, a user information
  may hold any RFC 3986 character (`o'brien:pw@h`). A special scheme
  (`http`, `https`, `ftp`, `ws`, `wss`, `file`) is also read after `:/`,
  `:\\`, `:///`. An address `user:password@host:path` loses its password.
- **Free text** (`whole=False` for the strip): prose or JSON that holds
  URLs. The authority ends hard at white space, a quote, `<`, `>` or a
  backtick before the last `@` is looked for, so `http://host:port ... mail
  a@b.org` is byte-identical. A password with such a character is a known
  gap.
- **Detector** (`find_url_credentials`): a whole value only, never prose
  ("Detector sweep (PR 1)" below); a URL value is read as a URL field, and
  as the masker reads a scheme (`find_urls(..., wide=True)`).
- **Masker** (`masked_given_path`, `sanitize_url_credentials`): always the
  widest reading (fail closed): it may hide a host, never a password.
- **Empty port**: `h:` before `?` is a host (`https://h:?x=a@b`), so the
  strip, refusal and Git split leave it; the masker still hides `u:?pw@h`.
  Gap: a password that starts with `?` or `#` right after `user:` is not
  stripped.

Call sites and their mode:

| Site | Mode |
|------|------|
| `export/_spdx3_strip._stripped_text` (every string of the graph) | `is_whole_url(text)` decides: a string that is one URL or address is a field, else free text |
| `core/purl.strip_purl_secrets`, `build_generic_purl` (qualifier value, decoded to a fixed point) | `is_whole_url(value)` |
| `export/_spdx3_strip._kept_urls`, `messages/url_credentials` (kept warning) | as the strip |
| `core/iri.namespace_problem`, `id_registry/_credentials` (namespace, key, element id) | detector (`find_url_credentials`, whole value only) |
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

## Detector sweep (PR 1)

What the detector reads (user ruling, 2026-11-15): URL-typed fields as a
whole value; prose is out of scope. `find_url_credentials` and
`holds_url_credentials` (`core/url_masking/_detect.py`, on the hits of
`_hits.py`) have no free-text reading: a value is read only when, as a
whole, it is a URL, a PEP 508 requirement with a direct reference, an
scp-style address or a PURL (each qualifier value read so, as written and
after each of 5 percent-decodes). A sentence that mentions a credentialed
URL, an AWS key or `build:42@ci:linux` is never a finding: secret scanning
of prose is other tools' job, and refusing README text blocks builds. An
identifier Pitloom stores (an ID registry key, id or namespace) is never
prose, so a URL or a token anywhere in it is read too (`embedded`:
`urn:x:https://u:p@h/ns`, `src/https:/u:p@h/x`); 51,423 real file names
(this tree, the venv's `lib`, the fixtures, `spdx-python-model`) gave no
refusal the whole-value reading does not. The masker (`_mask.py`, `masked_given_path`) still reads free text, for display
only, and hides every hit (tokens as `ghp_***`, a qualifier holding a hit
once decoded as `key=***`), so a refusal message shows nothing it refuses.

Probe corpus `tests/core/url_masking/_probe_corpus.py`: 133 rows with
planted `S3CRET`/`T0KEN`, each with the base strip's result and the reviewed
refusal; 17 `prose-` rows must never be refused.

- The strip changed 43 rows; the detector refuses the 37 that are values.
  The other 6 are prose (a URL, a requirement or a 17-`?` query inside a
  sentence, and a PURL `note` qualifier whose decoded value is a sentence),
  which the strip rewrote and the detector leaves, by the ruling. 85 rows
  are refused in all (one token row per prefix, the Slack ones included).
- Token shapes: gitleaks where its shape is fixed by digit groups, length
  or charset; never narrower than a8425fb5 (a seeded drift test, and a
  300,000-string sweep with no miss), but for AWS key ids, read as base32
  on purpose. The loose gitleaks legacy shapes (`xoxa-`/`xoxr-` workspace,
  `xoxb-` legacy bot) fit documentation words, so they are not read: such
  a token without the digit groups is missed (UNCERTAIN how many are still
  in use).
- A value is read as a reader reads it: format characters (Unicode `Cf`: a
  byte order mark, a zero-width space, also inside a scheme) dropped, and
  one enclosing `<>` or quote pair (`<https://...>`); a finding's view is
  then the value as written. The masker drops a format character only when
  that shows a credential, so a bidirectional override stays visible.
- A requirement's URL is its first word after `@`; the rest of the line (a
  marker, a comment, `--hash=...`) is not read.
- A secret query value runs over `;` (`?token=S3C;RET`), as `parse_qsl`
  (Python 3.10+) and WHATWG read it, in the detector, the masker and the
  strip; a parameter a `;` opens (a path parameter, `;jsessionid=`) ends at
  the next `;` as before. A message line reads a password through a tab or
  a line break (a URL parser deletes them); a `KEY=VALUE` value that starts
  with a URL is read whole (`cli/kv_output.py`); a URL in a log sentence
  still ends at other white space (documented gap).
- One PURL splitter (`purl_qualifiers`: a `#` stays in the last qualifier)
  and one decode loop (`qualifier_levels`) serve the detector, the masker
  and the strip (`core/purl.py`); a differential test compares the four
  deciders on 600 random PURLs.
- The strip leaves some values the detector refuses (an access token, a
  one-slash scheme other than the six it knows, a nested or subpath
  scp-style address, a secret-named PURL qualifier): each is said once,
  masked, "which the SBOM states as written" (`UNREMOVED_LINE`),
  on generate, the library, the hook, `embed-wheel` and `merge` (a property
  and an element id).
- Old `holds_url_credentials` missed 5 values: a `download_url` qualifier
  encoded once, twice or five times (also `PKG:`) and an encoded `?token=`.
  A qualifier still changed by the fifth decode is a `nesting` finding.
- A value is read after stripping the white space around it (a decoded
  qualifier value too). A value that starts with a URL is read whole, to
  its end: white space is a character of a URL, and every URL in it is read
  (conservative: `https://h/x see https://u:p@h2/y` is refused). An
  scp-style address holds no white space (`alice:pw@h:o/r trailing` is
  prose, as is `build:42@ci:linux now`). A requirement's marker (`;`) or
  comment (`#`) after white space is not part of its URL.
- Nested values: a URL's query value is read as a whole scp-style address
  (`?next=alice:pw@h:o/r`) and a URL in it as a URL; a PURL qualifier value
  as a whole value or a whole access token (a qualifier named like a secret,
  `token=...`, is a hit as written); the PURL subpath (after its first `#`,
  with or without qualifiers, at each decode depth) as a path, for a URL
  anywhere in it, a token or a whole scp-style address. The masker hides
  each: a qualifier as `key=***`, a subpath as `#***`.
- Accepted by the ruling (regressions against the free-text `holds`, not
  refused now): a URL inside a value of no kind above, such as
  `urn:x:https://u:p@h` as a namespace or the File key
  `src/https:/u:p@h/x`; a PURL qualifier whose decoded value is a sentence
  mentioning a URL. The over-fire `?code=1?session=2` is now weak only.
- A URL value is read as the masker reads it: any scheme after one `/` or
  after backslashes (`s3:/u:p@h`, `ssh:\\u:p@h`, `s3:/h/x?access_token=`),
  with a user information unless a path separator precedes the scheme
  (`/x/T10:/a@b` is a path), and white space or a quote inside it is part
  of it (`https://h/a b?token=T`, `https://x y:pw@h/x`).
- Token shapes (`_tokens.py`) follow the gitleaks rule set
  (`config/gitleaks.toml`, read 2026-11-16) and count inside a URL value
  (path segment, query value, user information, also after a
  percent-encoded character), as a whole PURL qualifier value, or in a
  subpath: GitHub `gh[porsu]_` (36) and `github_pat_` (22 `_` 59), GitLab
  `glpat-`/`gldt-`/`glrt-` (20 or more, one upper case among the first 20,
  no digit needed: a random draw misses about 3 in 100,000, and a lower-case
  slug such as `glpat-token-rotation-guide-v2` is none), `glcbt-`, `glptt-`
  (40 hex), `gloas-` (64), OpenAI `sk-proj-`/`sk-svcacct-`/`sk-admin-`
  (58 or 74, `T3BlbkFJ`, 58 or 74), Anthropic `sk-ant-api03-`/
  `sk-ant-admin01-` (93 then `AA`), Google `AIza` (35), Slack `xoxb-`/`xoxp-`/`xoxe-`/`xapp-` (the
  legacy `xoxa-`/`xoxr-`/`xoxs-` dropped), Hugging Face `hf_`/`api_org_`
  (34 letters), AWS `AKIA`/`ASIA` (16 base32: `ASIAPACIFICREGION123` is
  none, AWS's example `AKIAIOSFODNN7EXAMPLE` is one), PyPI
  `pypi-AgEIcHlwaS5vcmc` (50 or more), npm `npm_` (36). A fixed-length body
  followed by another body character is none; an open-ended body runs to
  its last body character, so masking leaves nothing of it. UNCERTAIN:
  newer GitLab token formats and TestPyPI tokens (another location in
  the macaroon), which the shape may not match; the OpenAI, Anthropic and
  Google shapes are gitleaks' (read 2026-11-16), not the vendors' own
  documents. No bare `sk-` (too many words and hashes start so), and no
  legacy OpenAI `sk-` key.
- scp-style addresses count only as a whole value (no white space), with
  no dotless-host exemption: `build:42@ci:linux` alone is refused.
- The strip changed too, through the shared prefix table
  (`_tokens.TOKEN_PREFIXES`): a user name with a token prefix (`hf_`,
  `pypi-`, `npm_`, `api_org_`, `glrt-`...) is no `ssh` account name, so
  `ssh://npm_abc@h/r` is now stripped, not kept.
- Unchanged gaps: `?state=`, a scheme-less `/x?token=` and the rest of
  "Tracked, not fixed here".
- Linear on 1 MiB inputs (late `://` or `@`, one-slash schemes, many `?`,
  many secrets, deep and many PURL qualifiers, tokens, requirements with
  long white space or `[`, scp, subpaths, query scp values): at most about
  6 s for the detector (as a value and as a PURL qualifier) and the masker
  (message and line) together, the slowest being 262,144 one-slash
  schemes. Two quadratic reads were found by review and fixed: each scp
  address of a text read to its end (scp is now read only as a whole
  value), and the requirement pattern's two adjacent `\s*` around optional
  extras (`"a" + " " * n + "x"`: about 20 minutes at 1 MiB; now one `\s*`
  inside the optional extras group). Every regular expression of
  `core/url_masking` was then timed on runs of white space, `[`, `@`, `:`,
  `/`, `%` and token prefixes at two sizes, flagging a growth beyond
  linear.
  The test (`test_each_view_is_linear`) checks each view's time ratio at
  4 KiB and 16 KiB (best of three, bound 8x), about 6 s serial under
  coverage, and catches the old requirement pattern; two 1 MiB rows
  (white space, scp runs) are skipped when a coverage tracer runs.
