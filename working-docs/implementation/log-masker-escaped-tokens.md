---
Created: 2026-11-23
Last-Modified: 2026-11-24
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Log masker: a credential after an escape, mask-then-escape, `Bearer`

See also: [message-catalogue-review-rounds.md](message-catalogue-review-rounds.md)
(rounds 4 and 5, where the defects were found),
[roadmap.md](../design/roadmap.md) and `docs/url-credentials.md` (what a user
reads).

PR #526. Three pre-existing defects of the log masker
(`pitloom.core.url_masking`), found in catalogue PR 13 and 14a reviews.

## The defects, reproduced on the base tree (0761d040)

- **D1, a token after an escape.** `TOKEN_RE`'s lookbehind
  `(?<![A-Za-z0-9_-])` sees the `t` of an escaped tab (`\t`), the `b` of
  `\x1b`, the `e` of `\u202e`. A text escaped by `loggable` before the
  formatter masks it printed the token. Probe: every `TOKENS` shape of the
  probe corpus, after each of 7 control characters, escaped once and twice:
  476 of 952 texts leaked, every "token last" text; "token first" was masked
  (the token's end check sees the backslash). The same lookbehind shape hid an
  scp-style password (`x:\talice:pw99@host:o/r` printed raw); a PURL after an
  escape was masked, but at another decode depth than the raw text.
- **D2, escape before mask.** `shown_url` (`loggable(sanitize_url(url))`) and
  the `files` of `project-not-found/model-files` (`loggable(name)`) escaped
  first. Besides D1, that order also hides a token split by a format character
  (a zero-width space): the masker drops a format character from a raw text
  when that shows a credential, but an escaped `\u200b` is six ASCII
  characters, so the token is two runs of letters. The same
  `loggable(sanitize_url(...))` shape was in `pypi_url._refuse`,
  `_model_generator._refuse_pypi_url`, `git._prepare` and
  `_git_credentials._split`.
- **D3, `Bearer`.** `Authorization: Bearer <jwt>`, `Bearer <opaque>` and
  `Basic <base64>` were printed as written (no rule read them).

## The rules decided

**Boundary** (`core/url_masking/_boundary.py`, `word_start()`): a credential
found by its shape starts where it is not glued to the character before it,
or right after a `%XX`, or right after an escape sequence `ascii()` writes:
`\t`, `\n`, `\r`, `\xHH`, `\uHHHH`, `\UHHHHHHHH` (`H` a hexadecimal digit of
either case). One fixed-width lookbehind per length (Python's `re` needs
that). The doubled form (`\\t`, a text escaped twice) ends the same way, so
it counts. Not a boundary: a letter after a backslash that is no escape
(`\q`), an incomplete escape (`\x1`, `\u202`), plain letters (`abt`), `x1b`
without the backslash. A drift test escapes every C0 and C1 control, U+2028,
U+2029, a lone surrogate, U+E0001 and every display control through
`loggable` and checks the escape ends in a match. The same `word_start()`
now opens `TOKEN_RE`, `SCP_USERINFO_RE`, the PURL word and the `Bearer`
scheme. Accepted false positive: a backslash typed before such a letter (a
Windows folder `C:\tghp_...`) reads as an escape.

**Order** (D2): mask, then cut, then escape, through two new writers in
`messages/_field_writers.py`, exported by `pitloom.messages`:
`escaped_name(text)` (`loggable(cut_name(text))`) and `url_text(url)`
(`loggable(masked(sanitize_url(url)))`, not cut). `shown_url` delegates to
`url_text`; the six call sites above and `_git_folder.folders_text` use them.
`git._prepare` dropped its `sanitize_url_credentials` pass: `masked` masks an
scp-style address too.

**`Bearer`/`Basic`/`Authorization`** (`core/url_masking/_auth_schemes.py`,
final rule after the security review below), two passes:

- After a header name (`Authorization`, `Proxy-Authorization`, any case, not
  glued to a letter, digit, `_` or `-`; an optional quote, also `\"`; white
  space or an escaped tab; `:` or `=`; the same again): the scheme `Bearer`,
  `Basic`, `token` or `Digest`, then the run of RFC 6750 `b64token`
  characters (`[A-Za-z0-9._~+/=-]`) is masked whatever its length or shape.
  A placeholder (`<token>`, `${TOKEN}`, `$GITHUB_TOKEN`) starts with no such
  character and is kept; `Authorization: Bearer token required` prints
  `Bearer *** required` (accepted). For `Digest`, only the `response=` value,
  up to the next header name or the line end.
- After `Bearer` or `Basic` alone: a run of 8 characters or more that ends in
  `=`, is digits only, holds `~` or `+`, or holds a word (letters and digits
  between the other characters) that is 20 characters or more, has a
  single lower-case letter among other runs (`dXNlcjpwYXNz`, `s3cr3t`), has
  2 digits or more before its end (`abcd12efgh`, `1234abcd`), or ends in
  digits at least as many as its letters (`abcd1234`). `Basic` must be
  base64. `/` and `.` count for nothing on their own: the words decide.
- Separators for both: spaces, tabs, no-break spaces, `%20`, the escaped tab
  and no-break space once or doubled (`\t`, `\\t`, `\xa0`, `\\xa0`). A `.`
  ending a run is kept; a run is masked whole (`Bearer s3cr3tvalue99.gguf`
  prints `Bearer ***`, the extension lost, by decision).
- Each run is read in a lookahead and replaced from a span list, so a prose
  run does not hide a later scheme; runs never overlap.

## Probe corpus (`Bearer`/`Basic`)

The first version (a digit, one of `.~+/=`, mixed case, or 20 characters)
kept 26 prose texts (`the bearer of bad news`, `Bearer token required`,
`Use Bearer authentication.`, `Basic Authentication`, `a basic well-formed
document`, `WWW-Authenticate` challenges, `Bearer $GITHUB_TOKEN`, `Bearer
access_token`, ...), all still kept. While choosing it, `_` as a mark
(`Bearer access_token`), no base64 check (`basic 20240101-x`) and no
trailing-`.` strip (`Use Bearer authentication.`) were false positives, fixed.

The security review then found these masked, now kept (all in the test
corpus): `basic types/values`, `Basic usage/configuration`, `use bearer
tokens/keys`, `requires basic understanding/skill`, `Basic tutorial2024`,
`see Bearer RFC-6750-style`, `Basic Latin1Supplement`, `bearer
requests.auth.HTTPBearer`, `https://h/guide/bearer%20tokens/setup`, and the
file name `Bearer Token.txt` through `escaped_name` (it printed `Bearer ***`,
the extension lost). Also kept now: `Bearer 1.2.3-beta`, `Bearer a.b.c.d.e.f`,
`Bearer tokens/authorization-headers`, `Bearer error=invalid_token`, `Basic
DevOps2024`, `X-Authorization: Bearer abcdefghij`. The reviewer's suggested
rule (a digit counts with a capital or 2 digits before the end) would still
mask `RFC-6750-style`, so the word-based rule was chosen instead.

Three earlier positive cases relied on `/` or `.` alone and were given inputs
that prove the rule: `Bearer abcd/efgh` became `Bearer dXNl/cjpwYXNz` (a
random word beside a `/`), `Bearer a.b.c.d.e.f.` became `Bearer eyJh.eyJz.`
(the `.` kept) and `Bearer a.b.c.d.e.f` is now prose; `Bearer abc.def.Bearer
12345678x` became `Bearer eyJh.eyJz.Bearer 12345678x`.

Now masked (review F2, F3): `ascii(loggable("Authorization: Bearer\ts3cr3tvalue99"))`
and the same for `Basic` and a no-break space (doubled escapes printed raw);
`Authorization: Bearer abcdefghij`, `... ABCDEFGHIJKLMNOPQRS`, `...
Abcdefghijklmnop`, `... abcdefgh-ijklmno`, `Authorization: token
abcdefgh12345678`, a quoted or escaped-JSON header, `Proxy-Authorization=Basic
abcdefgh`, a `Digest` `response="..."`.

Missed (in `docs/url-credentials.md`): after a scheme word alone, a credential
under 8 characters, of letters only without a single lower-case letter among
other runs, of one case or of words (`passw0rd`, `mySecretPassword`), or with
fewer digits at its end than letters; a `Digest` or `AWS4-HMAC-SHA256` header
over several lines; `Bearer 'x'`; `Cookie:` and `X-Api-Key:` values.

## Before and after

| Probe | Base 0761d040 | After |
| --- | --- | --- |
| `TOKENS` x 7 controls x 2 directions x 2 escapes | 476 / 952 leak | 0 |
| `x:\talice:pw99@host:o/r` escaped | printed raw | `x:\t***:***@host:o/r` |
| escaped `\tpkg:...?download_url=<encoded URL>` | `download_url=https://***:***@h` | `download_url=***` (as raw) |
| `Authorization: Bearer <jwt>` | printed | `Authorization: Bearer ***` |
| `Basic dXNlcjpwYXNzd29yZA==` | printed | `Basic ***` |
| `shown_url` of a URL with `\x1b` + token | token printed | `ghp_***` |
| model-files name `m<ESC>ghp_...gguf` | token printed | `m\x1bghp_***.gguf` |

Timing of `masked_text` on 1 MiB adversarial texts (macOS, Python 3.10, one
run each, seconds):

| Text | Base | After |
| --- | --- | --- |
| `\t` repeated | 0.39 | 0.16 |
| `\x1b` repeated | 0.22 | 0.46 |
| `\u202eghp_` + 20 letters, repeated | 0.07 | 0.20 |
| `\tglpat-` + 18 near-token characters, repeated | 0.08 | 0.23 |
| `Bearer` + 1 MiB of spaces + `!` | 0.66 | 0.24 |
| `Bearer \t\t\tab.` repeated | 0.27 | 0.28 |
| `basic ` repeated | 0.17 | 0.22 |
| `\U000e0001` repeated | 0.12 | 0.15 |

The first version (no first-character filter) took 1.0 s on the `\t` run:
`TOKEN_RE` tried 6 lookbehinds and 40 prefixes after every backslash. A
lookahead on the prefixes' first characters (`(?=[Aaghnpsx])`, `(?=[Bb])`
for the scheme) brought it under the base. Four shapes joined the
linear-time ratio test (`test_a_given_path_is_masked_in_linear_time`).

