---
Created: 2026-11-19
Last-Modified: 2026-11-27
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Catalogue PR 13 (Git source): tests, steps, gates, docs, risks

See also: [message-catalogue-pr13-plan.md](message-catalogue-pr13-plan.md)
(sites, design, rulings Q1 to Q15). Sections 5 to 9 of the same plan.

## 5. Tests (one per boundary)

New files: `tests/messages/test_git.py` (entries, lines, fields, frame),
`tests/messages/test_git_surfaces.py` (CLI, library), `tests/extract/remote/
test_git_say.py` (decisions), edits to `tests/messages/test_frames.py`
(table test names five frames and their surfaces), `tests/_message_drift.py`
(`SAMPLES`), `tests/messages/test_drift_quotes.py` (markers for the seven
families and the variant).

- Frame: an allowed family's line after `Git source: ` is trusted; `over-cap`
  and `lfs-pointer` after it are not; `emit(frame=GIT_FRAME)` with
  `over-cap` raises `InternalError`; `frame=` at `ERROR` raises; `Frame(
  levels={"INFO"}, families=None)` raises; AST drift test: each
  `emit(..., frame=X)` site's family in `X.families`; RELAY_FRAME: a
  scanner relay of a `text-malformed` record keeps its code (fails if
  families were topic-derived: regression for C8).
- Redirect (`test_git_redirect.py` local server): followed (`url-moved`);
  refused for each `why` (http target; non-`/info/refs` target); exactly 5
  hops passes and 6 raises (`url-unsafe`, `.code` unchanged); probe
  failures: `HTTP 404`, no Location, `no answer in time`, `URLError("x")`
  (prints `URLError`, never `str`: Q14), `OSError` subclass name.
- `git-url-invalid`: each of three lines; port case with
  `https://u:s3cret@h:abc/x`: `s3cret` absent from stderr and from
  `str(exc)`; scp-style `u:p@h:path` masked; segments `..`, `%2F..`, `%00`,
  `.git`, `\`.
- `git-ref-not-found`: path-style and query-style (two sites, one line); ref
  with `%0A` and `\x1b` (one escaped line).
- `git-missing`: patch `pitloom.extract.remote._git_run._which` (the
  imported name, never `shutil.which`); CLI `[git-missing]`, exit 1; library
  `pitloom_code`.
- Timeout before the call (`remaining() <= 0`) and during (`status None`):
  both `download-timeout`; inventory sees both sites coded
  (`tests/scripts/message_inventory/`: a `raise _timed_out(...)` fixture).
- `_failed`: network text -> `download-network-failed`; other text ->
  `git-repository-unusable`; server `remote:` text with `\r\n`, `\x1b`, a
  fake ` [over-cap]` and `https://u:tok@h` -> one line, code
  `git-repository-unusable`, token absent; `trusted_message` trusts it.
- `A and B` rules, one test per side: `_not_a_repository` (code
  clone-failed and "not found" in text; each false alone) and
  `page.plain_url == page.repo_url` (retry or not); `_checkout` retry (code
  and `HTTP 400`; each false alone); Q15 template guard.
- Empty repository (`git init` bare, served): `/empty`, `.code`
  `git.clone-failed`.
- Resolution (row 14): each of four shapes, cut query alone, version
  ignored alone, both notes, clone URL equal to given (no line), trailing
  slash only (shape 1).
- Links: 0 (no line), 1, 2; link into `.git`; link to a folder. POSIX only
  (Windows symlinks need privilege: `skipif` by one module constant).
- File/folder (rows 18, 19): each branch; `target.file` set -> raises.
- Hint (Q9): inner `project-not-found` + subprojects, whole repository and
  folder -> hint lines, code `project-not-found`, class RSE `git.no-project`;
  6 subprojects -> `and 1 more`; inner coded other code -> untouched; inner
  uncoded -> untouched (fails on base); no subprojects -> untouched;
  `git_target.py:188` same four cases; `trusted_message` trusts each
  printed line (fails on base).
- Relay dropped: CLI on `ssh://` prints exactly one stderr line (fails on
  base: two); library `caplog` has no WARNING. Same for PyPI offline (Q11).
- Echo summary: no code on the record; `echo=False` silent; credentials in
  the clone URL absent.
