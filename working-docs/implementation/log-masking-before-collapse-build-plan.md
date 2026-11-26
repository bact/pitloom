---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Log masking (#544): tests, build steps, gates and risks

See also: [log-masking-before-collapse.md](log-masking-before-collapse.md)
(scope, rulings, design and the as-built record; M-numbers and "section
n" below refer to it), [log-masker-escaped-tokens.md](log-masker-escaped-tokens.md).

The build plan of #544 (sections 5 to 9 and the prototype measurements),
split out for size.

## 5. Tests per item

Each regression case fails on 4c194136 (prototype-checked unless marked).
Names are the plan's; files 1:1 with the module.

| Item | Test (file) | Input | Assertion |
| --- | --- | --- | --- |
| M1 | `test_a_dropped_request_id_does_not_glue_a_token` (`tests/messages/test_messages_field_writers.py`) | `RuntimeError("abc(Request ID: a)" + TOKEN)`, also `Amzn Trace ID`, `Amz CF ID` | `failure_text` holds `ghp_***`, not the body; plus the mirror `https://u:pw(Request ID: a)@h` still masked |
| M2 | `test_one_line_masks_before_it_collapses` (`tests/test_logging_config.py`, param) | userinfo with `\n`, `\r\n`, `\t`, `\u2028`, `\n ` | no secret piece in `one_line`, `failure_reason`, `failure_text` |
| M3 | `test_relays_mask_before_they_split` (`tests/core/models_wheel/test_models_wheel_setuptools_relay.py`), `test_build_log_tail_masked_whole` (`.../test_models_wheel_build_subprocess.py`), `test_git_failure_masks_before_it_picks_lines` (`tests/messages/test_git.py` is 515 lines: new `tests/extract/remote/test_git_run_failure.py`), `test_cut_failure_masks_before_collapse` (the lock-say test file) | password split by `\n` | no piece in any record; `caplog` and stderr |
| M4 | `test_header_credential_after_a_line_break` (`test_url_masking_auth_schemes.py`) | `Authorization: Bearer\nhunter2Xabc`, `\r\n`, escaped `\\n`, through `masked_text` and a log record | masked; and `Authorization: Bearer\nX-Other: 1` keeps `X-Other` (R7 guard) |
| M5 | `test_a_token_after_an_ansi_sequence` (`test_url_masking_boundary.py`) | every `TOKENS` shape after `\x1b[m`, `\x1b[0m`, `\x1b[1;33m`, `\x1b[K`, `\x1b[?25l`, raw and `ascii()` once and twice | masked; negatives `2mghp_...`, `x[33mghp_...` kept; a CSI with 17 parameter characters kept (boundary of `_CSI_PARAMS`) |
| M6 | `test_loggable_masks_before_it_escapes` (`tests/test_logging_config.py`) | zero-width-split token, `alice:p\u00e4ssw0rd9@host:o/r\t` | `loggable`, `free_text`, `file_text`, `entity_text` print no secret; `kv_line(V="meet 10:30@ab:c.json\t")` unchanged (stdout guard, kills the "kv_line masks" mutant) |
| M7 | `test_scp_password_with_an_at` (`test_url_masking_userinfo.py`), detector row in `_probe_corpus.py` | `alice:hunter2X@x@host:o/r`, `a:b@c@d@host:o/r` | masked to the last `@`; detector `scp`; `user@host:o/r` still no hit |
| M8 | new `tests/core/url_masking/test_url_masking_headers.py` | the R3 names, JSON and dict-repr forms, `Cookie: a=1; b=2`, `Set-Cookie: sid=x; Path=/; HttpOnly` | masked as R3/R4; kept: `Cache-Key`, `Sort-Key`, `Public-Key`, `X-Request-Id`, placeholders, `Content-Type` |
| M9 | `test_a_quoted_credential_after_a_scheme` (`test_url_masking_auth_schemes.py`) | `"x"`, `'x'`, `\"x\"` after `Bearer` and `Authorization: Bearer` | `Bearer "***"`; prose `Bearer "token"`, `the "Bearer" scheme` kept |
| M11 | `_ADVERSARIAL` | see below | ratio under `_RATIO_BOUND` (15) |

Adversarial shapes (all linear in the prototype, ratio 4.2 to 5.8 at 100k
vs 500k): `\x1b[33m` repeated, `\\x1b[33m` repeated, `ESC[` + 16
parameters + `m` repeated, `m` * n, `\x1b[1mghp_` + 20 letters repeated,
`X-Api-Key: ` repeated, `X-A-` * n + `:`, `Cookie: ` + `a=b; ` * n,
`Cookie: a=b; ` repeated, `a-b:` repeated, `Authorization: Bearer\n`
repeated, `Authorization: Bearer` + `\n` * n + `x:`, `Bearer '` repeated,
`a:b` + `@b` * n, `a:b@` repeated, `a:` + `b@` * n + `h:`. Move
`_ADVERSARIAL` and the ratio test to a new
`test_url_masking_linear_time.py` (the given-path file is 492 lines).

A before/after sweep test (AGENTS, reversed reading): the corpus rows whose
output changes (12 to 16 rows per view in the final prototype: the header, scp `@`,
 multi-line and loggable rows of section 3) are pinned in their
item's test as the new expectation; no row loses masking (checked: zero
rows masked on base and not after).

Cross-surface: the masking is in the shared formatter, record factory and
writers; add one CLI test (`loom wheel` on a missing path
`x\x1b[33mghp_...whl`: the `input-not-found` line prints `ghp_***`; the
path is never created, so it runs on Windows too) and one library test
(the same path through `generate_wheel_sbom`: the coded exception text).
The hook and the Action read the same formatter (existing
`tests/logging/test_credential_sinks_*.py` cover the factory on each); no
hook-only path is touched. Platform: the relay and build-tail tests are
`platform` (process output, line ends); the masker tests are pure text.

## 6. Build steps and agents

1. **Helpers and order** (M1-M3, M6): `logging_config.py`, `log_masking.py`,
   `cli/kv_output.py`, `messages/_field_writers.py`, `messages/_lock_say.py`,
   `extract/remote/_git_run.py`, `core/_models_wheel_setuptools_relay.py`,
   `core/_models_wheel_build_subprocess.py`, `extract/env.py`, their tests.
   Opus: attacker text and the order are the security core.
2. **Masker shapes** (M4, M5, M7, M9): `core/url_masking/_boundary.py`,
   `_auth_schemes.py`, `_userinfo.py`, their tests, `_probe_corpus.py` rows.
   Opus: regex on attacker text, cost.
3. **Headers** (M8): new `core/url_masking/_headers.py`, `_mask.py`, new test
   file. Opus (same reason). Steps 2 and 3 share only `_mask.py`'s
   `_masked()` line: step 3 owns `_mask.py`.
4. **Linear-time file and shapes** (M11): the test move and the 16 shapes.
   Sonnet: mechanical to a clear spec.
5. **Docs and stale text** (M10), CHANGELOG. Sonnet for the docs pass;
   haiku for the stale-wording grep (`masks nothing`, `one masker pass`,
   `TOKEN_RE root cause`, `still open`).
6. **Before/after sweep** of the final tree against 4c194136 (the corpus
   script in the appendix's form) and a fresh review. Opus.

Fences: steps 1, 2 and 3 are file-disjoint; tests follow their module.
Step 4 waits for 2 and 3.

## 7. Gates

- **Tier 1** between rounds: the touched test files
  (`tests/core/url_masking`, `tests/test_logging_config.py`,
  `tests/logging`, `tests/messages/test_messages_field_writers.py`, the
  relay and git tests), ruff, mypy, pylint on the touched packages, the
  corpus sweep diff.
- **Gate A**: full suite `-n 4` (the final prototype: 28,958 passed, 0 failed,
  at 4c194136 plus the prototype, before the new tests); every CI linter
  incl. pyrefly and bandit; branch coverage of the changed modules (100%);
  `scripts/generate_message_reference.py` output unchanged (no catalogue
  change expected; not yet run); each new regression test failing on 4c194136.
- **Gate B**: mutation targets: each `AFTER_ANSI` form (raw, once, twice),
  `_CSI_PARAMS` and the gate class; the line-break separator and its
  header-name lookahead; the quote in each pass; `(?:@...)*` in
  `SCP_USERINFO_RE`; `weak=False`, the dash in the header name, each cookie
  attribute, the placeholder first characters, the next-header bound;
  `loggable`'s mask, `kv_line`'s raw escaper; each pass of `collapsed()`;
  `masked_lines` at each of its five callers. Manual CLI checks:
  `--only` the `core`, `extract` and messages areas touched (setuptools
  wheel, git URL, pypi URL, hub). Windows dry-run: ESC is not valid in a
  Windows file name (the CLI test never creates the path); `\r\n` in the
  relays and in the header separator; `kv_line` on `C:\Users\...` with a
  tab stays unmasked (raw escaper). Fresh-context review of the whole diff
  (opus). Label `test-all-os` (process output and line ends).

## 8. Risks and size

1. **Over-masking in `failure=` fields** (R1): two corpus texts lose text.
   Visible, safe; documented.
2. **SBOM refusal widens** (R5): `a:b@c@host:path` values now refused.
   Rare; CHANGELOG.
3. **Cost**: `one_line` is two masker passes (about 2x base on every
   adversarial shape, still linear); the ANSI alternation without its gate
   cost 7x on letter runs, so the gate is load-bearing (a mutation target
   and a shape: `m` * n).
4. **Header prose masked** (`X-Api-Key: header`): accepted, as for
   `Authorization:`.
5. **Merge with C1's split of `logging_config.py`**: textual, see 9.

Size: about 22 files (12 source, 9 tests, docs and working docs), about 300
lines of source and 400 of tests. Under the split threshold.

## 9. Overlap with C1 and C2

- `logging_config.py`: C1 may split it. This PR changes `loggable`,
  `one_line`, `excerpt` and adds `escaped_literal`, `collapsed`. Merge
  order per the roadmap (sweep C, then this PR): this PR rebases onto C1's
  split and puts the helpers where `one_line` lands. C1 should not change
  these four functions' bodies.
- `messages/_field_writers.py`, `messages/_lock_say.py`: leave `_steady`,
  `failure_text` and `_cut_failure` to this PR; wording changes there in C1/C2
  are fine (no conflict in the masking lines).
- `messages/_line_kind.py` (summary regex cost): left to sweep C.
- `docs/url-credentials.md`: C2's quote checks may touch it; this PR edits
  only the masking list (section "What is not read").
- Nothing in `core/url_masking/` is expected in C1 or C2.

## Appendix: prototype measurements (4c194136 vs prototype)

Probe (selected; all leaked on base, all masked in the prototype):
`abc(Request ID: a)ghp_...` to `abcghp_***`; `https://user:S3cr\n3tPw99x@h/x`
through `one_line` to `https://***:***@h/x`; `token: \x1b[33mghp_...` to
`ghp_***`; `'ghp_A1b2C3\u200bd4...'` through `free_text` to `'ghp_***'`;
`alice:hunter2X@x@host:o/r` to `***:***@host:o/r`; `Cookie: session=...;
other=1` to `session=***; other=***`; `{"X-Api-Key": "..."}` to `"***"`;
`Bearer "..."` to `Bearer "***"`; `Authorization: Bearer\nhunter2Xabc` to
`Bearer\n***`; setuptools relay of a split URL: no piece.

Per-regex cost on 200,000 characters (seconds, base / prototype with the
gate): `m` run: SCP 0.009 / 0.009, PURL 0.007 / 0.009, header 0.012; prose
words: SCP 0.010 / 0.010, token 0.011 / 0.011; ANSI and token text: token
0.009 / 0.016. Without the gate the SCP and PURL passes took 0.07 s (7x).