Timing after the review (seconds, best of two, 1 MiB; base 0761d040, the
first PR version, the reviewed version; the machine was loaded, so compare
within a row):

| Text | Base | First | Reviewed |
| --- | --- | --- | --- |
| `\t` repeated | 0.61 | 0.19 | 0.30 |
| `\x1b` repeated | 0.31 | 0.40 | 0.63 |
| `\tglpat-` + 18 near-token characters, repeated | 0.11 | 0.25 | 0.42 |
| `Bearer` + 1 MiB of spaces | 0.96 | 0.23 | 0.32 |
| `bearer abc\t` repeated | 0.23 | 0.29 | 0.46 |
| `Bearer ` + 1 MiB of `a` | 0.07 | 0.26 | 0.37 |
| `Bearer ` + 1 MiB of random mixed case | 0.10 | 0.19 | 0.18 |
| `Bearer ` + 1 MiB of digits | 0.10 | 0.19 | 0.14 |
| `Bearer ` + `ab/` repeated | 0.35 | 0.60 | 0.72 |
| `Bearer ` + `AbcDef.` repeated | 0.18 | 0.36 | 0.59 |
| `Authorization: Bearer ` + 1 MiB of `a` | 0.07 | 0.29 | 0.56 |
| `Authorization: Bearer x ` repeated | 0.24 | 0.35 | 0.53 |
| `authorization` + 1 MiB of spaces | 0.94 | 0.33 | 0.20 |
| `Authorization: Digest a=1, ` repeated | 0.30 | 0.38 | 0.28 |

