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
(PR 2: the strip replaced by detect and refuse, built), PR 487.

What was built to stop URL credentials (user information, secret-named query
values, git passwords) reaching logs, tracebacks, stdout, git, SBOMs and ID
registry files, what was decided, and what is left.

Since PR 2 a persisted value is **refused, never rewritten**: the SBOM
strip, the registry load-drop and the id-collision rewrite are deleted, and
an SBOM or registry file holding a credential is refused
(`credentials-unsafe/refused`, `credentials-unsafe/registry`); displayed text
(logs, tracebacks, `KEY=VALUE`, `ERROR:` lines) is still **masked**. What PR
2 decided: "Built in PR 2" in
[credential-detect-and-refuse.md](../design/credential-detect-and-refuse.md).
Below, "strip" and "kept" describe PR 487 and PR 1 unless a line says
otherwise.

Revised 2026-11-16 (still PR 2): the default is now **warn**: the SBOM is
written with `WARNING: ... [credentials-unsafe/written]`; refusing is opt in
(`url-credentials = "refuse"`, `--refuse-url-credentials`,
`CredentialPolicy(refuse=True)`). A registry key or file entry follows the
mode; a credentialed namespace is refused in both. Where this page says
"refused" for PR 2, read "refused in the `refuse` mode". Decision record:
"Decision record: warn by default" in
[credential-detect-and-refuse.md](../design/credential-detect-and-refuse.md).

## Root cause

Masking was per call site, so a forgotten site leaked, and the places that
decide where user information ends disagreed (masker, SBOM strip, registry
refusal, git splitter). Fixes act at the sinks and from one shared rule.

## Decisions (user)

- Credentials in user-written project data are STRIPPED from the SBOM with a
  catalogued `WARNING:` (`credentials-unsafe`), once per URL. Reversed in
  PR 2: refused (`ERROR:`, no SBOM) unless accepted by fingerprint.
