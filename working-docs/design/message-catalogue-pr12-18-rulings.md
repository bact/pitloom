---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue PRs 12 and 18: rulings, tests, risks and steps

See also: [message-catalogue-pr12-18-plan.md](message-catalogue-pr12-18-plan.md)
(the sites, codes and surfaces these rulings decide; "row n" and "section
n" below refer to it),
[message-catalogue-migration-plan.md](message-catalogue-migration-plan.md).

Sections 4 to 7 of the PR 12 and 18 plan, split out for size. Status and
sources: see the plan's header.

## 4. Rulings for PR 12 (Qn = item n)

Ruled or done: **1** (two PRs, PR 18 first: done, #498). **12** (two
expression codes by LicenseID's category: built, `Refusal.malformed`).
**13** (`license-db-missing` own code: built). **14** (licence surrogates on
`text-malformed`: built, `LICENSE_LINE`).

**Ruled 2026-11-19: every bracketed answer of 2 to 11 below is accepted**
(including 9: a `[build-system]`-only `pyproject.toml` is DEBUG). PR 12a is
merged (#499); PR 12 is on branch `catalogue-metadata`. A build-ready re-check
of this plan against the tree (two line drifts from the flit cast of #500;
ratchet target 154) added five rulings, also accepted 2026-11-19; no
backward compatibility is kept:

- **D1**: a `[project]` that is not a table, or a `name` that is not a
  string, is coded `metadata-invalid` ERROR in `read_pyproject`, beside row 44.
- **D2**: row 28 relays the `setup.py` error as its WARNING twin whenever
  not `quiet`, then raises `project-name-missing` plainly.
- **D3**: row 52 is `metadata-invalid` `FILE=<f>: listed by <field>, not
  found; skipped` (and a `not a file name` line), not `file-unreadable`.
- **D4**: row 17's catch narrows to `ValueError`, pinned by a fuzz test.
- **D5**: rows 18 and 21 both stay (the type, then the consequence).

The "Open" labels below are the questions as asked.

Open (asked 2026-11-18, ruled above):

2. **Reuse `config-malformed` for project `pyproject.toml`/`setup.cfg`
   syntax, split from `file-unreadable` (I/O, UTF-8)?** [Yes.] Evidence:
   the entry already holds `INI_FILE_LINE` for a `setup.cfg` read for
   `[tool:pitloom]` (`setup_cfg_pitloom_config`), so rows 29 to 31 would
   give the same file's syntax error a second code on the metadata read;
   the hook reads `[tool.pitloom]` first (`hatch.py:413`, then
   `_config_parse.py:417`) and the CLI `[project]` first, so one loader
   gives one code on both. `effect` (not-written), `actor` and advice fit;
   the `summary` and `did` (config routes only, "not yet coded") must be
   rewritten (2.1). Advice differs from `file-unreadable` (decision D).
3. **Rows 17, 27, 37: a WARNING twin carrying the inner code?** [Yes, R6
   and pr8-12 ruling 2, by `relay_extra` with an identical template; the
   outcome moves to `did` (2.4).] Evidence: the registry save relays this
   way (`_registry_save_say.py:46-55`); an appended outcome would make the
   text no line of the code, and `relay_extra` returns `None`.
4. **Drop `Build: ` from rows 1 to 6?** [Yes, as frames-forward decided;
   in the stderr sweep. No skill or doc quotes a discovery line.]
5. **Three discovery codes, or one?** [Three: the advice differs (report a
   failure; pass `--allow-build`; fix the layout).]
6. **Row 12: relay shape or coded?** [Relay shape, by reshaping the code
   (2.6), not by widening `_relay.py`: the text is setuptools' own; one
   rule for both relays; the rule stays as mutation-tested.] Evidence: the
   inventory record has `relays: null`, two arguments and `one_line(line)`
   of a loop variable, which `_one_line_param` and `_says_only` refuse.
   Cost: the line loses `<dir>`. Alternative if `<dir>` must stay: widen
   `prefixed` to one leading `quote_source(<param>)` subject argument (a
   rule change with its own counter-examples).
7. **`poetry-core` API moved: `library-unusable`?** [Yes, with a new line
   (`required library API not found: <module>: <error>; ...`) and a clause
   in the summary, which today says "fails to import" only; advice: a
   `poetry-core` release Pitloom supports (`>=2.4.1`).]
8. **Dynamic INFO/DEBUG.** [Settled by PR 18's pattern (1.2); applies in
   PR 12 only if Q6 codes row 12 instead.]
9. **Row 44.** [Split by branch, verified by probe.] `[project]` present
   without `name` (`[project]\nversion = "1"`): a real error PEP 621 refuses,
   today the same WARNING: code it `metadata-invalid` (WARNING, `FILE=`,
   `project.name` missing; read setup.cfg/setup.py). `[project]` absent
   (a `[build-system]`-only legacy setuptools layout, the normal case): absent
   source data, quiet by the design principle, but a level change in a coding
   PR needs a ruling: [lower it to DEBUG, listed in the stderr sweep];
   else code it WARNING `metadata-no-effect` and log the conflict.
10. **Rows 56, 58, 41: prove unreachable, then `InternalError` or a
    forward?** Row 56 [`InternalError`]: unreachable by reading. The only
    writers of `field_conflicts` are `record_setuptools_conflicts` (inside
    `read_setuptools`, `setuptools.py:272`) and
    `reconcile_installed_metadata` (`reader.py:253`, after every merge). The
    two merges' secondaries never hold one: `pyproject.py:409` merges Poetry
    metadata (no writer), `reader.py:96` the `read_pyproject` result
    (`_setuptools_dynamic` merges options without recording). Probe test: a
    structural test that `add_conflict`'s callers are those two, plus a run
    of a legacy layout with `setup.py`/`setup.cfg` and an `.egg-info`
    disagreeing. Row 41 [forward]: REACHABLE today (two probes); after the
    loader twin and the `setup.cfg` decoder, its residue is
    `parse_pitloom_config` and `setup_cfg_pitloom_config` only, the same as
    row 58's. Row 58 [forward, then `InternalError` for an uncoded
    `ValueError`]: the inventory finds no uncoded raise in `core/_config*`
    reachable from a table (`_config_types.py:75` is a parameter check; a
    table read reports through `_require_choice`), but a stdlib
    `ValueError` is invisible to it. Probe test: every `[tool.pitloom]` key
    of the drift table times four bad values (wrong type, NUL, huge int,
    empty) through `load_config_file` and the sdist route, each error coded;
    only then the residue becomes `InternalError`.
11. **Row 57 (`_extract_utils.py:261`) is not project metadata.** [Move
    out; ratchet 154.] Evidence: callers are `extract/dataset/croissant.py:252`
    (raises to the CLI: dataset, PR 17) and `assemble/spdx3/deps_pypi.py:106`
    (swallows the `ValueError`, returns `None`); `extract/remote/_pypi_release.py`
    calls another `fetch_json`. The URL case is `download-network-failed`
    (PR 13 reuses it), the absent file PR 17's.
15. **Index size: BLOCKING.** [Move the values table out of the index into
    one generated page per site, in a small PR before PR 12.] Measured on
    this tree (bytes, `MAX_BYTES = 30_000`,
    `scripts/generate_message_reference.py:144`, guarded by
    `test_every_generated_file_fits_the_size_limit`):

    | File | Bytes | Headroom | Code rows | Values rows |
    | - | - | - | - | - |
    | `docs/message-codes.md` | 29,252 | 748 | 123 rows, 11,995 (97.5 each) | 88 rows, 14,981 (170 each) |
    | `sbom-enrich/references/messages.md` | 28,910 | 1,090 | 11,380 (92.5 each) | 14,981 |
    | `sbom-generate/references/messages.md` | 28,866 | 1,134 | 11,380 | 14,981 |

    PR 12 adds 13 code rows (about 1,270 bytes), 2 page-list lines (about
    115) and 2 to 3 fields (340 to 510): the docs index reaches about 30,900
    to 31,100, over by itself (rows alone: 30,640). PRs 13 to 17 add about
    25 to 30 code rows and variants (migration plan rows 13 to 17) and about
    10 fields: about 35 to 36 KB without a change. The values table is 51%
    of the index and grows faster per entry than the code table. Moved out:
    the index is about 14.3 KB, 15.7 after PR 12, about 19 after PR 17; the
    values page about 15.6 KB, about 18 after PR 17. Rejected: shorter rows
    (dropping `Since` and `Level` saves about 25 bytes a row, 3 KB: one PR's
    worth); an index of pages only (a skill finds a code's page in
    `messages.md`: `known-limitations.md:90`, `pypi-url.md:137`,
    `deterministic-pass.md:24`); raising the limit (CLAUDE.md's file cap).
    Files: `scripts/generate_message_reference.py` (`render` drops
    `_values()`; a `render_values_page`; `expected_pages` lists it so
    `orphans` keeps it; `_PAGE_RULE` and the module docstring say "the
    values page"; it is 533 lines, so move the index and values renderers
    into a sibling module first), `tests/messages/test_generated_reference.py`
    (481 lines: `_RENDERS`, a test that the page lists every used field and
    that no topic is named `values`; a new test file if it nears 500),
    regenerated index, values pages (`message-codes-values.md`,
    `messages-values.md`) and every topic page (the rule text), `mkdocs.yml`
    nav. The frames table (328 bytes) stays in the index. PR 12 then splits
    its codes over two topic pages (2.1): licences runs 2.2 KB a code, so 12
    codes on one page would be 22 to 27 KB, near the guard.

## 5. Tests

New files: `tests/messages/test_metadata.py`,
`test_metadata_discovery.py`, `test_metadata_surfaces.py` (`platform`:
paths, encodings, archives), and a loader test beside `core`'s tests.
Parametrised, short `ids=`. Edited: `tests/test_message_ratchet.py` (four
relays if Q6), `tests/_message_drift.py` (`SAMPLES` for each new field),
`tests/messages/test_config.py` (441 lines: the `config-malformed` twins;
a new file if it nears 500).

- One case per boundary through the real reader: each condition per row;
  the OSError/UnicodeDecodeError/syntax split of rows 30 and 34 (a
  directory named `setup.py`, `\xff` bytes, `setup(`); a NUL in `setup.py`
  on 3.10/3.11 (`ValueError`) and 3.12+ (`SyntaxError`), each its own case;
  `failed` true/false on row 1; hint present/absent on rows 5 and 6; both
  branches of row 44; `quiet` silent per `q` row; row 39 said once.
- Canaries: no line with `config file` before `FILE=` or `FILE=` twice
  (sdist TOML, sdist non-UTF-8 `setup.cfg`, `--config`; each fails on
  base); a newline, `\x1b`, a lone surrogate in a `build-backend` string
  and a PDM error (one escaped line); `user:pass@` in a backend error
  (masked); a TOML error on line 3 of a CRLF file says line 3;
  `PureWindowsPath` `C:\p\x.tar.gz:pyproject.toml` into the file field (two
  colons before `: `); fail-on-base with `PYTHONPATH` pinned to a c4674613
  archive.
- Surfaces: CLI line, `[code]`, exit code; hook (`staged_sbom`) for row 7,
  the loader, a Poetry row; `loom fragment` for the loader; library
  `pitloom_code` from `generate_project_sbom` and `read_sdist`; Action
  through the CLI.
- Drift: the relay rule on both relays (and row 12's reshaped one) and on a
  planted `log.warning("%s", text)` (must count); `READ_USES` liveness;
  quotes via `test_drift_quotes.py`; a `relay_extra` twin for every inner
  code rows 17, 27, 37 can relay.
- Q10 probes: `add_conflict` callers; the config key times bad value sweep.
- Classify each file (`-m platform --collect-only -q`); `test-all-os`.
- Wording pinned in `tests/` today (re-counted): "file discovery" 70 lines
  in 39 files, "disagree" 52 in 31, installed 42 in 7, `Build: ` 29 in 12,
  "config file " 20 in 14, "Failed to parse project metadata" 6 in 2,
  "Could not parse setup" 7 in 3, "setuptools stderr" 7 in 4. Manual CLI
  checks pin none.
- Mutants: the loader's except order, `failed` in
  `_skip_hatchling_fallback`, the row 44 branch, the forward guards,
  `_read_marker_text`'s exception, the reshaped relay.

Gates (CLAUDE.md): Tier 1 between rounds; Gate A (full suite `-n 4`,
every CI linter, fail-on-base, branch coverage, `--only` manual checks for
`extract/`, `core/`, `plugins/hatch.py`); Gate B (mutation, full manual run
`-j 8`, determinism harness, Windows dry-run, fresh-context sweep, fresh
read of changed skill files). SBOM diff vs `main` empty with
`--creation-datetime` pinned.

## 6. Risks and contradictions

1. **Index over the guard** (ruling 15): measured, blocking.
2. File sizes a rewrite touches (lines; soft ceiling 500): within 60 of it
   or over: `setuptools_cfg.py` 500, `poetry.py` 491, `deps_installed.py`
   489, `pyproject.py` 480, `core/_config_parse.py` 469,
   `_setuptools_options.py` 459, `messages/_fields.py` 453,
   `plugins/hatch.py` 538 (over; touched only if the hook needs a line),
   `scripts/generate_message_reference.py` 533 (ruling 15 PR). None over
   800. A site rewrite must not grow them; move a helper out first.
3. Stacked prefixes today (verified): `No usable project metadata ...
   Could not parse setup.py: ...` (row 28) and `config file
   '<sdist>:<member>': ...` (row 41, both members).
4. Rows 25, 26 echo backend text raw; in a downloaded clone it can quote a
   file or a URL: `masked_free_text`.
5. Row 17 catches `KeyError`; its source is unread.

Contradictions with the older plan docs (each re-checked):

- C1. frames-forward PR 12, `plugins/hatch.py:177`: stale; the call is
  `:176`, and it is no discovery line (1.3).
- C2. Migration row 12, "`setuptools_cfg.py` passthrough 1": none there;
  the passthrough is `_models_wheel_setuptools_relay.py:59`.
- C3. Migration row 12, 50 sites: 58 (section 0).
- C4 to C6 (PR 18: `licenseid database` as an `INPUT_KINDS` kind, the
  surrogate helper as a drop-in, one `expression-malformed`): resolved by
  rulings 12 to 14 as built in #498.
- C7. Review rounds (PRs 8 and 9 second review, item 1): `hatch.toml`
  "lets a `hatch.toml` replace `tool.hatch` wholesale" is false. Read in
  Hatchling 1.32.3 (`.venv`, `hatchling/metadata/core.py:231-254`,
  `ProjectMetadata.hatch`): `hatch_config = tool.hatch.copy();
  hatch_config.update(load_toml(hatch.toml))`, a shallow update per
  top-level key. A `hatch.toml` with `[build]` replaces all of
  `tool.hatch.build` (hooks included); `version`, `metadata` and the other
  keys of `tool.hatch` survive. So the hook table's source is knowable: from
  `hatch.toml` when it has a top-level `build` key, else `pyproject.toml`.
  The fix (`FILE=hatch.toml`, `[build.hooks.pitloom]`;
  `plugins/_hatch_config.py:22`) is no ratchet site; it may ride with PR 12
  as its own commit. Not read: Hatchling 1.29.0 (the floor).
- C8. 8-12 plan section 4: `sdist.py:275` is now `:277`;
  `_extract_utils.py:261` is not project metadata (Q11).
- C9. pr8-12 ruling 4 gave `_poetry_requirements.py` to PR 11; its row 23
  is still uncoded and is PR 12's.
- C10. The earlier version of this plan: "5 callers" of row 7 (6 calls);
  `cli/options_resolve.py:282` as a load site (it swallows); Q10's "the
  wrappers' residue is unreachable" (row 41 is reached today); the loader
  in `pitloom.core` "unverified for cycles" stands, now beside
  `config_cascade`.

## 7. Order of steps and agents

PR 18 (steps 1 to 3 of the earlier order): done, #498.

**PR 12a, the index split (ruling 15), from fresh `main`, before PR 12:**

0. Opus: rulings 2 to 11 and 15 with the user.
1. BUILT 2026-11-19 (branch `catalogue-index`): the values page
   (`message-codes-values.md`, `messages-values.md`), `expected_pages`, the
   rule text, `mkdocs.yml` nav, `tests/messages/test_generated_values_page.py`.
   Not split into a sibling module (about 575 lines): the two tests that
   load it by path would first need `scripts/` on `sys.path`; noted in the
   complexity roadmap. Index 29,252 to 14,338 bytes, values page 15,589.
2. Opus: review; Gate A (generator tests, `--check`, linters on
   `scripts/` and `tests/`); no src change, ratchet unchanged.

**PR 12, from `main` after 12a merges:**

3. Opus: entries (`_metadata*.py`, two topics, `dependency-pin-conflict`),
   `_fields_metadata.py`, the shared twin helper, `config-malformed`
   rewrite and twins, `file-unreadable` use, `library-unusable` line, the
   loader `core/_project_toml.py` with `load_config_file` on it, the forward
   decisions, the discovery line choice, row 12's reshape.
4. Sonnet A `extract/project/` (rows 13 to 52); Sonnet B
   `core/_models_wheel_*`, `config_cascade.py`, `core/project.py`,
   `deps_installed.py`, `sdist.py` wrapper (rows 1 to 12, 53 to 58);
   Sonnet C tests (section 5). Each touches only its files, fenced in
   writing; judgement calls go to Opus.
5. Haiku: stale quotes, `%r` in touched templates, file sizes, `SAMPLES`.
6. Opus: review of every diff, stderr sweep (`Build: ` dropped, row 44,
   row 12's `<dir>`), generator, `--write-baseline` (211 to 153 or 154),
   CHANGELOG folded into the catalogue bullet, Gates A and B, review-rounds
   entries (C7 corrected there too).

Never: an exemption by text, a new condition word, an unruled level change,
`%r`, a helper adding a prefix, dropping a said-once memo, a hand-edited
generated file or baseline, a block `pylint: disable`.