`_looks_random` returns at once on a word of 20 characters or more, so a long
run costs one pass. Four more shapes joined the ratio test (a long
`Bearer` run, repeated headers, header-name gaps, repeated `Digest`
headers): all under the bound.

## Verification

- Fail on base: every new regression case fails on `git archive HEAD` (48 in
  the masking files, 21 in the writer and caller files); the boundary guards
  (`%XX`, a space, the negatives) and the linear shapes pass there, as
  expected.
- Mutation (hand, on a scratch copy, 66 mutants): each lookbehind
  alternative removed or narrowed (`\[tnr]` letter by letter, hex count, hex
  case, the backslash), `word_start` without the escape (all four users), the
  `%XX` alternative, each separator, each `Bearer` constant and mark, each
  case test, the base64 check, the `.` strip, the run class, the
  mask/cut/escape order in both writers, and each of the 7 caller sites put
  back to escape first: 65 killed. One equivalent: dropping the
  first-character lookahead (speed only). The caller mutants are killed only
  by the zero-width-space case: with the boundary fix, an escaped `\x1b` +
  token is masked whichever the order.

## Left open

- Review fixes (F1 to F4): the rule above; `logging_config.excerpt()` masks
  before it collapses white space (`excerpt("https://u:pa\nss99@h/x")`
  printed `'https://u:pa ss99@h/x'`); `huggingface.py` names the model URL
  through `url_text` (a model name from a URL may hold anything but `/?#`).
  Every new case fails on the first PR version (33 auth and excerpt cases, 5
  separator cases, 1 Hub URL case). Mutation of the new rule: 45 mutants
  first, 5 survived; 4 were killed by new cases (`Basic DevOps2024`, `Bearer
  s3cr3tx`, `Basic s3cr3t-value`, the Hub URL), one is equivalent (the run
  lookahead `*` against `+`: an empty run is skipped either way).