- Credential per new or widened field: `url`, `target` (Location with
  userinfo), `error`, `command_line`, `ref` (`ghp_` token shape masked at
  the sink).
- Surfaces (`test_git_surfaces.py`, `platform`, `loopback`): CLI `loom
  project|model|generate <local url>` line, `[code]`, exit code for
  `git-url-invalid`, `git-ref-not-found`, `git-repository-unusable`,
  `offline-unusable`; library `pitloom_code` from
  `generate_git_project_sbom`, `generate()`, `fetch_git_project`.
- Determinism: SBOM bytes of the local-server project vs `main` with
  `--creation-datetime 2026-01-01T00:00:00Z` (messages only change).

Platform: every new file classified (`pytest <f> -m platform --collect-only
-q`); git subprocess, path, symlink and encoding tests get `pytestmark =
pytest.mark.platform`; the local smart-HTTP server
(`tests/_git_http_server.py`) is POSIX-only (existing `skipif`). Label
`test-all-os` on the PR.

Windows dry-run notes (put in each brief): `_which` returns `git.exe`;
`path` of the checkout has backslashes (`quote_source`, never `repr`);
`mask_checkout` on a Windows temp path; `shlex.join` POSIX quoting in the
echo is as today; `PureWindowsPath` checkout folder into `path` for the
hint line; no `/tmp` in tests (`tempfile.gettempdir()`); CRLF in a served
`pyproject.toml` (`write_bytes`).

Mutation targets (Gate B): `_text_re` family filter (drop the `families`
clause); `emit` frame check; `_failed` branch; `_not_a_repository`'s `and`;
`_checkout`'s `or`; `explaining_failures`' narrowed condition;
`_probe_once` `str` fix; `_log_resolution` shape choice.

## 6. Order of steps and agents

Branch from fresh `origin/main` (user creates it). Before step 1: `git log
--oneline -3`, `--check` passes at 154.

### Step 1, Opus: core (one commit)

Fence: `src/pitloom/messages/**`, `scripts/generate_message_reference.py`
and a new `scripts/_message_reference_frames.py` (Q12),
`tests/messages/test_frames.py`, `mkdocs.yml` (nav for the `git` page).

1. `_frames.py`: `families`, `__post_init__` rule, `GIT_PREFIX`,
   `GIT_FRAME`, `RELAY_FRAME.families` (Q2 list); `FRAMES`.
2. `_lines.py` filter; `_emit.py` `frame=`/`frame_values=`.
3. `_fields_git.py`, `REF_KINDS`; merge; widened meanings.
4. Entries: new `_git.py` (seven families, about 250 lines; split
   `_git_decisions.py` if over 300), public `messages/git.py`, `_topics.py`
   (`git` topic + title), `_catalogue.py`/`__init__.py` registration as PR
   12 did; `target-ambiguous/git-page` and the hint lines in
   `_sbom_target.py` (194 lines); `url-moved`, `url-unsafe`,
   `query-no-effect`, `download-network-failed`, `config-unsafe` text.
5. Summary `GIT_COMMAND`.
6. `--write` the reference; Tier 1: `pytest tests/messages
   tests/scripts/message_inventory -n 4`, mypy on `src/pitloom/messages`.
   Import order test both ways if a new module imports `extract.remote`.
7. Hand A, B, C the exported names.

### Step 2, three Sonnets in parallel (after step 1 lands)

Each brief: read CLAUDE.md first; British English; ASCII in comments and
docstrings; no `%r`, no raw `exc`; catalogued messages only through
`emit`/`remote_error`/`say_summary`; never edit generated pages or the
baseline; no git writes; touched tests only (`pytest <files> -n 4`,
`--lf`), `ruff format`, `ruff check --fix`, `mypy` on touched files; report
judgement calls to Opus; the Windows dry-run notes of section 5; never put a
frame on an exception's text; never add `not found`/`HTTP 400` to a
template.

