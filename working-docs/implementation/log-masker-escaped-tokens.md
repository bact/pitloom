---
Created: 2026-11-23
Last-Modified: 2026-11-23
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

**`Bearer`/`Basic`** (`core/url_masking/_auth_schemes.py`): the word, any
case, not glued (`_`, `-`, letter, digit) or after an escape; one or more
spaces, tabs, `\t` or `%20`; a run of RFC 6750 `b64token` characters
(`[A-Za-z0-9._~+/=-]`, `_` included: base64url and JWTs use it, the brief's
class lacked it). A `.` ending the run is a sentence end and kept. The run is
a credential when it has 8 or more characters and a digit, one of `.~+/=`,
mixed case past a capital first one (`dXNlcjpwYXNz`), or 20 or more
characters; `-` and `_` alone do not count. A `Basic` run must be standard
base64 (`[A-Za-z0-9+/]+={0,2}`). The scheme and separators are kept:
`Bearer ***`. The run is read in a lookahead and replaced by hand, so a
short run (prose) does not consume a later scheme (`Bearer bearer 1234abcd`
masks the second). Runs never overlap, so it is linear.

## Probe corpus (`Bearer`/`Basic`)

Kept as written (26 prose texts): `the bearer of bad news`, `Bearer token
required`, `Use Bearer authentication.`, `Use Basic authentication for the
registry`, `a basic well-formed document`, two `WWW-Authenticate` challenges
(`realm=...`), `bearer-token`, `HTTP Basic Auth`, `Authorization: Bearer
<token>`, `Bearer ${TOKEN}`, `Bearer $GITHUB_TOKEN`, `basic_auth = True`,
`Basic Authentication`, `Bearer Token-Based scheme`, `the bearer co-signer`,
`Bearer access_token`, `basic 2024-edition`, `basic 20240101-x`, `Basic usage
examples`, `basicConfiguration`, `Bearer: none`, `Bearer tokens are described
in RFC`, `Basic and Digest schemes`, `subearer abcdef123456`, `x-basic
abc12345678`.

False positives found while choosing the rule, and fixed: with `_` counting
as a mark, `Bearer access_token` was masked (`_` dropped from the marks);
without the base64 check, `basic 20240101-x` and a hyphenated word after
`basic` would be; without the trailing-`.` strip, `Use Bearer
authentication.` was. Left (accepted, fails closed): a camelCase word or a
20-letter word after the scheme (`Basic HTTPAuthentication`), a version
after `Bearer` (`Bearer 1.2.3-beta`).

Missed (in `docs/url-credentials.md`): a credential under 8 characters, or of
8 to 19 letters of one case or title case; `Digest` and GitHub's `token`
scheme (a known token shape after them is masked).

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

- About 50 call sites still escape before the formatter masks:
  `log.warning(..., loggable(x))` across `extract/`, `core/`, `assemble/`
  (`grep -rn "loggable(" src/pitloom`), and the free-field writers
  `free_text`, `file_text`, `entity_text`. The boundary rule covers a token
  or address after an escape there; a credential split by a format character
  (a zero-width space inside a token) still prints through them. Moving them
  to mask-first is a cross-package change, not done here.
- `_SCHEME_RUN_RE` and `URL_AS_PATH_RE` (no `word_start`) read
  `\thttps://u:p@h` as scheme `thttps`; its user information is masked all the
  same, so they were left as they are.
- A JSON escape `\b` or `\f` (not written by `ascii()`) is no boundary.
