---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: review rounds of PR #359 to #378 (0.21.0 to 0.22.0)

See also: [recurring-bug-patterns-review-rounds.md](recurring-bug-patterns-review-rounds.md)
(the earlier rounds, PR #300 to #317; split here for size),
[recurring-bug-patterns.md](recurring-bug-patterns.md) (the main list),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md),
[recurring-bug-patterns-test-harness.md](recurring-bug-patterns-test-harness.md),
[AGENTS.md](../../AGENTS.md) ("Recurring bug patterns", the one-line summaries).

## From PR #359, #361 and #362 (0.21.0: licenseid.resolve, release sweep, live tests)

- **A binding returns a default for a field the file does not store.** After
  `fasttext.load_model`, `getArgs().lr` is 0.05 whatever the training value was
  (`lr=0.77` came back 0.05), and `minCountLabel` 0: `Args::save` writes neither.
  `maxn` is stored, but the loader resets it to 0 for a version 11 *supervised*
  model only; the first gate dropped it for every model below version 12, and a
  fresh review caught that with a skipgram file rewritten to version 11. Read the
  format's source for what is written and for version-dependent resets; test with
  a file of each kind, not a mock without the model type.
- **A cache keyed on a file stamp needs more than the mtime.** The licence
  answer cache of #359 was keyed on `(mtime, size)`; a rebuilt database of the
  same size within the clock's granularity would have kept stale answers. It now
  adds the inode, takes a lock, and stores an answer only if the stamp is the
  same after the lookup (a lookup that straddles `licenseid update` is dropped).
- **A static import that closes a cycle fails pylint R0401, even inside a
  function.** `_license_resolve` needed `_license`, which imports the classifier
  that imports it. `importlib.import_module("pkg.mod")` with an annotated result
  keeps mypy's types and passes pylint. Splitting the module is the cleaner fix.
- **A fallback that asks git directly turns a slow host into a bare 3xx.** The
  redirect probe timed out on Savannah and labs.etsi.org, git (which follows no
  redirect) reported `returned error: 301/302`, and the live test failed. The test
  now skips only when the probe failed and the error is a bare redirect; the
  classifier also knows git's GnuTLS wording (`gnutls_handshake() failed`).
- **One marker for two things.** `network` covered 68 tests that only use a
  server the test starts and about 53 that reach real hosts. `loopback` (local
  server, guarded in-process) now runs everywhere; `network` stays out of the
  default job (`-m "not network"`) and runs in the release gate, `live-tests.yml`
  and by hand. The guard covers in-process `connect`/`connect_ex` only, not DNS,
  UDP or a subprocess; a review found a `loopback` test that still asked DNS for
  `evil.example`.
- **A validator's findings come back in hash order.** `spdx3-validate` findings,
  and the values of a SHACL `not in list [...]` message, differed between runs
  (`PYTHONHASHSEED`). Sorted by (source, kind, message) and with the list values
  sorted through `ast.literal_eval`, six seeds gave one output.
