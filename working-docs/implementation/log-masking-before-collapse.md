---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Log masking (#544): mask before collapse and escape; header, ANSI, scp shapes

See also: [log-masker-escaped-tokens.md](log-masker-escaped-tokens.md)
(#526, its "Left open" list is this PR's source),
[message-catalogue-sweep-b-plan.md](message-catalogue-sweep-b-plan.md)
("For sweep C", masking items), [roadmap.md](../design/roadmap.md) ("Log masker
leftovers"), `docs/url-credentials.md` (what a user reads).

Reference tree 4c194136 (main 4ef7961d plus #543, `%20` ends a run). Every
"reproduced" item was run there with a probe; the prototype of the design
below was built in a scratch copy and run against the same probes, a
366-text corpus (the detector probe corpus, the auth-scheme prose rows and
70 header, scp, ANSI and multi-line texts, each also with a trailing tab so
`loggable()` escapes it) through 10 views, the full test suite and 16 new
adversarial shapes.

**The `TOKEN_RE` root cause is closed.** #526's `word_start()` fixed the
lookbehind that read the `t` of `\t` as a word (`remote: token:\tghp_...`,
`x\x1bghp_...`, `x\u202eghp_...` all print `ghp_***` at 4c194136). What is
left are two causes, not one regex: text is escaped, collapsed or split
*before* the masker reads it (M1 to M4), and shapes the masker never read
(M5 to M9). `message-catalogue-pr14-build.md:231` still calls it open (M10).

## 1. Scope

| Id | What | Where (4c194136) | Evidence | User-visible effect | SBOM / stderr change |
| --- | --- | --- | --- | --- | --- |
| M1 | Dropping a Hub request id glues a token to the word before it: `failure_text(RuntimeError("abc(Request ID: a)ghp_<36>"))` prints `abcghp_<36>` | `logging_config.py:466-474` (`one_line`, steady before the only mask), `messages/_field_writers.py:70-77` (`_REQUEST_ID`, `_steady`) | reproduced | token printed in a `failure=` field | stderr only: masked |
| M2 | `one_line` collapses white space before masking: `https://user:S3cr\n3tPw99x@h/x` prints whole (`S3cr 3tPw99x`), through `one_line`, `failure_reason`, `failure_text`, every `failure=` field (31 callers) | `logging_config.py:466` | reproduced | password printed | stderr only |
| M3 | The same class at the other collapse or split sites: `_lock_say._cut_failure` (collapse, then mask), `_git_run._failure` (keeps only `fatal:` lines, or collapses `err`, then masks), the setuptools stderr relay (splits, then masks each line: `WARNING: setuptools stderr: error: fetch https://u:S3cr`), the build-log tail and pipdeptree's last line (split, keep one line) | `messages/_lock_say.py:119`, `extract/remote/_git_run.py:329-333`, `core/_models_wheel_setuptools_relay.py:73`, `core/_models_wheel_build_subprocess.py:318`, `extract/env.py:31` | reproduced (lock, git, setuptools relay, build tail: synthetic input); env read-only | start or end of a password printed | stderr only |
| M4 | A header credential after a line break: `log.warning("%s", "Authorization: Bearer\nhunter2Xabc")` prints the credential (raw `\n` and escaped `\\n` both); the header pass allows no line break, and the scheme-word pass keeps `hunter2Xabc` (not random enough) | `core/url_masking/_auth_schemes.py:86` (`_SEPARATORS`) | reproduced | credential printed | stderr only |
| M5 | A token after an ANSI colour sequence: `token: \x1b[33mghp_...` (raw, and escaped `\\x1b[33m`) prints the token: the `m` glues to the prefix | `core/url_masking/_boundary.py:40-53` (`word_start`; users `TOKEN_RE`, `SCP_USERINFO_RE`, `_PURL_WORD`, `_SCHEME_RE`, `_HEADER_RE`, `_SECRET_PARAM`) | reproduced | token printed (coloured build, pip, git output) | stderr only |
| M6 | `loggable()` escapes before the formatter masks (41 call sites in 20 files, plus the writers `free_text`, `file_text`, `entity_text`): a token split by a zero-width space prints (`'ghp_A1b2C3\u200bd4...'` through `free_text` and `loggable`), and an scp password with a non-ASCII letter prints once `ascii()` writes it `\xe4` (`alice:p\xe4ssw0rd9@host:o/r`) | `logging_config.py:239-257` | reproduced | token or password printed | stderr, and exception text a library caller reads (`pypi_url._refuse`) |
| M7 | An scp-style password holding a raw `@`: `alice:hunter2X@x@host:o/r` printed whole (`[^\s@/\\:]+@` stops at the first `@`, the host lookahead then fails) | `core/url_masking/_userinfo.py:226-230` (`SCP_USERINFO_RE`, shared with the detector) | reproduced | password printed | stderr; **SBOM refusal widens** (R5) |
| M8 | `Cookie:`/`Set-Cookie:` values and secret-named headers (`X-Api-Key:`, `Private-Token:`, `X-Auth-Token:`, also in JSON `"X-Api-Key": "..."`) printed | new pass in `core/url_masking/` | reproduced | credential printed | stderr only |
| M9 | A quoted credential after a scheme: `Bearer "s3cr3tvalue99"`, `Authorization: Bearer 'hunter2Xabc'` printed | `_auth_schemes.py:107-133` (`_SCHEME_RE`, `_HEADER_RE`: the run cannot start at a quote) | reproduced | credential printed | stderr only |
| M10 | Stale text: `loggable()` says it "masks nothing" and that `kv_line` masks "only a URL's credentials" (it masks the whole value with `masked_given_path` when it holds a URL); `one_line` says one masker pass after `steady` is enough (M1 disproves it); `_boundary`, `masked_given_path` and `docs/url-credentials.md` list no ANSI, header or quote rule; the #526 doc's "Left open", the roadmap bullet and `message-catalogue-pr14-build.md:231` ("TOKEN_RE root cause, still open") | as named | read-only | none | none |
| M11 | Cost: every new pass and boundary stays linear; shapes join `_ADVERSARIAL` | `tests/core/url_masking/test_url_masking_given_path.py:375` | measured (prototype) | none | none |

The `_auth_schemes.py` "Linear" paragraph named in the sweep-B nits was
corrected by #543 (it now says `%20` ends a run): not in scope.

## 2. Out of scope

| Item | Why | Goes to |
| --- | --- | --- |
| `GET /x?token=S3cr\n3tPw99x` prints `?token=*** 3tPw99x` | A secret value ends at white space by rule; the accepted partial leak `masked_given_path` documents (no start of a secret shown). Unchanged by any order | stays documented |
| Summary regex (two `.+` without DOTALL, about 0.4 s at the 65,536 cap; `messages/_line_kind.py:85`) | Test-harness classifier, not masking; read-only here | sweep C (C1 or C2, whichever owns `_line_kind.py`) |
| After a scheme word alone, `passw0rd`, `mySecretPassword`; a `Digest`/`AWS4` header over several lines | Prose rule ruled in #526; unchanged | `docs/url-credentials.md` keeps listing them |
| JSON `\u001b`, `\b`, `\f` and OSC (non-CSI) sequences as boundaries | `ascii()` never writes them; no Pitloom path produces them | stays documented |
| `_SCHEME_RUN_RE`/`URL_AS_PATH_RE` read `\thttps://` as scheme `thttps` | userinfo masked all the same (#526) | stays documented |
| Converting the 41 `loggable(x)` sites one by one | M6 fixes them centrally (R2) | not needed |
| `Request ID` in `log.debug(exc.request_id)` | off stderr | sweep C carried list |

## 3. Rulings needed

**R1. First mask of a multi-line text before it is collapsed** (M1, M2, M3,
M6). Options: (a) `masked_text` (reads a multi-line text as one text, then
as a line), as the log sink, `excerpt()` and `print_traceback()` do today;
(b) the line reading alone (`masked_given_path(line=True)`), which already
takes a tab or a line break inside a user information. Measured: (b) misses
`https://u:S3\u2028cr@h` (U+2028 is a line break to `splitlines` and white
space to `split`) and a wrapped line `https://u:pa\n ss@h/x`; (a) over-masks
2 of 366 corpus texts, hiding text, never showing a secret:
`Failed https://example.org\nContact admin@example.org for help` prints
`Failed https://***:***@example.org for help`, and
`line1\nline2 https://h/x?token=\nline3` loses `line3`. **Recommend (a)**:
one reading on every surface, the one already shipped for `excerpt()`
and the sink; the over-mask is the sink's today for a multi-line record.

**R2. Where `loggable()` masks** (M6). Options: (a) `loggable()` masks
(`masked_text`) on its escape path only, and a new non-masking
`escaped_literal()` serves stdout data (`kv_line`) and the writers that have
masked already; (b) convert each of the 41 sites and 3 writers to a
mask-first writer. Measured (a): the escape path is the only path where the
order matters (a printable text reaches the sink unchanged); 0 call-site
edits; the full suite passes; cost one masker pass per escaped text (the
printable fast path is untouched). **Recommend (a)**: one shared
mechanism, and a new call site cannot reintroduce the order.

**R3. Which header names hide their value** (M8). Options: (a) a name with a
`-` that `is_secret_name(name, weak=False)` accepts (the detector's refusal
strength), plus `Cookie`/`Set-Cookie`; (b) a closed list (`X-Api-Key`,
`Api-Key`, `Private-Token`, ...); (c) any secret name, weak ones too.
Measured: (c) masks `Cache-Key`, `Sort-Key`, `Primary-Key`, `Public-Key`;
(a) keeps those and masks `X-Api-Key`, `Api-Key`, `Private-Token`,
`X-Auth-Token`, `X-Goog-Api-Key`, `X-Amz-Security-Token`, `X-Vault-Token`,
`Ocp-Apim-Subscription-Key`, `Job-Token`, `Session-Id`, `Access-Token`, and
`Key-Value` (no such header; accepted). Prose after a header name is masked as
after `Authorization:` (`the X-Api-Key: header must be set` prints `X-Api-Key:
*** must be set`; `Api-Key: see docs` prints `*** docs`); a placeholder
starting `<`, `$`, `{` or `*` is kept. **Recommend (a)**: the secret-name
rule is the shared one (`_params`), and no list to drift.

**R4. Which cookie values** (M8). Options: (a) each `name=value` value on
the line, Set-Cookie attribute names (`Path`, `Domain`, `Expires`,
`Max-Age`, `SameSite`, `Secure`, `HttpOnly`, `Priority`, `Partitioned`)
kept; (b) the whole value after `Cookie:` as one `***`; (c) only cookies
with a secret name. **Recommend (a)**: a session cookie's name is
arbitrary (`sid`, `_gh_sess`), and the structure stays readable
(`Cookie: session=***; other=***`).

**R5. A raw `@` in an scp password, for the detector too** (M7).
`SCP_USERINFO_RE` is shared by the masker and the detector (`_hits`), so
the fix makes `foo:bar@baz@qux:path` a refused SBOM value (`scp` hit), the
only detector change in the 366-text sweep (2 rows: the text and its
tab variant). Options: (a) shared (git and OpenSSH split `user@host` at the
last `@`); (b) masker only, a second pattern. **Recommend (a)**: the
module's contract is that the two never disagree. CHANGELOG names it.

**R6. ANSI boundary breadth** (M5). Options: (a) precise CSI lookbehinds
(`ESC [`, parameters `[0-9;?]` up to 16, a final letter; raw, escaped once
and twice), gated by `(?<=[0-9;?\[][A-Za-z])`; (b) the loose
`(?<=[0-9;\[]m)` (also `10mghp_...`); (c) strip sequences before masking
(the masker must print text as given: rejected). **Recommend (a)**: no
false boundary in prose; the gate keeps cost at base (see M11). A CSI with
over 16 parameter characters is missed (accepted, documented).

**R7. A line break as a header separator** (M4). Options: (a) a raw or
escaped line break counts unless a header name follows it
(`(?![tchar]+[ \t]*:)`, so `Authorization: Bearer\nX-Other: 1` keeps
`X-Other`); (b) only an obsolete fold (a line break then a space or tab).
**Recommend (a)**: (b) misses the reproduced case. The doc's "a header's
separators stay without a line break" rule (#526 third review F1) is
reversed, with its reason kept: the next header name is never masked
(pinned by a test).

**R8. One PR or two.** Estimated ~22 files, ~700 changed lines (section 8).
**Recommend one PR**; split as (A) order M1-M4, M6 and (B) shapes M5,
M7-M9 only if it passes 800 lines.

### Rulings (maintainer, 2026-11-26)

- R1: (a) `masked_text` first, the sink's reading.
- R2: (a) `loggable()` masks on its escape path; `escaped_literal()` does not
  mask (chosen as the cleaner: one shared mechanism, no call-site edits).
- R3: **(b) a closed list**, not the recommended secret-name rule. Names,
  any case: `X-Api-Key`, `Api-Key`, `Private-Token`, `Job-Token`,
  `X-Auth-Token`, `X-Access-Token`, `Access-Token`, `X-Goog-Api-Key`,
  `X-Amz-Security-Token`, `X-Vault-Token`, `Ocp-Apim-Subscription-Key`,
  `X-JFrog-Art-Api`, `X-Registry-Auth`; plus `Cookie`/`Set-Cookie` (R4).
  One constant in `_headers.py`; `Key-Value` and `Session-Id` are kept.
- R4: (a) each `name=value` value; Set-Cookie attributes kept.
- R5: (a) shared with the detector; CHANGELOG names the widened refusal.
- R6: (a) precise CSI lookbehinds, gated.
- R7: (a) a line break is a header separator unless a header name follows.
- R8: one PR.
- Split of `logging_config.py` (503 lines): this PR does it, as a pure-move
  first commit (C1 ruling Q8 (a)); C1 does not touch the file.

## 4. Design per item

New and changed shared helpers (no message catalogue code changes: no new
or changed message, only what a value prints; no `since`):

- `pitloom.log_masking.masked_lines(text) -> list[str]`: `masked_text(text)`
  then `splitlines()`. Used by `print_traceback` (replaces its inline form),
  the setuptools relay, the build-log tail, `env._last_line`, and
  `_git_run._failure` before it picks its `fatal:` lines (M3).
- `pitloom.logging_config.collapsed(text, steady=None) -> str`: mask
  (`masked_text`), collapse white space, then `steady` and collapse again
  when given, then mask again. Used by `one_line` (M1, M2), `excerpt`
  (replaces its inline form), `_lock_say._cut_failure` and `_git_run._failure`
  (M3). Docstring states why two passes: a drop or a collapse can both
  split and join a credential.
- `pitloom.logging_config.escaped_literal(text)`: today's `loggable()`
  body. `loggable(text)` becomes: printable, as is; else
  `escaped_literal(masked_text(text))` (M6, R2). `kv_line` calls
  `escaped_literal` (stdout data must not take the scp line rule: `meet
  10:30@ab:c.json`); `one_line`, `excerpt`, `cut_and_escaped`,
  `escaped_name`, `url_text` call it too (they have masked already: no
  second pass).

Per item:

- **M1, M2**: `one_line` = `escaped_literal(collapsed(str(value),
  steady)[:limit])` plus its class-name and ellipsis rules; `failure_reason`
  unchanged (goes through `one_line`).
- **M3**: the five sites through the two helpers; `_git_run._failure` masks
  `err` whole, then selects lines, then `collapsed()`.
- **M4**: `_SEPARATORS` in `_auth_schemes.py` gains `(?:\r?\n|\\{1,2}r\\{1,2}n|
  \\{1,2}n)(?![tchar]+[ \t]*:)`; the docstring's separator paragraph
  changes.
- **M5**: `_boundary.AFTER_ANSI` (built from one constant
  `_CSI_PARAMS = 16`) joins `word_start()`; written with regex escapes
  (`\\x1b`), not a raw ESC in source (AGENTS: no invisible characters).
- **M6**: as R2.
- **M7**: `SCP_USERINFO_RE` password `[^\s@/\\:]+(?:@[^\s@/\\:]+)*@`; the
  host lookahead picks the last `@`.
- **M8**: new `core/url_masking/_headers.py` (standard library only, the
  package contract): `mask_secret_headers(text)`, a header name at
  `word_start` (`[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+` or `cookie`/`set-cookie`),
  optional quote (also `\"`), `:`, gap, optional quote; the value run
  `[^\s"'\\,;<>${}*][^\s"'\\,;]*` for a secret name (R3), the cookie pairs
  for a cookie (R4); each header's scan stops at the next header or the
  line end (the `Digest` bound pattern), spans written once. Called from
  `_mask._masked()` after `mask_auth_schemes`. Fast exit when no `:`.
- **M9**: an optional quote (`\\{0,2}["']`) between the separators and
  `_RUN` in `_SCHEME_RE` and `_HEADER_RE`; the closing quote is kept.
- **M10**: docstrings in `logging_config.py` (`loggable`, `one_line`,
  `excerpt`), `log_masking.py`, `_boundary.py`, `_auth_schemes.py`,
  `_userinfo.py`, `_mask.masked_given_path`, `kv_output.kv_line`;
  `docs/url-credentials.md` (masking list: headers, cookies, quotes, ANSI,
  scp `@`; over-masked: header prose, `Key-Value`; missed: CSI over 16
  parameter characters); #526 doc's "Left open" (each item: fixed here, with
  this PR's number), roadmap bullet removed, `pr14-build.md:231` corrected,
  one CHANGELOG bullet (Fixed). Skills quote no masking rule
  (`grep -ril "bearer\|escape sequence" skills/` is empty): no skill change.

## 5. to 9. Tests, build steps, gates, risks, overlap; appendix

Moved to [log-masking-before-collapse-build-plan.md](log-masking-before-collapse-build-plan.md):
tests per item, build steps and agents, gates, risks and size (section 8),
overlap with C1 and C2, and the prototype measurements.

## 10. As built (2026-11-26)

Built as planned, with the rulings above (R3 a closed list). Changes from
the plan:

- `logging_config.py` split first, as a pure move: `loggable`, `excerpt`,
  `one_line`, `failure_reason` and their constants went to
  `pitloom._log_text`, re-exported from `pitloom.logging_config` (no caller
  changed). `collapsed()` and `escaped_literal()` live there too.
- `collapsed()` turns every white space character that `str.split()`
  collapses but the masker's line reading does not read inside a user
  information (U+00A0, U+3000, U+2000 to U+200A, ...; built from `\s`
  minus the space, the tab and the `splitlines` breaks) into a tab before
  the first mask. A tab is read inside a user information, so a password
  split by a no-break space is masked. Over-mask: words joined only by such
  characters can read as one address, as with a tab.
- The ratio helpers of the linear-time tests are one module,
  `tests/_linear_time.py`, used by the masker shapes and by a new
  `one_line` (with `steady`) cost test.

Fresh review (Fable, after Gate A; 20,232-case differential over 16
surfaces, 69 cost shapes, 23 mutants). Two regressions against base, both
fixed: a scheme-less `Authorization:` credential before a line break was
shown (the line break made the key the "scheme"; the first word is now
judged alone when the run after a line break is no credential), and a git
failure text showed a password split by a no-break space (above). Gaps
fixed: a quote escaped three times (`\\{0,3}`), any `splitlines` break raw
or escaped as a header separator (lone `\r`, U+2028, U+0085, `\x0b`), an
scp password starting or ending with `@` (`[^\s/\\:]+@`, greedy to the
last `@`, linear as no password spans a `:`), a terminal sequence between
the scheme and the credential, ECMA-48 parameter characters `[0-?]` (a
`:` in `\x1b[38:5:196m`), `("X-Api-Key", "v")` pairs, a quoted cookie value
holding a space, an indented next header name kept. One mutant survivor
(the second mask in `_git_run._failure`) is now killed.

Not taken: the review's finding that an empty secret value at a line end
takes the next line (`?token=` then `fatal: repository not found` prints
`?token=***`, and `env._last_line` loses `ValueError: boom`). A fix was
built and reverted: it showed a secret wrapped right after its `=`
(`?token=\n<secret>`), which base masks, against this PR's rule that no
text masked on base is shown after. Documented as over-masked; pinned by
`test_a_secret_wrapped_after_its_parameter_name_stays_masked`.

Verification:

- Before/after sweep (366 texts x 10 views, base 63dde20e against the
  tree): 87 of 3,670 rows change, every one masking more; no word shown
  that base hid, no row with fewer `***`. Reviewer's differential against
  base: 0 regressions on 15 surfaces, no new exception.
- Linear time: 45 new masker shapes (ratio 2.3 to 9.0 on a loaded
  machine, bound 15) and 6 `one_line` shapes (3.9 to 7.6 at 100k against
  500k; the 13.9 seen at 30k was noise).
- Gate A (before the review round): full suite 29,417 passed; branch
  coverage of the 15 changed modules 100%; every CI linter clean; message
  inventory and reference unchanged; manual CLI checks (setuptools, build,
  wheel, remote targets, offline): 90 pass, 0 fail, 8 need `--network`.
- Windows dry-run: an ESC in the CLI test's path is `ERROR_INVALID_NAME`
  (winerror 123), which `is_missing_errno` and `Path.exists()` read as
  missing, so the test gives `input-not-found` there too; `\r\n` is covered
  in the relay, `masked_lines` and header-separator tests.

Gate B mutation (hand, on scratch copies, after the review round): 146
mutants, 100 killed at first. The 46 survivors were test gaps, now killed
by pinned inputs (the 13 header names as a literal list, the `Expires` and
`Priority` attribute values, each placeholder first character, `token` as
a scheme word in a secret header, the escaped tab and line end in the
header pass, a cookie value escaped twice, an empty cookie value, a
terminal sequence after a scheme word alone, the `\x1c` to `\x1e` and
U+2029 breaks raw and escaped, upper-case hexadecimal escapes, a triple-
escaped and a pair `Authorization`, the steady collapse, `one_line`
writing a cut masked text unmasked again), or equivalent: CR and LF
alternatives inside a `+` run, the git fallback escaper over masked text,
`Secure`/`HttpOnly`/`Partitioned` (no value). From it:

- The header and cookie placeholder first characters are one constant
  (`<`, `$`, `{`, `*`); before, a header value starting `>` or `}` was kept
  and a cookie value not.
- The pass order stays `Authorization` first. Run first, the header pass
  masks `Authorization: Bearer X-Api-Key: v` too, but ends a value at a
  terminal sequence's `;` and so hides the scheme word from the
  `Authorization` pass: `X-Api-Key: Bearer\x1b[0;1m<key>` printed the key
  (found by the review differential, 9 inputs per surface).
- Removing the cost gate of the terminal-sequence lookbehind makes masking
  about 4x slower on every text alike, so the ratio test cannot see it; it
  is a speed-only mutant, left to review.