- Second review (performance and tests, M1 to M6): the two passes now
  read the text as given and their spans are merged (overlapping or
  touching spans write one `***`), written once through `io.StringIO`. The
  header pass had masked a scheme word as the credential and hidden the
  credential after it: `Authorization: Basic Bearer abcd1234efgh` printed
  `Basic *** abcd1234efgh`, now `Basic *** ***` (and `Authorization: token
  Bearer s3cr3tvalue99`). Peak memory of `masked_text` on 4 MiB of `Bearer
  abcd1234 ` repeated (tracemalloc): first PR 21.5 MiB, first review fix
  51.7 MiB, now 6.1 MiB; 4 MiB of `Authorization: Bearer x ` 46.8 to 8.7
  MiB. `Bearer x86_64-linux` and `Bearer iPhone15Pro` stay masked (no cheap
  rule tells them from `abcd1234` and `abcd12efgh`): pinned by a test and
  listed as over-masked in `docs/url-credentials.md`. `Basic
  dXNlcjpwYXNz===` (three `=`) is kept, pinned. The `Digest` scan's bound at
  the next header is load-bearing (without it the ratio test hung): a spy
  test now checks the searched lengths add up to the text's length, and the
  `Digest` shape left the ratio test, so losing the bound fails fast.
  Timing after it (1 MiB, seconds, one run): `Bearer` + letters 0.19, +
  random mixed case 0.13, + digits 0.10; `Bearer abcd1234 ` repeated 0.27;
  `Authorization: Bearer ` + letters 0.18; repeated headers 0.21; repeated
  `Authorization: Basic Bearer abcd1234efgh ` 0.23; repeated `Digest`
  headers 0.21. Mutation: the two passes run in sequence (killed by the
  `Basic Bearer` case), each pass dropped, the merge dropped, `={0,3}` and
  `={0,1}` padding, the `Digest` bound at the next header and at the line
  end: killed. Equivalent: `start <= done` against `<`, and dropping the
  early return when nothing is masked. Not equivalent (third review):
  `max(done, end)` against `end`: spans nest, as the `Digest` value class
  holds `%20`, so a scheme span can sit inside a `response=` span
  (`Authorization: Digest response=Bearer%20s3cr3t99x~/:abc, x=1`); with
  `end` the value's tail `:abc` printed. Pinned by `digest-nested-spans`.