**Sonnet A: `extract/remote/` and callers.** Fence:
`src/pitloom/extract/remote/{git.py,_git_run.py,_git_redirect.py,
git_url.py,_git_folder.py,git_target.py,pypi.py}`, new
`src/pitloom/extract/remote/_git_say.py`,
`src/pitloom/assemble/_generators_git.py`,
`src/pitloom/cli/commands/_remote.py`, `tests/extract/remote/test_git_*.py`,
`tests/extract/remote/test_pypi_fetch*.py`, `tests/test_network_helpers.py`,
`tests/test_network_retry.py`. Not: `messages/`, `core/temp_dirs.py`,
`_hub_files.py`, `huggingface*.py`. Brief: "Code rows 1-22 and the four
'also touched' sites of section 1 of `<plan path>` with the entries Opus
exported from `pitloom.messages.git`, `.network`, `.targets`, `.pypi`,
following section 3.3: `remote_error` for every raise; `_timed_out` module
function; `_failed` both branches; echo via `say_summary(GIT_COMMAND)`;
decisions via `emit(..., frame=GIT_FRAME)` with a `URL=` subject; move
`_log_resolution`, `_drop_outside_links`, `_folder` to `_git_say.py`
(git.py under 450 lines); one `_ref_not_found` helper in `git_url.py`
(under 500); `subproject_hint` returns data; narrow `explaining_failures`;
drop the relays `git.py:222`, `pypi.py:455,464`; `temp_dir(...,
log_prefix=...)` unchanged (PR 14); fix the probe `str` reason. Update every
test in your fence that pins old wording or the removed constants. Report,
per row, the code and line used, and every changed stderr text."

**Sonnet B: docs and skills.** Fence: `docs/git-urls.md` (the Messages
table, lines 411-445, and every quote), `docs/python-api-remote.md:35-73,
140-150`, `docs/messages.md` (frames on WARNING/INFO), 
`skills/sbom-generate/references/git-url.md` (lines 26, 60, 87, 98-104,
116), `skills/sbom-generate/SKILL.md` and `skills/sbom-enrich/SKILL.md`
only if a quoted line changes (grep `Git source`), `CHANGELOG.md`. Brief:
"Rewrite each quoted Git line to the catalogue's new text with its
`[code]` (`docs/message-codes-*.md` regenerated by Opus are the source);
remove the `WARNING: Git source: <reason>` row and the 'after the same text
as a WARNING' clauses (relay dropped); say ERROR lines carry no frame;
`git.clone-failed` now has `pitloom_code` `git-repository-unusable`
unless the network. Run `pytest tests/messages/test_drift_quotes.py
tests/test_docs*.py -n 4`. No link from `docs/` into `working-docs/`.
British English." CHANGELOG: fold into the existing catalogue bullet (Git
source) with the PR link; no new bullet.

**Sonnet C: new tests** (section 5). Fence: the new test files of section
5, `tests/_message_drift.py` (`SAMPLES`),
`tests/messages/test_drift_quotes.py` (markers),
`tests/scripts/message_inventory/` (one fixture). Brief: "Write section 5's
tests against `pitloom.messages.git` and the real fetch: the local
smart-HTTP server `tests/_git_http_server.py` (`serve_git`, `make_repo`),
the redirect server of `tests/extract/remote/test_git_redirect.py`, the CLI
via `subprocess` for surfaces. Short `ids=`. Classify each file
(`platform`, `loopback`). Wording assertions: `trusted_message` or a short
stable substring. Fail-on-base: run each regression test with
`PYTHONPATH=<git archive of main>/src` from inside the extracted copy and
record it fails there." C writes entry and frame tests at once; fetch tests
run after A lands.

### Step 3, Haiku: sweep (after A lands)

Fence: test files outside A, B, C fences; nothing in `src/`. Brief: "grep
`tests/` for `Git source`, `redirected to`, `names repository`, `is not a
repository; trying`, `blob filter`, `symbolic link(s)`, `is a file, not a
folder`, `is a folder, not a file`, `Invalid path in URL`, `No branch or
tag`, `empty repository`, `only http and https`, `not installed or not on
PATH`, `RESOLVED_INFO`, `REDIRECT_INFO`, `PROBE_FAILED_INFO`,
`REDIRECT_REFUSED_WARNING`, and A's reported texts. Known hits outside A's
fence: `tests/cli/test_cli_project_git_url.py`,
`tests/cli/test_cli_git_url_download_cap.py`,
`tests/cli/test_cli_unfetchable_remote.py`,
`tests/assemble/test_spdx3_compliance_shacl.py`,
`tests/test_over_cap_surfaces.py`. Update each to the new text, run that
file. Report any `%r` in a touched template, any touched file over 450
lines, any new field missing from `SAMPLES`." Live tests
(`test_git_platforms_live.py`, `network` mark) pin `PROBE_FAILED_INFO` and
the blob filter: A owns them; Opus runs them with `--network` at Gate B.