- **Sweeps that verified their own claims still shipped defects.** Three agents
  swept docs, comments and skills and each ran the CLI to verify; a fresh review
  of the same diff then found: an over-broad statement ("an invalid `--sbom` is
  refused" was true for SPDX 3 only), a false message when the validator was
  missing, wrong dates and links, and the `maxn` gate. Schedule a fresh-context
  review of the combined diff before merge, and give it the diff, not the
  author's summary.
- **Tooling slips that cost a commit or a command.** `uv sync` wrote a 4,835-line
  `uv.lock` into the checkout and `git add -A` committed it (set
  `UV_PROJECT_ENVIRONMENT`; read `git status`). `pkill -f "uvicorn app.main"`
  matched its own shell and killed the command (write `[u]vicorn`). A bot commit
  (`CITATION.cff` from `codemeta.json`) made a push fail: merge it, do not rebase.
  PyPI's JSON endpoint served the old latest version for a minute after
  publishing: ask for the version URL.

## From PR #364, #365 and the 0.21.1 release (log levels, a failure flag)

- **A signal set by a helper must be set by every path that logs the failure.**
  #365 made `warn_discovery_failed` set a per-thread flag so the dispatcher stopped
  saying "no static config resolvable" after a reported failure. A review found the
  setuptools `PackageDiscoveryError` branch logs its own warning and returned
  `None` without the helper: the old wrong line still followed it. Grep every
  `return None` after a logged failure, and add one test per branch.
- **Lowering a message's level keeps its diagnostic content.** The `INFO:` that
  replaced the missing-database `WARNING:` dropped the path the warning carried
  (`one_line(exc)`); in a container whose `HOME` differs, nothing said where
  Pitloom looked. Keep the fact; change the tag.
- **A message prefix is a classifier only while no sibling shares it.** The
  missing-database test matched `database: not found:`; LicenseID's `no home
  directory; pass --db` has the same prefix and is a setup problem. List the
  sibling conditions of a prefix before keying on it, and test each.
- **Sibling lines share one literal prefix and one separator.** The `INFO:` and
  `WARNING:` about one database said "licence file check" against "license text
  detection" with `:`/`;` against ` -- `. A `_DB_PREFIX` constant and a test that
  both lines start with it and hold one ` -- ` keep them together.
- **A doc says what the code does, not what the commit meant.** "declares a
  licence" was wrong for `Apache2` (still `INFO:` plus `WARNING:`); the doc beside
  it already said "an SPDX expression". Re-read each sentence a change touches
  against its test.
- **A review's side effects leave the repository.** A reviewer ran `HOME=
  licenseid update` and wrote a 17 MB database under `/`. Tell review agents to
  use a scratch `HOME`, and not to run anything that writes a cache.
- **A strict network gate fails on someone else's outage.** The 0.21.1 publish
  gate ran 53 live tests with `PITLOOM_REQUIRE_NETWORK=1`; seven failed because
  `code.overheid.nl` did not resolve and `git.sr.ht` took 135 s to refuse. The
  re-run of the failed job passed. The gate depends on every third-party forge
  being up: keep PyPI, GitHub and one more in it, and the rest in the weekly job.
- **A PR needing its own number for the CHANGELOG.** `test_changelog` wants each
  entry to link its PR; two PRs adding `[Unreleased]` conflict on the second
  merge. Add the entry once the number exists, and merge `main` (never rebase) to
  combine the sections.

## From PR #374 to #378 (embed refusals, masking, model keys, LFS pointers)

- **`json.loads` accepts `NaN`, `Infinity` and `-Infinity`.** A "refuse an SBOM
  that is not well-formed" gate (#374) let `{"x": NaN}` through. Pass
  `parse_constant` to reject the constants, and test a deeply nested document.
  Do: decide what "well-formed" means for the format, then probe the parser with
  its extensions.
- **A new input gate breaks the tests whose stubs relied on having none.** After
  #374 refused an unparsable `--sbom`, existing tests that passed `{}` or
  `{"foo": "bar"}` under `.spdx3.json` names failed. Decide per test which is
  wrong, the stub (make it a valid SPDX stub) or the name (call it `.json`); do
  not loosen the gate.
- **A helper typed `str` fails on the first real exception.** `loggable(exc)`
  raised `AttributeError: 'JSONDecodeError' object has no attribute
  'isprintable'`; the call needed `loggable(str(exc))`. Drive an error branch
  with a real exception object, not a message string.
- **A lint suppression for an unused argument goes on the parameter's line.**
  The `disable-next=unused-argument` for a stub's `pyproject_data` parameter had
  to sit on the line before that parameter, not before the `def`.
- **A lint run that does not import the branch can disagree with CI.** Local
  pylint printed 10.00 while CI reported C1803 (`x == []` in a drift-guard
  test); with the worktree's `src` on `PYTHONPATH` both Python 3.10 and 3.14
  reported it. The cause was not confirmed. Judge pylint by its exit code, with
  `PYTHONPATH` set, on directories.

- **A fix that accepts either of two keys must also keep writing one of them.**
  The registry lookup was changed to try the recorded hash, then the pointer's
  `oid`. A cold review of that fix found that the wheel route then rewrites the
  entry's SHA-256 to the pointer-text digest, so the next checkout run misses it
  and mints a new id: the ids flip-flop between routes. Lookup and write are one
  contract; a pointer needs one stored key (the `oid`) that every route writes,
  and a lookup that tries the other spelling. Test both directions: an entry
  written by route A hit by route B, and B's write hit by A.
- **A module-level skip travels with every import.** `pointer_fixture()` called
  `pytest.skip(allow_module_level=True)` while `tests/_lfs.py` built a shared
  `TREE` at import, so in an sdist (which leaves the fixtures out) 17 modules,
  307 tests, were skipped, among them 61 scanner tests unrelated to LFS. Build
  such data lazily, in a function or fixture, so only the tests that need it
  skip; and make a missing directory in a git checkout a failure, not a skip.
- **A fix that handles one input form can leave its twin.** The pointer licence
  file was skipped in `read_license_file`, but `license = {file = "LICENSE"}` is
  turned into `.text` by `pyproject-metadata` before that function runs, so the
  pointer text still became a `SimpleLicensingText`. When a value reaches the
  code by two forms (a path and the text read from it), list both and test both.
- **`os.path.normcase` is the identity on every POSIX system.** A de-duplication
  key `normcase(realpath(p))` claimed to fold case on macOS and did nothing
  there; APFS `Data.bin` and `data.bin` stayed two keys. Use the file's
  identity, `(st_dev, st_ino)` when `st_ino != 0`, and `normcase(realpath)` only
  as the fallback.
- **A new test must fail without its fix.** One test of the licence reader
  passed with `parse_lfs_pointer` patched to return `None`, because the SBOM
  never contained the text in the way it asserted. Run each new test against the
  pre-fix code, and assert on the value the bug produced.
- **A message path is native, an expected string is not.** Loom's `FILE=` text
  names a dataset member with the platform's separator (`corpus\a.bin`), and two
  tests compared it with `corpus/a.bin`; found by reading the tests as Windows
  would, with `ntpath`. Build the expected text with `os.path.join`. The
  messages stay native, like their siblings.
- **A drift guard against a tool pins the tool's version.** The grammar matrix
  asserts git-lfs 3.4.1's verdict on every row (including the ten rows it
  accepts and Pitloom refuses); another runner's git-lfs may differ. Skip the
  guard unless the version is the pinned one, or compare only the rows both
  versions agree on.
- **An assertion on a quote character fails with an apostrophe in the path.** A
  test expected `quote_source` to use single quotes around a temporary path; a
  Windows user name with an apostrophe changes that. Derive the expected text
  from `quote_source`.
- **Two elements for one file turn a fix into a silent loss.** With a loom
  fragment merged into a built SBOM, a pointer appeared twice: the document's
  element (text digest) and the fragment's (`oid`). Once harvest read both as
  the `oid`, the key was ambiguous and nothing was recorded, so the id changed
  at the next checkout run. The rule that fixed it is separate from `_stale`
  (`pointer_twins`): an element with no recorded key is a twin when a recorded
  file under the same key has the same hash. It reserves the twin's id and logs
  one DEBUG line, and it leaves the existing "older SHA-256" INFO alone. Do:
  when a change makes two readers agree, check every place where one of them
  used to disagree on purpose.
- **A mutant can survive because the test case is too plain.** Dropping the "id
  is in `hashes`" restriction survived until the plain-file case got a pointer
  at another path: its `hashes` was empty, so the restriction was never
  exercised. Give each case the state the condition guards.
- **A new rule goes beside the old one, not into it.** Changing `_stale` to drop
  its `!= sha` check fixed the sequence and broke `held-key-rewritten`. A
  separate rule with its own scope left every old branch as it was; the harvest
  tests assert what is written, and what is logged, in both element orders.
- **A mask added to a shared sanitiser rewrites data as well as messages.** The
  Git checkout mask (#375) sat in `loggable()`, which the CLI also uses for
  `KEY=VALUE` stdout that the Action reads back. It moved to `escape_controls`,
  which only logging calls. Do: list the sink of every caller before changing a
  shared helper, and test the data path, not only the message path.
- **A text rewriter must be linear.** The first mask was not; the word-based
  version (`deque(..., maxlen=1)` keeps the last word) is. Time a rewriter on
  one long line of near-matches before it ships.
- **Strip a placeholder where the value enters.** A padded `unknown` in a Hub
  card licence (#376) was not treated as a placeholder; the card licence is now
  stripped at the source, and `NOASSERTION` or `unknown` gives way to a name.
- **A fixture that satisfies only the marker keeps testing the marker.** Tests
  with `version https://git-lfs.github.com/spec/v1` plus `oid sha256:00` passed
  before and after the pointer grammar became strict, because they only open
  with the version line. They were kept on purpose as the "opening only" case;
  the new "whole pointer" cases use real oids and sizes. Do: when a rule gets
  stricter, name which old fixtures now fall on the other side of it.
- **A predicate standing in for a state is a latent bug.** The summary warning
  tells a checkout pointer from a shipped one by `digest_sha512 is None`. It is
  right today because only three constructors set `lfs_pointer`; a fourth route
  that leaves SHA-512 empty (an over-ceiling file) would be misread. Do: grep
  the constructors when relying on such a predicate, and prefer an explicit
  field.
- **An index keyed by one hash misses when a route records another.** The hook
  stores the pointer text's digest; `id generate` on the checkout stores the
  oid. Lookups by the recorded hash alone lost every pointer file's id on the
  hook route, a silent regression against `main` that no per-task test saw
  because each task tested its own route. A fix accepts either hash in one
  helper (`registry_hashes()`). Do: add a round-trip test across routes for
  every field that two routes record differently.
- **Advice in a message depends on where the file came from.** "run `git lfs
  pull`" is wrong for a Git URL scan, where the clone is temporary. A context
  variable set while the checkout is read carries the route to the warning. Do:
  when a message gives a command, check it works for every source that can reach
  it.
- **`# pylint: disable-next` binds to the next statement, so code inserted
  between them moves the suppression.** A helper placed above `build()` took the
  `too-many-arguments` suppression and left `build()` flagged (exit 8). Put new
  code above the comment, not between it and its target.
- **A static guard keyed on names flags a new constant.** `test_cap_warnings`
  treats every `*_MAX_*` constant as a cap; two format limits of the pointer
  grammar needed entries in its allow list with a reason.
- **A temporary copy made to unblock a parallel task is a merge-time chore.** A
  task copied another task's helper and said so; at the merge a grep for the
  function name found both. Do: ask each agent for its temporary copies, and
  grep for duplicates (and for helpers nothing calls) before the combined gate.
