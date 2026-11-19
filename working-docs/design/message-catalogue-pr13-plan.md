---
Created: 2026-11-19
Last-Modified: 2026-11-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 13 (Git source): build plan

See also: [message-catalogue-pr13-build.md](message-catalogue-pr13-build.md)
(tests, steps and agents, gates, docs, risks),
[message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md),
[message-frames-forward.md](message-frames-forward.md).

Status (2026-11-19): not built. The user accepted every recommendation
of Q1 to Q15 (section 4); do not re-ask them. Written by Opus on `main` at
8bdca1e6; re-verify line numbers before building.

Read-only plan on `main` at 8bdca1e6 (PR 12, #501, merged). Last tag
`v0.24.0`: every new entry `since="0.25.0"`. Worktree
`/Users/arthit/projects/pitloom/.claude/worktrees/catalogue-registry-ids`.
Pattern: `working-docs/design/message-catalogue-pr12-18-plan.md` and the PR 12
build plan. Tags: (V) verified in code or by a run, (I) inferred.

## 0. Counts and ratchet

`python -m scripts.message_inventory --jsonl` filtered by `_scope.in_scope`
and `not coded` over `extract/remote/*git*` (V):

| Module | Baseline | Sites |
| - | - | - |
| `pitloom.extract.remote.git` | 10 | 147, 222, 278, 323, 373, 405, 459, 490, 508, 511 |
| `pitloom.extract.remote._git_redirect` | 5 | 104, 200, 205, 213, 229 |
| `pitloom.extract.remote._git_run` | 4 | 213, 218, 226, 239 |
| `pitloom.extract.remote.git_url` | 3 | 411, 456, 476 |

22 in scope, all to 0. Baseline 154 -> **132** (`--write-baseline`, check the
four modules leave the file). Out of the count: `git.py:252`
(`_log_resolution` call; its body, 373, counts), `_generators_git.py:138`
(`InternalError`), `messages/_config_unsafe.py:27` (mechanism),
`pypi.py:455,464` (bare `%s` relays, `PASSTHROUGH_PAT`), `temp_dirs.py:164`
(PR 14). Levels: 11 ERROR (raises), 2 WARNING, 9 INFO.

## 1. Sites

Surfaces: CLI (`loom project|model|generate <url>`, `cli/commands/_remote.py`
under `@cli_error_handler`, V); library (`generate_git_sbom`,
`generate_git_project_sbom`, `generate()` line 232, `fetch_git_project`); the
Action through the CLI; the hook never fetches Git (V). Every Git failure is a
`RemoteSourceError` (`.code` dotted, documented in
`docs/python-api-remote.md:41-51`; `.pitloom_code` read by `code_of`). No
site is quiet- or once-gated; no `-v` gating exists on this route (V).
Credential handling: `url` values go through `sanitize_url` (+
`sanitize_url_credentials` for scp-style) and `loggable` at the source; the
CLI handler masks again at the sink (`escape_controls`).

| # | file:line | Lvl | Text now | Exception / caller | Credential exposure | Maps to |
| - | - | - | - | - | - | - |
| 1 | `_git_redirect.py:104` | E | `Invalid URL: the port is not a number.` | RSE `git.url-invalid` from `_probe_url`, via `resolve_git_url` | none now (URL left out on purpose); new `url` must be `sanitize_url` (V: masks `https://u:p@h:abc/x`) | `git-url-invalid` (new) |
| 2 | `_git_redirect.py:200` | I | `Git source: could not check %s for a redirect (%s); asking git directly` | decision, `resolve_git_url` | url `_shown`; reason is a class name or `HTTP n` | `git-redirect-unusable` (new) |
| 3 | `_git_redirect.py:205` | W | `Git source: %s redirected to %s, which is not followed: %s` | decision; then git clones `current` (fails on the 3xx) | target from the server's `Location`: `_shown` masks userinfo | `url-unsafe` WARNING line (reuse) |
| 4 | `_git_redirect.py:213` | E | `{url} redirects more than 5 times.` | RSE `git.too-many-redirects` | `_shown` | `url-unsafe` `TOO_MANY_REDIRECTS_LINE` (reuse) |
| 5 | `_git_redirect.py:229` | I | `Git source: %s redirected to %s` | decision | following URL may carry carried-over userinfo: `_shown` masks | `url-moved` (reuse, line exact) |
| 6 | `_git_run.py:213` | E | `git is not installed or not on PATH.` | RSE `git.not-found` | none | `git-missing` (new, Q5) |
| 7 | `_git_run.py:218` | I | `Git source: $ %s` (each git call) | trace, no condition | argv `sanitize_url` each + `sanitize_url_credentials` | Summary (no code, Q3) |
| 8 | `_git_run.py:226` | E | `raise self._timeout(what)` | already `download-timeout` at run time | none | refactor to module helper (no text change) |
| 9 | `_git_run.py:239` | E | same | same | none | same |
| 10 | `git.py:147` | E | `{exc}{hint}` (subproject hint after a project error) | RSE `git.no-project`, code DROPPED | folder names `loggable` | hint lines on `project-not-found` (Q9) |
| 11 | `git.py:222` | W | `Git source: %s` relay of every failure | duplicate of the CLI `ERROR:` | `sanitize_url_credentials` | dropped (ruling 5) |
| 12 | `git.py:278` | E | `Cannot fetch {url}: only http and https URLs are fetched (...)` | RSE `git.url-invalid` | `shown` | `git-url-invalid` |
| 13 | `git.py:323` | I | `Git source: %s is not a repository; trying %s` | decision | `sanitize_url` both | `target-ambiguous/git-page` (Q8) |
| 14 | `git.py:373` | I | `Git source: %s names repository %s%s` (`named` built at run time: ref kind, ref, folder, two notes) | decision | `sanitize_url`; ref/folder `loggable` | `target-ambiguous/git-page` 4 lines + `query-no-effect` 2 lines (Q8) |
| 15 | `git.py:405` | I | `Git source: the server rejected the blob filter; fetching without it` | decision | none | `git-filter-unusable` (new) |
| 16 | `git.py:459` | E | `{url} is an empty repository (no commits).` | RSE `git.clone-failed` | `shown` | `git-repository-unusable/empty` (Q7) |
| 17 | `git.py:490` | I | `Git source: %d symbolic link(s) leading out ... were not followed` | decision (security) | none | `git-link-unsafe` (new, Q13) |
| 18 | `git.py:508` | I | `Git source: %s is a file, not a folder` | decision | path `loggable` | `target-ambiguous/git-page` |
| 19 | `git.py:511` | I | `Git source: %s is a folder, not a file; reading it` | decision | path `loggable` | `target-ambiguous/git-page` |
| 20 | `git_url.py:411` | E | `Invalid path in URL: {url}` | RSE `git.url-invalid` | `sanitize_url` + `quote_source` | `git-url-invalid` |
| 21 | `git_url.py:456` | E | `No branch or tag {ref} in {repo} (a commit needs ...)` | RSE `git.ref-not-found` | `sanitize_url` | `git-ref-not-found` (new) |
| 22 | `git_url.py:476` | E | same text, query-style page | same | same | same line; one helper `_ref_not_found` |

Also touched (coded today, not counted):

- `_git_run.py:285` (`_failed`, non-network branch): `RemoteSourceError(
  "git.clone-failed", text)` with no code. The inventory counts `raise
  _failed(...)` as coded because the helper body has one coded branch: a
  ratchet blind spot (V). Text is git's own stderr, server `remote:` lines
  included (attacker text; `_failure` joins lines with `; `, masks
  credentials and the checkout, `loggable`). -> `git-repository-unusable`
  (Q6).
- `git_target.py:188`: coded `project-or-model-not-found` but text
  `{exc}{hint}` is no line of the entry, so `trusted_message` refuses the
  printed line (V by reading `_lines.py`). -> hint lines (Q9).
- `messages/_config_unsafe.py:27`: `CONFIG_UNSAFE_REMOTE_LINE` holds the
  literal `Git source: `; said at `_generators_git.py:186` and
  `cli/commands/_remote.py:85`. -> template without the prefix, said with
  `frame=GIT_FRAME` (printed text unchanged).
- `pypi.py:455,464`: the PyPI relays of ruling 5 (Q11).

Not PR 13's: `temp_dirs.py:164` and `temp_dir(CHECKOUT_DIR_PREFIX,
log_prefix=_LOG_PREFIX)` at `git.py:217` (PR 14 changes the call to
`frame=GIT_FRAME`); the `Build: ` option line from `settle_not_applicable`
(PR 14); `credentials-unsafe/*` Git lines (unprefixed today, stay so);
`huggingface*` lines (PR 14).

## 2. Contradictions (plan and design text vs code)

- C1. Migration plan row 13: 29 sites (11 fetch-failed, 11 decision, 2
  redirect, 4 network-refused, 1 missing). The tree has 22 (V). The
  "network-refused 4" are gone from the Git modules (coded by #487's
  credential lines, `url-unsafe/host-spelling`, `pypi-url-unusable`;
  I: not traced one by one). Fix the row: -22, now -22.
- C2. `_git_run.py:181` is now `:213`; frames-forward's line list
  (`_git_redirect.py:59,68`, `git.py:105,324,405,507,524,528`,
  `_git_run.py:190`) is stale: those are the constants' lines or older
  numbers. Agents locate by function name.
- C3. frames-forward: "10 INFO, 3 WARNING, 0 ERROR" with the prefix. Now 9
  INFO + 1 catalogued INFO, 2 WARNING; the 11 ERROR raises never had the
  prefix (only the relay printed `WARNING: Git source: <ERROR text>`).
- C4. Row 13 proposes `git-redirect-invalid`; `url-unsafe` already has an
  `ERROR` and a `WARNING` redirect-refused line and an `ERROR` too-many line,
  and `url-moved` the exact followed line (V). Reuse them (Q4).
- C5. Row 13 "reuse `download-timeout`, `download-network-failed`": already
  shipped (0.24.0) and wired (`_git_run.py:270-290`); only the non-network
  failure is uncoded, and `download-network-failed`'s summary says it
  "carries no code" (changes with Q6).
- C6. Rows 8, 9: `raise self._timeout(...)` is coded at run time; the
  inventory does not resolve a method through `self` (`_index.lookup`), so
  -2 comes from a refactor, not a coding.
- C7. frames-forward lists `git.no-project` as uncoded; `git_target.py:188`
  is coded but untrusted, `git.py:147` uncoded. Both append text after a
  catalogued line.
- C8. frames-forward sketch: `RELAY_FRAME` families "derived from
  `_topics.py`" (models, model-fields). Readers under `extract/ai_model/`
  also say `text-malformed` (`warn_lone_surrogates`, files topic) and a
  licence line (`warn_unless_expression`, licences topic) (V by grep).
  Topic-derived families would make `relay_extra` drop those codes
  silently (it returns `None`, no `InternalError`) (Q2).
- C9. frames-forward's "Git and Hub go to `network` (12.1 KB)": now 12.8 KB,
  222 lines; adding about 8 entries reaches about 22 KB (Q10).
- C10. Found: `_probe_once` reports `type(reason).__name__`; a
  `URLError` whose `reason` is a `str` prints `(str)` (V: run). Fix with the
  line (Q14).

## 3. Design

### 3.1 The frame (Q1)

`GIT_FRAME = Frame(levels={"WARNING","INFO"}, template="Git source: ",
surface="a Git URL fetch", families=GIT_FRAME_FAMILIES)` in
`messages/_frames.py`, added to `FRAMES`.

- `Frame.families: frozenset[str] | None = None`; `__post_init__`: a frame
  with `WARNING` or `INFO` in `levels` must name families (so `RELAY_FRAME`
  must too, Q2); `ERROR`-only frames keep `None`.
- `_lines._text_re(message, level)`: frames filtered by `level in f.levels
  and (f.families is None or message.family in f.families)`; still at most
  one. `says`, `relay_extra`, `trusted_message` follow.
- `emit(..., frame: Frame | None = None, frame_values: Mapping | None =
  None)`: text is `frame.render(frame_values or {})` + the line; a frame not
  allowing `message.family` or the level raises `InternalError` (a
  programming error; note `InternalError` is a `ValueError`: no Git
  `except ValueError` sits between, V). Implementation: log with
  `frame_prefix + shape.template`, the frame's rendered text escaped
  (`%` doubled) as it is a literal.
- No `frame=` on `CodedValueError` or `remote_error` (rule 4).
- `GIT_FRAME_FAMILIES`: `git-redirect-unusable`, `git-filter-unusable`,
  `git-link-unsafe`, `target-ambiguous` (only the `/git-page` variant is
  said framed; restriction is by family, so the three `FILE=` lines of
  `target-ambiguous` are trusted after it too: accepted, I), `url-moved`,
  `url-unsafe`, `query-no-effect`, `config-unsafe`. A drift test: every
  `emit(..., frame=X)` site's message family is in `X.families` (AST walk).
- `RELAY_FRAME.families`: every family a module under `extract/ai_model/`
  can say (emit, `warn_*` helpers), listed explicitly, with a drift test that
  walks those modules (Q2).
- Printed text after the change: `INFO: Git source: URL=<url>: redirects to
  <target>; followed [url-moved]`. Each INFO/WARNING line gains `URL=` and a
  code; ERROR lines never carry the frame.

### 3.2 Codes (all new ones `since="0.25.0"`, actor/effect per R1)

New topic `git` ("Git URLs") unless Q10 says `network`. Templates are
proposals; Opus fixes them at step 1 against `template_problem` and
`test_no_two_entries_share_a_line` (level + template unique over ALL lines,
V `test_drift_sources.py:165`).

| Code | Page | Lvl | Cond | Effect / actor | Fields | Template (proposal) | Rows |
| - | - | - | - | - | - | - | - |
| `git-url-invalid` | git | E x3 | invalid | not-written / user | url | `URL=%(url)s: only http and https URLs are fetched (not ssh, git, file or scp-style addresses); nothing fetched`; `URL=%(url)s: the port is not a number; nothing fetched`; `URL=%(url)s: a path part decodes to ., .., an empty part, a backslash, a NUL or .git; nothing fetched` | 12, 1, 20 |
| `git-ref-not-found` | git | E | not-found | not-written / user | url, ref* | `URL=%(url)s: no branch or tag %(ref)s; a commit needs its full 40 or 64 hex digits` | 21, 22 |
| `git-missing` | git | E | missing | not-written / user | none | `git is not installed or not on PATH; nothing fetched` | 6 |
| `git-repository-unusable` | git | E | unusable | not-written / user | command, error | `git %(command)s: %(error)s; nothing fetched` (NOT `... failed: ...`, the network line) | `_failed` non-network |
| `git-repository-unusable/empty` | git | E | unusable | not-written / user | url | `URL=%(url)s: an empty repository (no commits); nothing read` | 16 |
| `git-redirect-unusable` | git | I | unusable | none / none | url, why | `URL=%(url)s: could not be checked for a redirect (%(why)s); git asked directly` | 2 |
| `git-filter-unusable` | git | I | unusable | none / none | url | `URL=%(url)s: the server rejected the blob filter; fetching without it` | 15 |
| `git-link-unsafe` | git | I | unsafe | thinner / none | url, number | `URL=%(url)s: %(number)s symbolic link(s) leading out of the repository, into its .git directory or to a folder; removed, not followed` | 17 |
| `target-ambiguous/git-page` | targets | I x7 | ambiguous | none / none | url, target, ref_kind*, ref*, path | `URL=%(url)s: read as repository %(target)s`; `... %(target)s, %(ref_kind)s %(ref)s`; `... %(target)s, folder %(path)s`; `... %(target)s, %(ref_kind)s %(ref)s, folder %(path)s`; `URL=%(url)s: not a repository; read as repository %(target)s`; `URL=%(url)s: %(path)s is a file, not a folder; read as the file named`; `URL=%(url)s: %(path)s is a folder, not a file; reading it` | 14, 13, 18, 19 |

Reused, new lines or wider text only:

| Code | Change | Rows |
| - | - | - |
| `url-moved` | summary/did name the Git redirect probe too (`_pypi_info.py:182`) | 5 |
| `url-unsafe` | summary/did name Git (redirect not followed: git then asks the URL itself; too many: no SBOM); `why` meaning widened; Git `outcome` `the URL itself asked of git` (a literal passed by one constant) | 3, 4 |
| `query-no-effect` | Git page with a cut query: the existing line, framed; new INFO line `URL=%(url)s: the version names no branch, tag or commit; the default branch is read` | 14 notes |
| `config-unsafe` | `CONFIG_UNSAFE_REMOTE_LINE` template loses `Git source: `; both callers pass `frame=GIT_FRAME` | - |
| `project-not-found` | ERROR hint lines, two (whole repository / folder advice): `No pyproject.toml, setup.cfg, or setup.py found in %(path)s; Python projects are in subfolders (%(folders)s); give the URL of one of them` and `...; Pitloom reads the folder in the URL only` | 10 |
| `project-or-model-not-found` | the same two hint shapes after its line | `git_target.py:188` |
| `download-network-failed` | summary: "a git failure with any other cause carries no code" -> "is `git-repository-unusable`" | - |
| Summary `GIT_COMMAND` | `Summary(template=GIT_PREFIX + "$ %(command_line)s", topic="git")`, `GIT_PREFIX` the one constant the frame's template is built from | 7 |
| `RemoteSourceError` | docstring: every `git.*` code now has a `pitloom_code` | - |

Fields (`messages/_fields_git.py`, `GIT_FIELDS`, merged in `_fields.py`,
which is at 459 lines): `ref` (free, "a branch, tag or commit as the URL
names it"), `ref_kind` (closed `branch|tag|commit`, `REF_KINDS` in
`_field_tables.py`), `folders` (free, "subfolders holding a Python project,
comma-separated, then `and N more`"), `command_line` (free, "a git command
line as run, credentials taken out"). Widened meanings: `url` (a Git URL),
`target` (the repository a page URL names), `why` (why a redirect could not
be checked), `error` (git's own `fatal:`/`error:`/`remote:` lines, joined
with `; `; server text), `command` (adds `ls-remote`, `rev-parse`,
`checkout`, `init`, `remote`: the regex `[a-z][a-z-]*` already allows them).
`SAMPLES` in `tests/_message_drift.py` gets each new field.

One field, one meaning: `path` stays quoted (`'<path>'`); `ref` is never
used for a URL; `error` is never a URL. `why` gets only the probe reasons
(`HTTP <n>`, `HTTP <n> without a Location`, `no answer in time`, an exception
class name; never `str`: Q14).

### 3.3 Code moves in `extract/remote/`

- One builder: Git raises through `remote_error(code, message, line,
  **values)` (`_http_errors.py:69`, sets `.said`), so a later caller that
  goes on can say the WARNING twin. No Git route continues after a failure
  today (V), so no WARNING twins are added (each relay is dropped instead).
- `_git_run.py`: `_timed_out(seconds, what)` module function (rows 8, 9);
  `git-missing`; `_failed` codes both branches; echo through `say_summary`.
- `git.py` (517 lines, over the soft limit): move `_log_resolution`,
  `_drop_outside_links`, `_folder` and the hint wrapper's line choice to a
  new `extract/remote/_git_say.py` (see also pointers both ways). Drop the
  relay (row 11). `RESOLVED_INFO`, `_LOG_PREFIX` (kept only for `temp_dir`
  until PR 14: rename to the frame's constant), `REDIRECT_INFO`,
  `REDIRECT_REFUSED_WARNING`, `PROBE_FAILED_INFO` leave `__all__` (private
  alpha; tests move to the catalogue lines).
- `git_url.py` (499 lines): rows 21, 22 through one helper; row 20 coded.
- `_git_folder.subproject_hint` returns `(names, more)` data, not text; the
  two wrappers render the hint line (Q9). `explaining_failures` wraps only
  `code_of(exc) == PROJECT_NOT_FOUND.code`, not `None` (an uncoded failure
  is re-raised as it is).
- Text-sniffing guards: `_not_a_repository` (`"not found"`, `"does not
  appear to be a git repository"`) and `_checkout` (`"HTTP 400"`) read
  `str(exc)`. The new `git-repository-unusable` line keeps git's text in
  `error`, so they still work, provided no template adds those words; a test
  asserts no Git ERROR template contains them (Q15).

### 3.4 Example (stderr, `loom project`)

```text
INFO: Git source: URL=https://gitlab.example/g/p: redirects to https://gitlab.example/g/p.git; followed [url-moved]
INFO: Git source: $ git -c http.followRedirects=false ... clone --depth 1 ...
INFO: Git source: URL=https://gitlab.example/g/p/-/tree/v1/svc: read as repository https://gitlab.example/g/p.git, tag v1, folder 'svc' [target-ambiguous/git-page]
ERROR: loom project: URL=ssh://host/r: only http and https URLs are fetched (not ssh, git, file or scp-style addresses); nothing fetched [git-url-invalid]
```

### 3.5 Exception classes that must not change

- Every Git failure stays `RemoteSourceError` with its `.code` unchanged
  (`git.url-invalid`, `git.ref-not-found`, `git.not-found`,
  `git.clone-failed`, `git.too-many-redirects`, `git.timeout`,
  `git.no-project`, ...): `docs/python-api-remote.md:41-51` documents them;
  callers branch on `.code` (`git.py:320,402,456`, `_hub_files.py:422`).
- `git.no-project` keeps its class and code; only its text becomes a line.
- `_generators_git.py:138` stays `InternalError`.
- `CodedValueError` from `git_target` (model errors) unchanged.

## 4. Rulings (Qn; all accepted 2026-11-19)

- **Q1. `Git source: ` as `GIT_FRAME` (rule 3).** [Frame, as
  frames-forward designs: lines are said with it (Git) and without it
  (PyPI's `url-moved`, `url-unsafe`, `query-no-effect`), and PR 14 needs the
  mechanism.] Evidence: `url-moved` is said by PyPI unframed
  (`_pypi_info.py:182`). Alternative: drop the prefix (rule 1: every new
  line has `URL=`; PyPI parity, it has no `PyPI source: ` on its lines): no
  `Frame.families` work in PR 13, about 150 fewer lines, but the echo and
  `config-unsafe` lose the route name and PR 14 builds the mechanism alone.
- **Q2. `RELAY_FRAME.families`.** [An explicit list of every family a
  reader module says, held by an AST drift test over `extract/ai_model/`.]
  Alternative (frames-forward): derive from the models and model-fields
  topics: drops `text-malformed` and the licence line's codes on a scanner
  relay, silently (C8).
- **Q3. The git command echo (row 7).** [A Summary (R1: no condition, out
  of the ratchet by kind), its template built from the frame's constant; a
  doc row stays.] Alternatives: DEBUG (the docs' "each git call" row goes;
  a user loses what ran), or a code (no condition to name).
- **Q4. Redirect lines.** [Reuse `url-moved` and `url-unsafe` (exact
  shapes exist); widen their summaries.] Alternative: `git-redirect-invalid`
  (plan): a second family for one condition, and a line equal to
  `url-unsafe`'s would fail `test_no_two_entries_share_a_line`.
- **Q5. `git` missing.** [`git-missing` on the git page.] Alternative:
  `tool-missing` shared with PR 14's interpreter line
  (`_models_wheel_build_subprocess.py:133`): one family on one page, so it
  would sit on `git` while PR 14 is a build line, or move pages later (moving
  breaks anchors).
- **Q6. A non-network git failure.** [Code it `git-repository-unusable`,
  line `git %(command)s: %(error)s; nothing fetched`.] Evidence:
  `_git_run.py:285`, a blind spot of the ratchet (C5). Alternative: leave it
  uncoded (the docs say it "carries no code"): the most common Git failure
  (404, sign-in refused) stays uncoded.
- **Q7. Empty repository.** [Variant `git-repository-unusable/empty`.]
  Alternative: fold into `project-not-found` (no project, but the advice
  "point at a project folder" misleads on an empty repository).
- **Q8. Page decisions.** [Variant `target-ambiguous/git-page` (Pitloom
  chose what a URL names by its rule, as `target-ambiguous` already does for
  a Git URL of `README.md`); the resolution line split into four fixed
  shapes; the cut query said by the existing `query-no-effect` line, the
  ignored version by a new `query-no-effect` line.] Alternative: a new
  `git-page-ambiguous` on the git page (keeps `targets`, 22.9 KB, from
  growing about 2.5 KB); or one structured `named` field (a free field
  beside others fails `template_problem`).
- **Q9. Subproject hint (rows 10, `git_target.py:188`).** [Hint lines on
  `project-not-found` and `project-or-model-not-found`, two each (advice
  differs by `whole_repository`), the inner code kept as `pitloom_code`, the
  class `RemoteSourceError("git.no-project")` kept; wrap only
  `project-not-found`.] Alternative: an `INFO` summary with the hint, then
  the inner error re-raised: changes the documented class
  (`FileNotFoundError` instead of `RemoteSourceError`).
- **Q10. Topic.** [New `git` page ("Git URLs"): the seven Git families and
  the summary.] Alternative: `network` (12.8 KB -> about 22 KB, under the
  guard, but mixes Git-only families with the shared ones).
- **Q11. PyPI relays (`pypi.py:455,464`).** [Drop in PR 13 with Git's
  (ruling 5 named the three together; ratchet 0); `fetch_pypi_file`'s
  callers (`_generators_pypi.py`, CLI) let the error reach the `ERROR:`
  line.] Alternative: leave to PR 14.
- **Q12. Frames in the generated reference.** [One "Printed after
  `Git source: `" line per entry whose family a WARNING/INFO frame allows,
  in a helper module (`scripts/_message_reference_frames.py`; the
  generator is 578 lines).] Alternative: defer (frames-forward "Not
  decided"): a skill then cannot tell a reader that the prefix is not part
  of the line.
- **Q13. `git-link-unsafe` effect.** [`thinner`: the links are removed, so
  the SBOM lists neither them nor what they point to.] Alternative: `none`
  (they lead outside the repository anyway).
- **Q14. Probe reason `str`.** [Fix in PR 13: a `str` reason prints
  `URLError`.] Alternative: roadmap entry.
- **Q15. Text sniffing on `str(exc)`.** [Keep, guarded by a test that no
  Git template contains `not found`, `does not appear to be a git
  repository` or `HTTP 400`.] Alternative: keep git's raw stderr on the
  exception (a new attribute, a pickling change in `__reduce__`):
  out of scope, roadmap.

R1 itself is ruled (2026-11-14): decisions coded by condition, actor none,
effect none (`git-link-unsafe` aside, Q13); counts and traces as Summary.