### Step 4, Opus: integrate and gate

Regenerate (`--write`), `--write-baseline` (expect 132), page sizes (each
under 30,000 bytes and 800 lines; `targets` after the variant), review
rounds (fresh-context reviewer given the diff, not conclusions), the stderr
sweep (6.3), working docs (migration plan row 13 counts C1, frames-forward
PR 13 section built, review-rounds entry, roadmap pointers for out-of-scope
findings), Gates A and B.

## 7. Gates

### 7.1 Tier 1 (between rounds)

`.venv/bin/pytest <touched> -n 4 --lf`; linters on touched files;
`PYTHONPATH=src .venv/bin/python -m scripts.message_inventory --check`;
stderr diff of the sweep corpus vs `main`.

### 7.2 Gate A, from the worktree root

```shell
export PYTHONPATH=src
PY=/Users/arthit/projects/pitloom/.venv/bin/python
$PY -m ruff format examples/ src/ tests/
$PY -m ruff check --fix examples/ src/ tests/
$PY -m flake8 examples/ src/ tests/; echo "flake8=$?"
$PY -m pylint examples/ src/ tests/ tests/*/; echo "pylint=$?"
$PY -m mypy examples/ src/ tests/; echo "mypy=$?"
.venv/bin/pyright --pythonpath "$PY" examples/ src/ tests/; echo "pyright=$?"
.venv/bin/pyrefly check --python-interpreter-path "$PY" examples/ src/ tests/; echo "pyrefly=$?"
$PY -m bandit -r src/pitloom; echo "bandit=$?"
$PY -m scripts.message_inventory --check; echo "ratchet=$?"
$PY scripts/generate_message_reference.py --check; echo "reference=$?"
$PY -m pytest tests/ -n 4
$PY -m pytest tests/messages tests/extract/remote tests/cli tests/assemble -n 4 \
  --cov=pitloom --cov-branch --cov-report=term-missing \
  | grep -E "messages/(_frames|_lines|_emit|_git|git|_fields_git|_sbom_target)|remote/(_?git|pypi)|_generators_git|commands/_remote"
$PY scripts/manual_cli_checks --only 'M/*/*git*' '8' 'M/completeness'
```

Read each exit code directly (never through `| tail`). Build the licence
database first if tests fail on `main` too (`licenseid update --source
packaged`). Run `shellcheck`/`actionlint` only if `scripts/action/` is
touched (not planned). Delete `<prefix>-tmp/pytest-of-*` after runs.

### 7.3 Gate B

