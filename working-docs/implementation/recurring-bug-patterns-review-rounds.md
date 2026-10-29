---
Created: 2026-10-15
Last-Modified: 2026-10-29
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns: review rounds of PR #300, #305, #306, #311 to #315, #317, #359 to #362 and path keys

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
- **Codecov takes one leg; local 100% is not CI 100%.** CI uploads coverage
  from Linux / Python 3.14 only. `RegistryCopy._at` returned its
  case-insensitive match (`return cut, True`) only where a differently cased
  spelling is the registry's own file, i.e. on macOS; Codecov showed
  `walk_rules.py` at 97.72% (1 line missing, 1 partial) against 100% locally.
  A test reaches it on any file system by making the other-case spelling a
  hard link to the registry (skip where the file system folds case, because
  the folding test covers it). To check without a Linux machine: make a
  case-sensitive volume (`hdiutil create -size 64m -fs "Case-sensitive APFS"`,
  `hdiutil attach -mountpoint ...`) and run `pytest --basetemp <volume>/bt
  --cov-branch`; the line is missing without the test and covered with it, and
  a whole-suite run there found no other such gap. Do: for every branch that
  depends on the file system, the OS or the interpreter, name the CI leg that
  reaches it.
- **A new dataclass field must be set by every constructor call site.**
  `DocumentModel.identity_known` / `identity_seed` were set by the standalone
  wheel and embed routes but not by `_build_sbom_from_project_and_wheel`
  (`embed-wheel --project-dir`): two wheels with different file names got
  one namespace and a pinned `unknown` id was reused. Found by a late
  focused review, not by the 14 tests. Fix: one helper
  (`wheel_document_identity(metadata, wheel_path)`) returning the fields, used
  by all three routes. Do: when a field's meaning is a rule, give it one
  producer; grep every construction of the class when adding it.
- **A batch hint repeats unless it goes through the batch memo.** The
  unknown-identity `INFO:` printed once per wheel in an `embed-wheel` batch;
  other hints use `EmbedFileCache.first_use`. A single-wheel call has no cache
  and still always logs.
- **A Markdown line that starts with `<p>` is an HTML block.** In
  `docs/id-registry.md` a code span wrapped so that a line began with `<p>`
  (`... --project-dir <p>` newline `is not a directory`): Python-Markdown
  ended the page there (2 of 7 headings rendered) and mkdocs reported only
  three "missing anchors". Backticks do not help once the span crosses a line
  break. Reflow so no line starts with `<`; compare source and rendered
  heading counts for every page.
