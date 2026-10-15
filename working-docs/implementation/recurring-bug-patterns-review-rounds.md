---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: review rounds of PR #300 and PR #305

See also: [recurring-bug-patterns.md](recurring-bug-patterns.md) (the main
list; split here for size),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md),
[AGENTS.md](../../AGENTS.md) ("Recurring bug patterns", the one-line summaries).

## From PR #300 (extras, authors, copyright on every route)

- **Coverage that depends on the interpreter.** `_assigned_string`'s
  `except (SyntaxError, ValueError)` is reached by a NUL on 3.10/3.11
  (`ast.parse`: "source code string cannot contain null bytes") but not on
  3.12+, where the tokenizer rejects it first in `_logical_line`. The local
  `.venv` is 3.10 and showed 100%; Codecov reported one line missed (line 287,
  found through `api.codecov.io/.../file_report/<path>?sha=<sha>`). Fix: a row
  that tokenizes everywhere and is not a statement (`a = = '1'`).
  Do: for every `except` tuple that lists several exception types, write one
  row per type that is raised on every supported version.
- **A reversal needs a probe corpus.** The ruling "one `Author` value is one
  author" (2026-10-14) was implemented and tested, and the 11,500 tests
  passed, while `Ann <a@x.org> and Bob <b@x.org>` recorded nobody and the
  dependency route fell back to the Maintainer. The tests pinned the new rule,
  not what HEAD recorded. A fresh read-only review that ran HEAD and the tree
  on the same inputs found it. The fix (cut only where the text proves a
  list) came from the maintainer's option answer, not a guess.
  Do: before accepting a change of reading, run 30 to 50 representative inputs
  through the old and new code and list each input whose record count fell.
- **A hint must be conditioned on what the branch did.** The one-author
  `INFO:` fired next to the "not recorded" `WARNING:` for the same value.
  Do: emit a status line only on the path that recorded the thing it names.
- **A test that pins a loss is wrong even when the rule says so.** The row
  `bare-address-after-name` expected `[b@x.org]` for `Doe, a@x.org, b@x.org`
  because the splitter dropped `Doe` and `a@x.org`; it stayed green for a
  round. Do: when a row's expected value has fewer records than its input
  names people, justify it in the row's comment or fix the code.
- **Warn-once keys must name the whole input.** A key made from a 120
  character excerpt merged two different over-cap fields into one warning.
  Do: key on a hash of the whole value plus the field name.
- **A confinement check and the open must be one operation.** A textual
  `in .parents` test failed on a case-insensitive file system (macOS) and a
  check followed by the backend's own open (Flit, PDM) leaves a swap window.
  `core/path_confine.py` compares `(st_dev, st_ino)` of the opened handle with
  the resolved path and treats `st_ino == 0` as no identity.
- **A deterministic cap before a parser beats catching its exception.**
  `ast.parse` on a 300,000-attribute expression segfaults 3.10 (exit 139), so
  a `try/except RecursionError` cannot protect it; the line is capped by
  length first, and the tests run the input in a child process.
- **Reuse the tool's own code for a tool's own syntax.** A hand-written Poetry
  caret converter wrote `^0.0.3` as `<0.1.0`; poetry-core writes `<0.0.4`.
  poetry-core is a dependency, so its converter is used, behind a lazy lookup
  and a drift-guard test (no upper pin).
- **An agent's "the tree is clean" is a claim about its start.** The maintainer
  committed between turns; an agent's base for its fail-on-base proof was a
  commit, not the working tree. Check `git log` and `git status` before and
  after every delegated round.


## From PR #305 (registry v3 review rounds)

Each was found by a fresh read-only reviewer who ran a real repro, not by the
author or the existing tests.

- **A guard before a side effect drops the effect.**
  `_import_sbom_element` skipped an element whose name cannot be encoded as
  UTF-8 and returned before `registry.reserve_id(spdx_id)`; its id (`#File-9`)
  was then minted for another key, breaking "a retired id is never reused".
  Reserve first when only the name is bad; test by registering until the
  counter passes the skipped id.
- **A fix scoped to explicit input leaks to implicit input.** "An unreadable
  PATH argument is an `ERROR`" was implemented in the walk root, which the
  default roots (`src`, `data`) share, so an unreadable `data/` turned a
  warning-and-continue into rc 1 against HEAD. Thread `explicit: bool` from
  the CLI (`bool(args.paths)`) through `generate` -> `index_files` ->
  `_iter_files`; keep one walk. Method that found it: run the same
  invocations against a `git archive HEAD` copy with `PYTHONPATH` pinned and
  diff.
- **A conflict branch returned early and skipped the cascade.** `hash_conflict`
  made `_find_survivor` return `(None, "")`, so the content-hash and
  structural criteria never ran: two fragments carrying the same changed
  bytes produced two elements, and bytes already under another id made a
  third. Skip only the by-id fold; the renamed-apart result applies when no
  other criterion matches.
- **First-seen survivors are order-dependent.** Preferring the registry-pinned
  id: a minted id's namespace belongs to one fragment, the registry namespace
  is shared by several, so count sources per namespace over ALL fragments
  before the first merge (`merge_fragments` loads them all first; load
  warnings may now precede merge warnings), rank by count, keep the earlier on
  a tie. Test both fragment orders and the base-holds-the-pinned-id case.
  Key a source by the full path (`base_dir` + path), not the relative path.
- **A dedup cache keyed by name merges distinct content.** One dataset package
  per `(name, digest)` per run: a file rewritten between declarations stays
  two packages, and roles of repeated declarations attach to one.
- **`relative_to` does not collapse `..`.** `generate([Path("../out/o.txt")])`
  registered `../out/o.txt`; `normpath` both sides first, `realpath` only as
  the fallback for a symlinked root; an in-project symlink to an outside
  directory is still keyed by its project path.
- **A placeholder name must not become a registry key, and must be flagged,
  not name-matched.** The wheel `unknown` package (no usable `.dist-info`)
  was looked up and harvested like a real package: two unrelated broken
  wheels shared one id and left a junk entry. `identity_known` is set by the
  generator and skips lookup and harvest. `unknown` is also a valid PyPI
  name, so a name check would reject a real package. A document
  namespace seeded from the placeholder collided on identical payload
  digests, so the wheel's base file name is folded into the seed
  (`identity_seed`).
- **A coverage gap is first a subset-run artefact, then dead code.**
  `_fragments_refs.py` line 137 looked uncovered in a partial run and was 100%
  in the full suite; `_is_eligible_file`'s ignored-directory guard was
  genuinely unreachable (the walk prunes and `_skipped_name_in` rejects first)
  and was removed with its parameter and helper.
- **Intermittent failures during a multi-agent round are first suspected as
  concurrent edits.** Four permission tests failed in one combined run while
  another agent edited the same area; each passed alone and the next full run
  was clean. Re-run alone, then after the agents stop, before investigating.
- **A tool left at a default is a silent bug:** `sed -i` needs a backup
  suffix argument on macOS (`sed -i ''`); a scripted edit that failed with
  "undefined label" changed nothing: check the edit landed.