Mutation (section 5 targets, each mutant runs its module's tests);
`scripts/manual_cli_checks -j 8` full, then `--network --only
'M/*/*git*'` (live GitHub); `pytest -m network
tests/extract/remote/test_git_platforms_live.py` (blob filter, live hosts);
determinism (two runs + `main` diff); Windows dry-run (section 5 notes); a
fresh-context sweep agent on the full diff; fresh read of
`skills/sbom-generate/references/git-url.md` in full against the code;
`gh pr view <n> --json labels` for `test-all-os` and that `Unit tests` and
`Build wheels` ran on the head SHA after the label.

### 7.4 stderr sweep (HEAD vs tree, offline)

Feasible without the network: the local smart-HTTP server
(`tests/_git_http_server.serve_git`, `git http-backend` on 127.0.0.1,
POSIX) and a local redirect server; run each case on `main` (an archive of
it, `PYTHONPATH` pinned) and on the tree, `loom project <url>`, diff
stderr, exit code and SBOM bytes:

- plain clone URL; page URL with branch + folder; tag; full commit; cut
  query; trailing slash only; ref not found; a `src`-group page (not a
  repository, retry); file page naming a folder; folder page naming a file;
  repository with links out, into `.git`, to a folder; empty repository;
  a monorepo root (hint, whole) and a folder URL (hint, folder);
- `ssh://`, `git@h:p`, `https://h:abc/r`, `%2F..` segment, `--offline`,
  `--max-download-bytes 1`, `PATH` without git (`git-missing`);
- redirect 301 to `.git` (followed), to `http://` (refused), to a sign-in
  page (refused), seven hops (too many), probe 404, probe hang (`no answer
  in time`, a server that never answers within a shortened budget:
  in-process harness, as the budget is not a flag);
- a URL with `user:token@` in each case above that names a URL.

Expect: identical exit codes and SBOMs; every INFO/WARNING Git line gains
`URL=` and a code; the `WARNING: Git source: <reason>` duplicates are gone;
ERROR text changes per section 3.2. Network-only: Azure DevOps blob filter
400, live GitHub/GitLab page URLs, a real TLS failure.

## 8. Docs, skills, CHANGELOG

- Quotes to rewrite (grep verified): `docs/git-urls.md` (13 `Git source`
  quotes, the Messages table 411-445, `Invalid path in URL` x2, the network
  paragraph 390-405), `skills/sbom-generate/references/git-url.md` (26, 60,
  87-88, 116), `docs/python-api-remote.md` (41-51, 112, 144). Generated
  pages regenerate (`message-codes-targets.md` quotes the config-unsafe
  line).
- `tests/messages/test_drift_quotes.py` `_MARKERS`: one per new family
  (`test_every_family_has_a_marker` fails until then); after the rewrite
  the Git table rows hold markers and are checked.
- No CLI flag or subcommand changes: no `SKILL.md` description change, no
  `_matrix_plan.py` entry.
- CHANGELOG: fold into the existing catalogue bullet; no new bullet.
- Working docs: migration plan row 13 (C1), frames-forward PR 13 section
  marked built, review-rounds entry, roadmap pointers (Q15 raw stderr
  attribute if deferred; C10 if deferred).
- Format-gap ledger: none (messages only).

## 9. Risks and unknowns

Top 5 risks:

1. **Frame restriction drops codes silently.** `relay_extra` returns
   `None` (no error) when a framed text is not trusted; a too-narrow
   `RELAY_FRAME.families` or `GIT_FRAME_FAMILIES` strips codes from real
   lines with no test failing. Mitigation: the AST drift tests (reader
   modules, `emit(frame=)` sites) and a scanner relay regression per
   non-model family.
2. **Text sniffing.** `_not_a_repository` and the blob-filter retry read
   `str(exc)`; a template word (`not found`, `HTTP 400`) would turn every
   failure into a retry. Mitigation: the Q15 guard test and the `A and B`
   tests on both sides.
3. **Credential leaks through new fields.** `target` comes from a server's
   `Location`, `error` from server `remote:` lines, `command_line` from
   argv, `url` on the bad-port path (previously left out on purpose).
   Mitigation: one credential test per field, source masking plus the sink.
4. **Pins outside fences and live tests.** `network`-marked live tests
   (`test_git_platforms_live.py`) pin the probe and filter lines and run
   only with `--network`; the CLI tests pin `Git source`. Mitigation:
   Haiku sweep, full suite, live run at Gate B.
5. **File sizes.** `git.py` 517 (over), `git_url.py` 499, `_git_run.py`
   476, `messages/_fields.py` 459, `generate_message_reference.py` 578:
   splits come first (`_git_say.py`, `_fields_git.py`, the frames helper).

Unknown:

- Whether the four "network-refused" sites of row 13 were all coded or some
  moved (C1 not traced one by one).
- The `targets` page size after the variant (about 25 KB, I); measure at
  step 1, else Q8's alternative.
- Whether `trusted_message`'s worst case (quadratic, `LONGEST_LINE`) grows
  with one more frame alternative in the regex (I: one more alternation;
  time it on a 64 KiB hostile line).
- The live servers' current wording (Azure 400, GitLab redirects): network
  only.
- Whether `_failure`'s joined text can exceed a useful length (no cap
  today beyond `MAX_OUTPUT_BYTES`, 8 MiB of stderr in one line); out of
  scope, roadmap candidate.