- Namespaces and registry keys with credentials are REFUSED, not masked.
- An id that holds credentials (a merged third-party fragment's) and every
  reference to it are stripped to the same new id; two ids that differ only
  by credentials are an error (`credentials-unsafe/id-collision`). Retired
  in PR 2: such an id is refused like any other read field.
- Weak names (`code`, `session`, `ticket`, `sid`, `otp`) are KEPT in the
  SBOM, namespaces and keys, and masked in logs; the warning says they are
  kept (`credentials-unsafe`; since PR 2 "the SBOM states it as
  written"). `session_id` and `sessionid` are secrets. A `git@`-style
  account name on an ssh/git URL is kept and said.
- Plain `http://` with credentials: `credentials-unsafe/http-clear` warning,
  then proceed.
- System git credential helpers, `core.askPass` and `GIT_ASKPASS`/`SSH_ASKPASS`
  are reset only when the URL carries user information; a plain URL behaves
  like `git clone` with the user's own helper.

## Built

- **One rule** (`core/url_masking/_userinfo.py`): user information ends at
  the last `@` before the first `/`; a `?` or `#` before that `@` belongs to
  it only when the text before it reads as `user:password` (so
  `https://h?contact=me@x.org` stays a query). The masker, the detector
  (`find_url_credentials`, `holds_url_credentials`) and git's
  `split_credentials` use it
  (`split_userinfo`, `userinfo_end`); a differential test keeps the masker no
  weaker than the others, except the gaps listed under "Tracked, not fixed
  here".
- **Sinks**: every record of the `pitloom` and `pitloom.*` loggers is masked
  (`msg`, `args`, tracebacks, `handleError`) on any handler at any level,
  root and embedder handlers included; records of third-party loggers are
  not covered; `excerpt()`
  and `one_line()` mask before they cut; `kv_line` masks only a value that
  holds a URL; `InvalidURL` text is cut to its class.
- **SBOM** (PR 2, PR 490): `export/_spdx3_credentials/` reads the URL-typed
  fields of the whole `@graph` (the reference fields as ids too, an `identifier`
  of any type, an id percent-decoded, every string of Pitloom's JSON statements
  and each segment of its provenance comment) at the one
  place every surface passes (`Spdx3JsonExporter.to_json`), plus
  `embed-wheel --sbom`, and refuses the SBOM when one holds a credential
  the run does not accept by fingerprint; nothing is rewritten. The dataset
  PURL is built from the URL as given and refused with it. PR 487's
  `export/_spdx3_strip.py` and `core/url_masking/_strip.py` are deleted
  (the URL scanner moved to `core/url_masking/_urls.py`).
- **Registry**: `IdRegistry()`, `register()` and `-e` refuse a credentialed
  namespace or key (`id_registry/_credentials.py`); `id import` and harvest
  skip such an element with a warning; since PR 2 `IdRegistry.load()` and
  `rebase()` (the re-read before a save) refuse a file holding such an
  entry or namespace (`REGISTRY_FILE_REFUSED_LINE`, the path quoted, same
  code) and never
  rewrite it (PR 487 dropped the entry). A
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

Since PR 2 a gap of the detector is "not detected": the value is neither
refused nor rewritten, so it reaches the SBOM or registry file as written,
silently. Rechecked against the PR 2 tree on 2026-11-16.

- Not detected, and not masked: a `/` in a password; `state=`; CloudFront
  `Policy=`; an scp-style `S3CRET@host:o/r` (no `user:`); a
  percent-encoded URL nested in a query value outside a `pkg:` string
  (`?next=https%3A%2F%2Fu%3Ap%40h`). `@[::1]` hosts and `;jsessionid=`
  path parameters are read by the detector and the masker.
- Not detected after PR 490 (each run through the detector on 2026-11-16): a
  `|` in a requirement's password (Pitloom writes it as `/`); the no-slash
  `https:u:p@h` form; a JSON statement's or metadata *key* that is a
  credentialed URL (its values are read); prose fields such as a dataset
  `name` that is a URL (by ruling); free strings not typed as a URL
  (`hashValue`, `software_attributionText`, `standardName`,
  `software_packageVersion`); `DictionaryEntry` values; a JSON statement
  nested too deeply for `json.loads` (a merged fragment can hold one); a
  GitLab (`glpat-`) or Google (`AIza`) key lacking a digit or either letter
  case; a legacy OpenAI `sk-` key without `proj-`, `svcacct-` or `admin-`.
- Third-party `warnings.warn` text, Hatchling's own traceback and `urllib3`
  log lines print the raw text; the Action does not `::add-mask::` its source
  inputs and has no input of its own for the credential flags (PR 3); a line break in a password can split a traceback line so that its
  parts are not recognised.
- An `ssh` account name is weak (warned, never refused) even when it looks
  like a value (`ssh://abcdeftokenvalue@h`).
- A `?token=` value of a Git URL still reaches git's argv (visible in `ps`)
  and the clone's `.git/config`; only user information is kept off them.
  Its refusal before the fetch is PR 3.
- Prose (a description, a README, a comment other than Pitloom's
  provenance line) is never read, by the ruling: a credential there
  reaches the SBOM as written. Secret scanning of prose is other tools'
  job.
- A non-secret parameter value with more than 16 `?` is read as a secret
  (refused in an SBOM, masked in a message), so a crafted query cannot
  nest the reading without limit.
- `loom verify-wheel` with a path 1000 directories deep fails in the standard
  library's `glob.glob` (`cli/commands/utils.py`): exit 1, nothing leaks.
- A password that starts with `?` or `#` right after `user:` is not
  detected (`h:` before `?` is an empty port); the masker still hides it.
- An scp-style address is detected only as a whole value (no white space,
  no dotless-host exemption: `build:42@ci:linux` alone is refused); one
  inside a longer value or prose is not.
- A `_key` parameter name outside the listed kinds (`api`, `access`,
  `secret`, `signing`, `subscription`, ...) is weak (warned, never
  refused).
- Log masking covers `pitloom` and `pitloom.*` records made through the record
  factory; third-party loggers, `logging.makeLogRecord`, an `extra` key, the
  exception object in `exc_info` and output before `configure_logging` are not.
- Release decision: the change ships as 0.25.0, with the advisory framing;
  every unreleased catalogue entry says `since` 0.25.0 (the last tag is
  v0.24.0). The skills' `pitloom >= 0.24.x` floors are not raised here; the
  release cut does.
- The user-facing list is "Not detected" in `docs/url-credentials.md`.
- Not run: the `!f()` helper on Windows (Git for Windows ships the sh it
  needs; the real-git tests are POSIX-only), a SIGKILL during the clone
  itself, pyrefly from the worktree path (run from the repository root;
  today it reports 7 errors, all in files this work does not touch).
- `pitloom.loom` programs can now see `register()` raise for a credentialed
  key.
- From the batch-5 re-check, still not detected after PR 2: (a) a token
  followed by `;` or `#` in a PURL qualifier (`pkg:pypi/x@1?type=AIza<35>;x`;
  the masker and the registry catch it); (b) a value wrapped twice
  (`<<https://u:S3CRET@h/x>>`, `pkg @ <https://u:S3CRET@h/x>`; one-pair
  rule). Not leaks of display: (c) `kv_line` reads a value whole only when
  it starts with a URL; after `<`, a BOM or a space it falls back to line
  mode (stdout values are paths only today); (d) masking twice differs from
  masking once for `pkg:pypi/x@1?vcs_url=ssh://git:S3\tCRET@h/x` (no leak).
- From the batch-6 check: (a) a requirement such as
  `foo @ https://e.example/h/ghp_<36>` is refused since PR 2 (the dependency
  field and Pitloom's provenance notes are read as whole values); (b)
  U+FE0F (a variation selector) is `Mn`, not `Cf`: inside a token it splits
  the token; the detector and the masker agree where it ends. Its (c), (d)
  and (e) were faults of the strip and its warnings, deleted in PR 2.
- Accepted false positives (batch-8 check): `glptt-` followed by 40 hex
  digits is a token, so a Git SHA right after the literal `glptt-` is
  refused (31 of 20,000 sampled slugs, hashes and words); a 35-character
  CamelCase slug with a digit after `AIza`
  (`AIzaGitlabInstallAppRefresh-2000-deploy`) is still a token, since the
  digit-and-both-cases rule cannot tell it from a random key.
- Token shapes: the a8425fb5 AWS rows (`AKIAT0KEN12345678901`, `0` and `1`
  outside base32) are none on purpose, unlike every other earlier row,
  which the drift test keeps found; `test.pypi.org` macaroons are read from
  the version-2 macaroon layout (`AgE`), not from a published
  rule (UNCERTAIN beyond the two locations checked): any `pypi-AgE` body of
  50 or more characters is a token, where gitleaks names only the
  `pypi.org` location (`AgEIcHlwaS5vcmc`).
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
mode explicit (`whole=` on the strip and its helpers). PR 2 deleted the
strip and the mode with it; two readings are left:

- **Detector** (`find_url_credentials`, `holds_url_credentials`): a
  URL-typed value as a whole only, never prose ("Detector sweep (PR 1)"
  below). Read as `urllib`/git read a URL field: no quote, `<`, `>`,
  backtick or space ends anything, a user information may hold any RFC 3986
  character (`o'brien:pw@h`), and a scheme is read as the masker reads one.
- **Masker** (`masked_given_path`, `sanitize_url_credentials`): display
  only, free text included, always the widest reading (fail closed:
  `userinfo_end(..., widest=True)`): it may hide a host, never a password.
- **Empty port**: `h:` before `?` is a host (`https://h:?x=a@b`), so the
  refusal and the Git split leave it; the masker still hides `u:?pw@h`
  (gap listed under "Tracked, not fixed here").

Call sites and their reading:

| Site | Reading |
|------|---------|
| `export/_spdx3_credentials` (URL-typed fields of the graph, provenance notes; `embed-wheel --sbom`) | detector, each field as a whole value |
| `core/iri.namespace_problem`, `id_registry/_credentials` (namespace, key, element id; `load()`, `rebase()`) | detector, `embedded` (a URL or token anywhere in it) |
| `extract/remote/_git_credentials` (`split_userinfo`) | field |
| masker call sites (logs, `kv_line`, `ERROR:` lines, path checks) | masker |

Name rules: a name the masker masks is refused in an SBOM, or weak (warned,
stated as written). A `_key` name that is no kind of secret key
(`sort_key`) is weak. A name after a second `?` is a parameter; a secret's
value is read whole.

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
2. The same URL in a project's `[project.urls]` no longer crashes
   `generate` or `project`; since PR 2 it is refused with a fingerprint and
   accepted by it (`tests/test_credential_deep_query_surfaces.py`).
3. A PEP 508 `name@URL` with no space is read as a direct reference
   (`test_a_pep_508_direct_reference_reads_its_url_as_a_field[no-space]`).
4. A string that only looks like an scp address is not rewritten
   (`test_a_string_that_only_looks_like_an_address_is_not_rewritten`).
5. Punctuation after a direct reference's URL in prose is kept
   (`...[comma]`, `...[full-stop]`).
6. A secret nested after a weak name's value (`?code=1?token=T`) is found
   (`iter_params(..., weak=False)`; removed by the strip until PR 2, refused
   since).
7. A finding for nesting is said as such: the condition ends "or a query
   nested too deeply to read".

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
`urn:x:https://u:p@h/ns`, `src/https:/u:p@h/x`); the 105,836 file names and
relative paths of this tree, the venv's `lib` and `spdx-python-model` gave no
refusal. The masker (`_mask.py`,
`masked_given_path`) still reads free text, for display only, and hides every hit (tokens as `ghp_***`, a qualifier holding a hit
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
  in use). A GitLab token's 20 characters, as in a8425fb5, and a Google
  key's 35 hold a digit, an upper- and a lower-case letter: a random
  base-64 body lacks a digit about 3.4 times in 100 (GitLab) and 2.6 times
  in 1,000 (Google), and is then missed; gitleaks needs one upper case only
  for GitLab, which matched about 1,100 more of 20,000 slugs. Counts after
  batch 8 unchanged: 133 rows, 43 changed by the strip, 85 refused.
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
  and one decode loop (`qualifier_levels`), both in
  `core/url_masking/_hits.py`, serve the detector and the masker (and, in
  PR 1, the strip in `core/purl.py`); a differential test compares the
  deciders on 600 random PURLs.
- In PR 1 the strip left some values the detector refuses, each said once
  as "stated as written" (`UNREMOVED_LINE`); PR 2 deleted both, and such a
  value is refused.
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
  `glpat-`/`gldt-`/`glrt-` (20 or more, a digit, an upper- and a lower-case
  letter among the first 20, as in a8425fb5, so a slug such as
  `glpat-token-rotation-guide-v2` is none), `glcbt-` (optional `<1-5>_`
  then the same 20), `glptt-` (40 hex, or the same 20), `gloas-` (64, or
  the same 20), OpenAI `sk-proj-`/`sk-svcacct-`/`sk-admin-`
  (58 or 74, `T3BlbkFJ`, 58 or 74), Anthropic `sk-ant-api03-`/
  `sk-ant-admin01-` (93 then `AA`), Google `AIza` (35, the same three
  kinds of character), Slack `xox[abeoprs]-` (two digit groups and 8
  letters or digits, a8425fb5's shape) and the gitleaks shapes fixed by
  digit groups or length (`xoxb-`, `xoxe-`, legacy `xoxo-`/`xoxs-`,
  `xoxe.xoxb-`/`xoxe.xoxp-`) and `xapp-` (the loose gitleaks legacy
  workspace and bot shapes are not read, see above), Hugging Face
  `hf_`/`api_org_` (34 letters), AWS `AKIA`/`ASIA` (16 base32:
  `ASIAPACIFICREGION123` is none, AWS's example `AKIAIOSFODNN7EXAMPLE` is
  one), PyPI `pypi-AgE` (50 or more: any version-2 macaroon, TestPyPI
  included), npm `npm_` (36). A fixed-length body
  followed by another body character is none; an open-ended body runs to
  its last body character, so masking leaves nothing of it. UNCERTAIN:
  newer GitLab token formats, which the shape may not match; the OpenAI,
  Anthropic and Google shapes are gitleaks' (read 2026-11-16), not the vendors' own
  documents. No bare `sk-` (too many words and hashes start so), and no
  legacy OpenAI `sk-` key.
- scp-style addresses count only as a whole value (no white space), with
  no dotless-host exemption: `build:42@ci:linux` alone is refused.
- The strip changed too, through the shared prefix table
  (`_tokens.TOKEN_PREFIXES`): a user name with a token prefix (`hf_`,
  `pypi-`, `npm_`, `api_org_`, `glrt-`...) is no `ssh` account name, so
  `ssh://npm_abc@h/r` was stripped, not kept (refused since PR 2).
- Unchanged gaps: `?state=`, a scheme-less `/x?token=` and the rest of
  "Tracked, not fixed here".
- Linear on 1 MiB inputs (late `://` or `@`, one-slash schemes, many `?`,
  many secrets, deep and many PURL qualifiers, tokens, requirements with
  long white space or `[`, scp, subpaths, query scp values): 8 such inputs
  of 1 MiB took 0.1 to 2.9 s for the detector and the masker (message and
  line) together (macOS, Python 3.10; the growth-ratio tests bound the
  rest). Two quadratic reads were found by review and fixed: each scp
  address of a text read to its end (scp is now read only as a whole
  value), and the requirement pattern's two adjacent `\s*` around optional
  extras (`"a" + " " * n + "x"`; now one `\s*`
  inside the optional extras group). Every regular expression of
  `core/url_masking` was then timed on runs of white space, `[`, `@`, `:`,
  `/`, `%` and token prefixes at two sizes, flagging a growth beyond
  linear.
  The test (`test_each_view_is_linear`) times one run of each view at a
  size grown from 1 KiB by 4 times until it takes 3 ms and 4 clock steps
  (`perf_counter`), then at 16 times that size: the growth must stay under
  32 (linear 16, quadratic 256), the least of up to three tries. The file
  takes about 16 s serial and 14.7 s under coverage (Python 3.10, macOS),
  3 min on an emulated 15.6 ms clock. It fails a8425fb5's requirement
  pattern (growth 251, 252), an scp masker reading to the end per match
  (`scp` 145, `query-scp` 103) and a `?` count redone from each place to
  the end (`many-marks` 160, `semicolons` 91). Two 1 MiB rows (white
  space, scp runs) are skipped when a coverage tracer runs.