- Third review (delta of the second fix, 2026-11-24, fresh Opus agent; 9
  findings, all taken). F1: `excerpt()` masked before collapsing, so a
  scheme word and a credential split by a line break (`Bearer\ns3cr3t...`)
  printed; it now masks again after collapsing, and the scheme-word
  separators are any white space and the escapes `ascii()` writes for it
  (`\n`, `\r`, `\x0b`, `\u2028`), so `loggable()` text is masked too. A
  header's separators stay without a line break (`Authorization: Bearer`
  with no value, then another header, must not hide the next header's
  name). F2: a `Digest` `response=\"x\"` in escaped JSON printed the hash;
  the value class excludes `\` and the value may open with `\"`. F3:
  `Negotiate`, `NTLM`, `ApiKey`, `AWS4-HMAC-SHA256 ... Signature=` and a
  value with no scheme printed; the header pass reads any RFC 7235 token as
  the first word, masks the run after an unknown scheme when it looks
  random (a prose word after `Authorization:` stays), the word itself when
  nothing follows and it looks random, and a `Signature=` value as it does
  `response=`. F4: a `%XX` escape is a run character and a mark of a
  credential (`Bearer%20abcd%2Fefgh%2B12`); a `Basic` value is decoded
  before the base64 test. F5: above. F6, F7: the docs name the over-masked
  words (`t5-small`, `eCommerceSite`) and the missed ones (`passw0rd`,
  `mySecretPassword`). F8: this file's date. F9: the spy test patches
  `_SECRET_PARAM`, which it still names.
- Mutation pass after the third review (166 mutants of `_auth_schemes.py`
  and `excerpt()`: AST operators plus regex edits): 131 killed at first, 35
  survived. 24 were test gaps, now killed by new cases (a `Basic` value with
  `+` or `/`, `response = "x"` spaced, an unquoted `response=` that stops at
  a space, a thrice-escaped quote, `%2zz` after a run, `.` after an unknown
  scheme or a scheme-less value, a scheme word before a header, raw
  no-break space after `token`, the escapes `\x1c`, `\x85`, `\u2028`,
  `\u3000`, the tchar `! $ . ~ +` in a scheme-less value, the second mask
  of `excerpt()`, `unquote` and the no-separator rule, each tested on
  `mask_auth_schemes` alone because another rule masks the same text
  through `masked_text`). 11 are equivalent: `return False` to `None`
  (3), `line_end < 0` to `<= 0` (the search starts after the header, so
  never 0), `start <= done` to `<` (spans never touch: a separator lies
  between), dropping the early return when nothing is masked, `{2}` to `{1}`
  hex digits in the credential mark (the run already needs two), the
  scheme-less test with the scheme name (never `basic` there), and one
  malformed mutant.
- About 50 call sites still escape before the formatter masks:
  `log.warning(..., loggable(x))` across `extract/`, `core/`, `assemble/`
  (`grep -rn "loggable(" src/pitloom`), and the free-field writers
  `free_text`, `file_text`, `entity_text`. The boundary rule covers a token
  or address after an escape there; a credential split by a format character
  (a zero-width space inside a token) still prints through them. Moving them
  to mask-first is a cross-package change, not done here. Also open: an scp
  password with non-ASCII or a raw `@`, `Cookie:` and `X-Api-Key:` values, a
  quoted `Bearer 'x'` (one roadmap bullet).
- `_SCHEME_RUN_RE` and `URL_AS_PATH_RE` (no `word_start`) read
  `\thttps://u:p@h` as scheme `thttps`; its user information is masked all the
  same, so they were left as they are.
- A JSON escape `\b` or `\f` (not written by `ascii()`) is no boundary.
- A token after an ANSI colour sequence (`token: \x1b[33mghp_...`, coloured
  build or pip output) is not masked, raw or escaped: the `m` glues to the
  prefix.