- **A multi-agent round leaves stray files.** An empty `out1.txt` at the
  repo root (an agent's repro) and 1.8 GB of `pytest-of-<user>` in the
  temporary directory; `git status` lists the first, nothing lists the
  second. Check `git status --short | grep -v '^ M'` and clear the
  temporary directory before handoff.

## From PR #306 (model producer and parameter count)

Decisions and the full story:
[g7-model-producer-parameter-count.md](g7-model-producer-parameter-count.md).

- **A byte-identity test must not let the writer stamp the clock.**
  `test_a_route_is_byte_identical_when_run_twice[cli-wheel]` built a PT2
  archive with `zipfile.ZipFile.writestr("mdl/extra/author", ...)`, which
  stamps the member with `time.localtime(time.time())`. The archive bytes
  feed the wheel hash and the Merkle root, hence the document UUID, so the
  two builds differed whenever the second ticked over between them: green
  locally on every run, red once on CI (Python 3.10, Ubuntu). The diff showed
  the UUID first; the real cause was one file hash further down. Fix: write
  the member with `zipfile.ZipInfo(name)` (its default `date_time` is the
  fixed 1980-01-01), and run the test on a clock that moves on every call
  (`monkeypatch.setattr(time, "time", ...)` returning `count(..., 7)`), which
  fails the old shape 3 times in 3. A rerun cannot prove a flake is gone.
  Do: for any test that compares two builds of anything hashed, grep the
  fixture builders for `writestr(<str>`, `time`, `mtime`, `uuid4`, and
  perturb the clock instead of rerunning.
- **Narrowing a derived field's rule needs an inventory of its writers.**
  The package `comment` note ("`ai_hyperparameter` `parameters` holds the
  number of elements...") is derived by the merge from the `parameters`
  entry. A follow-up changed the rule to "keep or add the note only if an
  input carried it", to spare a model's own `parameters` key. That left a
  count added by an `sbom-enrich` fragment (a figure from a model card) with
  no note, which is the main route for a fragment-added count; the change was
  reverted the same day and recorded as "tried, then reverted". Do: before
  restricting a derived field, list every route that writes its source (the
  builder, the `loom` SDK, a fragment, a hand-built model) and run each
  through the new rule.
- **Derive from the value, not only the key.** The same note appeared beside
  `7B` (a `loom.set_model(hyperparameters={"parameters": "7B"})` value): a
  note about element counts next to a label. The rule now also requires the
  value to read as a count (`is_parameter_count_text`: ASCII digits, positive,
  at most 10**15, guarded by length before `int()`), and a test needs a case
  where only the key differs (`llama.context_length: "2048"`): deleting the
  key check survived every other test and was found by mutation testing.
- **A doc claim about a derived field names the code path that derives it.**
  "After a merge every package with a `parameters` entry has the note" was
  true only for packages the fragment merge folds (same `spdxId` in two
  inputs); a package only one input holds keeps its comment as written.
  Do: before writing "after X, every Y", find the call site and say which Y
  it reaches.
- **A check a skill tells the agent to run needs a legitimate input that trips
  it.** The `sbom-enrich` recipe ended with a one-liner printing any
  `ai_AIPackage` name that occurs twice, "regenerate and redraft". Two
  `model.onnx` files with the same graph name in one project do that with no
  fragment at all, so the agent would loop. Compare the fragment's ids with
  the base's, not names.
- **Fail-fast hides the other legs.** The red 3.10 job cancelled the
  Windows, macOS and 3.14 test jobs; "CI is red on one leg" is not "the other
  legs pass". Read which jobs were cancelled before drawing a conclusion.
- **Agents that edit in parallel need their scope fenced in writing, and a
  rule reversal must reach the running reviewers.** The docs-sweep and the
  skills agent were told which tree each owned; a merge-rule change made
  mid-sweep left one doc stale and was reported by the sweep agent itself;
  the reviewer in flight was told by message that the rule was reverted, or
  it would have filed findings against code that was no longer there.

## From the registry path-key PR (2026-10-16)

Built as [id-registry-path-keys.md](id-registry-path-keys.md).

- **A lookup rule restricted by what exists on disk must test the shorter
  (stale) key's existence.** The layout alias "`demo/x.py` is the installed
  path of `src/demo/x.py`" first took any one leading part. With
  `tests/foo/__init__.py` and `foo/__init__.py` both real and equal in bytes
  (empty files), a wheel's `foo/__init__.py` hit the id held for the test
  file. Fix: first part `src`/`lib` only, and the shorter key must not exist
  as a real file or directory under the registry root, so two real files are
  never one alias. Do: for every "A is an alias of B" rule, write the test
  where both exist as real files with equal content.
- **An O(1) lookup replaced by a full-table scan in a hot path.** The same
  loose rule found its candidates by scanning every held key per lookup
  (quadratic in the registry). The built rule constructs the (at most two)
  candidate keys and asks the dictionary for each. Do: when a rule needs
  "which held key matches", derive the candidates from the input; a scan is
  a sign the rule is too loose.
- **Write what you looked up, not what the element is called.** Harvest keyed
  an element by its `.name`; a merged loom fragment's model, found under its
  path key, lost it (K17), and harvesting a model by name released the stem
  key `id generate` had made. Fix: the session records the key each lookup
  used and harvest writes that; an element with no recorded key never moves
  an id held under another key of its type. Do: any "read back, then write"
  pair shares the key by construction, not by recomputing it.
- **User-typed path versus derived path: spell once, at the boundary.** A
  path a user typed takes its on-disk spelling (`DATA/T.TXT` is
  `data/t.txt` on a case-insensitive file system); a path derived from a
  scan, an archive or a registry is used as given. Both go through one helper
  (`pitloom.id_registry.keys`); a call site that spells a key by hand drifts.
- **Order of work against a gate.** A dataset pin made before the data exists
  (`-e data/new.txt:dataset_DatasetPackage`) cannot hold a digest; a strict
  gate would never hit it. The gate became hybrid: a hash-less pin hits any
  content (with an `INFO:`), a hashed entry is gated. Do: when a gate meets a
  pin created before the thing it gates exists, decide what an absent hash
  means.
- **A fixture is green by construction; a review reads the rule against real
  trees.** All three failures of the loose alias rule passed the tests that
  had been written for it; an independent review found them together.

## From PR #311 to #315 (dataset folding, supplier, NumPy typing)

Field-note version, with the measured context:
[datasets-and-reproducible-results.md](sbom-generator-field-notes/datasets-and-reproducible-results.md).

- **`repr(path)` is not `str(path)`.** `repr(WindowsPath)` writes `/`, and
  `repr(str)` doubles each backslash; a message built with `{source!r}` never
  held the path as the OS writes it, and a test asserting `str(path) in
  message` passed everywhere but Windows (#311, four fuzz tests). One helper
  now quotes a source (`core/quote_source.quote_source`) and escapes
  control characters and lone surrogates, so a name with a newline cannot
  split a message over two lines.
  Do: put a path into a message with one helper that writes `str()`, quoted
  and escaped; assert on the same spelling.
- **"No digest" is not "not a file".** The first #314 rule folded a dataset
  name when `found.hex_digest is None`; an empty directory, a file over
  `max-dataset-hash-bytes` and an unreadable file also return `None`. A
  dangling symlink was a path to `artifact_key` (`lexists`) and not to the
  hasher. Fix: `found.kind is not None or os.path.lexists(name)`.
  Do: ask existence with the call that asks it; when two helpers answer "is
  it a path", test the cases they can disagree on (empty dir, over the
  ceiling, unreadable, dangling).
- **A fold keeps the first and forgets the rest.** Two spellings of one
  dataset, the registry pinned under the later one: the pin was ignored with
  no message, and the id depended on declaration order. Fix: one `WARNING:`
  naming the ignored pin; the first spelling is the one looked up and named.
  Do: a first-wins merge that drops a keyed fact says so.
- **Every value in a new message is untrusted.** The pin warning escaped the
  later spelling but not the kept one or the registry id; a name `ds\nWARNING:
  fake` forged a tagged second line. Do: `loggable()` every interpolated
  value, and test with a newline in each.
- **Say a fold once per pair, on every route.** The SDK and the merge route
  deduplicated the `INFO:`; the card route logged each repeat (a thousand
  lines for a card repeating one name). Do: when one message has several
  emitters, test each with a repeated input.
- **Review the fix of a review.** Two of five findings in the third #314
  round were in code the second round added.
- **Count slots against the limit before adding a field.** Adding a
  said-once set to `LoomElements` made 13 instance attributes against a limit
  of 12 (pylint R0902). Three "said once" sets became one set and one helper
  (`_first_time`) rather than a `disable`. Local pylint showed "10.00/10"
  with the message present: read the messages and the exit code.
- **A test that creates case-variant paths probes the file system first.**
  `mkdir("Org/Data")` then `mkdir("org/data")` raised `FileExistsError` on
  macOS before the skip ran. Do: create a `Probe` directory, test `probe`,
  skip, and only then make the pair.
- **`# type: ignore` against a library that changes its types.** numpy's
  `lib.format` was untyped to 2.3 and typed from 2.5, so the ignore was unused
  on one version and needed on the other (#315). Use an `Any` view plus a
  `cast`; check the lowest supported version in a second environment
  (`mypy --python-executable`).
- **Compare failure sets in a degraded environment.** The sandbox cannot
  build the licence database (a GitHub download is blocked), so 73 tests fail
  on `main` too. Stash the change, run, and compare the sorted ids: zero
  new ids is the evidence, not "73".

## From PR #317 (Git URL ingestion; a fresh review after two rounds)

- **A check on the URL does not cover every client the tool starts.** The
  address check and `http.followRedirects=false` bound git's HTTP; git-lfs, run
  by the checkout's smudge filter from the repository's own `.lfsconfig`, was
  a second client past both. List every program the fetch starts and what each
  reads from untrusted data; switch off what is not needed.
- **Text from a server or a subprocess needs the same escaping as a file name.**
  Git's stderr, built into an `ERROR:` message, carried a forged tagged line,
  a `::error::` workflow command and an escape sequence. The escaping helper
  existed and was applied to the echoed command and to refs, not to this path.
  Grep for every f-string that interpolates `err`, `stderr`, `exc` or a URL.
- **A masking helper applied at one site is a bug at the other sites.**
  Credentials were masked in the command echo and not in two messages built from
  the raw URL. Test every message with a URL holding `user:SECRET@`.
- **A new kind of target adds rows to registries no type checker sees.** The
  inert-options table and its docs row, the cap-warning list and the skill's
  size limits each had a guard test; none was run before the first push.
  Run the whole suite, not the touched area, before a PR (full suite on the
  fresh branch: 10 guard failures that the area tests never showed).
- **A fallback needs the condition it is for.** "Retry with the whole URL" on any
  clone failure hid TLS and sign-in errors behind a message about a URL the user
  never meant.
- **Process groups, both directions.** Killing the process left
  `git-remote-https` holding the pipe (a 30 s hang); a timeout was handled and
  Ctrl-C was not. Kill the group on `BaseException` too, and drain stderr
  with a cap.
- **"Rejected, so say it" needs a central place.** Seven refusals logged nothing
  because each raised from a different helper. One wrapper around everything
  before the hand-over logs them; the caller's own `with` body is outside it.
- **Two surfaces, two wordings.** The CLI settled "option has no effect" against
  the random checkout path, the library against the URL. A parity test
  across library, `generate()` and both CLI commands found it only because it
  compared warnings as well as the SBOM.

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
  missing-database test matched `database: not found:`; licenseid's `no home
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
