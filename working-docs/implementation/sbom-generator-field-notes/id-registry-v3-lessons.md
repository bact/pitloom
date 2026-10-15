---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: a typed, content-gated id registry (registry v3)

See also: [README.md](README.md) (index of these notes),
[identity-and-archives.md](identity-and-archives.md) section 3 (the
registry bugs v3 answers),
[process-lessons.md](process-lessons.md) (review rounds and test tiers),
[id-registry-v3.md](../id-registry-v3.md) (the design; D-numbers
below refer to it),
[id-registry-followups.md](../../design/id-registry-followups.md) (what v3
left open).

Lessons from building registry v3: one table keyed by `(type, name)`, a
sha256 recorded per entry, the content gate chosen by each lookup, loom
datasets as packages, and a loom run that resolves its models at exit. The
work was nine commits (0b to 7b), not merged at the time of writing
(2026-10-15). Each item gives the evidence and one "Do:" rule. Open
problems found on the way are in the follow-ups doc, not here.

## 1. Identity design

- **A classifier that guesses a table from an element's shape misfiles.**
  Harvest used to decide from the element's shape which table it belonged
  to, and a hashed `AIPackage` and a hashed `DatasetPackage` looked alike.
  The fix was to stop classifying: harvest records `(compact type, name)`
  with an optional sha256, each lookup chooses its own gate (content must
  match, or not), and ids carry their type (`AIPackage-`, `DatasetPackage-`)
  so one type's table can never hand out another's id.
  Do: let the side that knows the requirement (the lookup) decide it; make
  the recorded data typed enough that tables cannot cross.
- **A content-gated identity makes "retrained" a different model.** Once an
  entry holds a sha256, a changed file gets a new id and one `INFO:`. A
  model with no single hashable file (sharded directory, remote, no `path=`)
  falls back to a name-only entry. The gate has a seam: lookups that stay
  ungated (project, wheel, embed, D16) return the old id after a retrain,
  and harvest (D15) then writes `(name, new sha)` under the OLD id, so a
  later gated lookup of the new bytes lands on the old id: retrains laundered
  into old ids. Latent while those surfaces do not hash AIPackages.
  Do: when a gate is added to one lookup, list every other lookup and every
  writer of the same key, and gate them in the same change.
- **A Merkle leaf must bind the path.** Content-only leaves keep the root
  unchanged when a file is renamed and give the same root for two
  permutations of the same files. The leaf is `sha256(relpath + NUL +
  raw digest)`; NUL is unambiguous because no path contains one. A
  one-file directory's root must also differ from that file's own digest, or
  a directory dataset and a file dataset hash-merge. Both hold with the path
  in the leaf (`core/dataset_hash.py`).
  Do: put what identifies a member (its path) inside what is hashed, with a
  separator the member cannot contain.
- **Key a file lexically first, then by realpath, then by file identity.**
  An in-project symlink keys where it is declared (as `id generate` keys
  it); a path that aliases the project from outside is found by realpath; a
  case-insensitive file system, where the on-disk case and the caller's
  differ, needs a `(st_dev, st_ino)` ancestor match (`st_ino == 0` is no
  identity). On macOS `/tmp` is `/private/tmp`, so a textual prefix test
  alone misses (`id_registry/resolve.py`, `registry_key_for_path`).
  Do: try the cheap lexical match, then the resolved one, then identity,
  and test the macOS and case-insensitive shapes.

## 2. Hashing and safe writes

- **A size check before reading is not enough.** A file can grow after
  `stat()`. The dataset ceiling is a budget over the whole directory: each
  read stops at what is left, and the budget shrinks by the bytes already
  read, not by the sizes stat() reported. Mutation testing found the missing
  shrink only with a two-file case; a one-file test passes either way.
  Do: bound every read by the remaining budget, and write the multi-file
  case that makes "remaining" differ from "total".
- **A lock-free shared registry only narrows the race.** Re-reading the file
  just before minting shrinks the duplicate-id window. Refusing at save time
  a new id whose key another run already saved (`WARNING: another run
  saved ...`) keeps the registry at one key per id. It does not make the
  claim "a lost update is never a wrong id" true: two simultaneous exits can
  already have written the same id for different models into their
  fragments.
  Do: state the guarantee for the file, not for the outputs written from it
  earlier.
- **Atomic temp-file plus `os.replace` changes more than atomicity.** The
  temp file from `mkstemp` is mode 0o600, so the original mode was silently
  lost; and `os.replace` over a symlink replaces the link with a plain file.
  `replace_text_lf` copies the mode and resolves the symlink first. It also
  now succeeds on a `chmod 444` registry, where the old in-place save
  failed, and fails on Windows while another process has the file open.
  Do: when replacing a file atomically, carry over mode and symlink
  identity, and decide each platform's behaviour on a protected or open
  target.

## 3. Deferring work to run exit

- **Defer resolution but keep the bytes identical.** Loom resolves models at
  run exit (D13) so the sha256 and the registry are known first. Ids are
  counters per document (`#Annotation-N` is shared with datasets), so
  replaying the calls in another order changes the ids. The working shape:
  build the provenance at the call, bind only the subject (the model) later,
  and replace a provisional `urn` id at exit. Check with a pinned UUID and a
  byte comparison of the old and new output.
  Do: when a deferral reorders work, prove equality of the output bytes, not
  of the object graph.

## 4. Harvest churn

- **Recording a sha on a dependency `Package` made the registry flip.**
  Alternating `project` and `wheel` runs recorded the lock-file sha in one
  and the PyPI sha (or none) in the other, so the entry changed and the
  registry was rewritten each run. Ruling (2026-10-14): harvest never erases
  a recorded sha; an unhashed element keeps the entry's hash and a hashed
  one replaces it. A guard test (the third run's bytes equal the second's)
  cannot see a rewrite of identical content; it needed a spy on the save
  call.
  Do: test "no write" with a call spy, not with a byte comparison.

## 5. Process

- **Re-verify a design's anchors before coding.** The v3 design was written
  against `main` at 4c052dd and re-checked 203 commits later: line anchors
  and locations had drifted (checks 16 to 19 of the manual CLI runner had
  been taken; `_sync_registry` had moved package), while the invariants
  held. The design cites line numbers in several places.
  Do: treat line anchors as hints; re-find each by name before relying on
  it.
- **A hard text budget limits discoverability.** The `sbom-generate`
  description is 1021 of 1024 characters (checked 2026-10-15 by joining the
  folded lines), so each new trigger phrase costs an existing one.
  Do: budget the description at design time; put detail in `references/`.
- **Mutation testing paid off.** About 140 mutants over the commits. The
  survivors led to new tests: the budget not shrinking (section 2), the
  refuse-known-ids alias, and the harvest sha restore. One survivor was
  equivalent: dropping the `add` in the remap changes nothing, because
  references are linked objects. An equivalent mutant is no evidence;
  reinstate the exact pre-fix shape instead.
  Do: classify every survivor as missing test or equivalent mutant before
  writing anything.
- **Parallel agents on disjoint files still collide at the gate.** Agents
  owned separate file sets; each time two sets overlapped there was one
  transient cross-agent test failure. One hand-back left a dead test that
  imported a helper another agent had removed, found only by the full-suite
  gate after all agents stopped. See also
  [process-lessons.md](process-lessons.md).
  Do: name file ownership in each brief, and run the full suite once, after
  the last agent reports.

## 6. What a fresh reviewer found after 12,452 passing tests (PR #305)

Three independent read-only reviewers ran real repros against the live tree
and a `git archive HEAD` copy. They found a dozen defects the author and the
suite had not; each below is a class, with its measured instance.

- **A guard placed before a side effect drops the effect.** An element whose
  name cannot be encoded as UTF-8 (a lone surrogate from a non-UTF-8 file
  name, `\udcff`) was skipped before its id was reserved, so the counter
  passed no number for it and the 7th mint returned the skipped `#File-9`:
  a retired id reused, the invariant the counters table exists to keep.
  Do: reserve first, then guard; assert on the next mint.
- **A name that cannot be encoded freezes the whole registry.** One such key
  made every save raise `UnicodeEncodeError` inside the RFC 8785 key sort,
  so the registry stayed unwritable from then on (the file was never
  corrupted). Do: refuse it at `register()` and at load, skip it in the walk
  with one warning, and log it escaped (`ascii()`), because logging a lone
  surrogate on a UTF-8 stream raises too.
- **A fix scoped to explicit input leaked to implicit input.** "An unreadable
  PATH is an error" was implemented in the walk root, which the default roots
  share: an unreadable `data/` turned a warning-and-continue into exit 1.
  Found only by diffing the CLI against HEAD on a probe corpus. Do: carry an
  `explicit` flag from the argument parser to the one walk.
- **A conflict branch must skip itself, not the cascade.** On a sha256
  conflict between two elements sharing an id, the survivor search returned
  "none" and never tried the content-hash or structural criteria: the same
  changed bytes in two fragments became two elements. Do: skip only the
  by-id fold.
- **A placeholder must be a flag, not a key.** A wheel with no usable
  `.dist-info` is named `unknown`; looked up like a real name, two unrelated
  wheels shared one package id and a junk registry entry. A name test cannot
  decide it (`unknown` is a real PyPI name). The document namespace was seeded
  from the same placeholder, so wheels with identical payload digests shared
  every id; the base file name is now folded into the seed. Do: set an
  explicit `identity_known` in the generator.
- **Prefer the id more fragments share.** With first-seen survivors, the
  sentimentdemo merged wheel SBOM kept run-minted ids for the two processed
  data files and lost the registry's `#File-8`/`#File-9`. A minted id's
  namespace belongs to one fragment; the registry's is shared. Count sources
  per namespace over all fragments before the first merge, keep the earlier on
  a tie; reversed order must give the same ids.
- **`relative_to` keeps `..`.** `generate([Path("../out/o.txt")], root)`
  registered the key `../out/o.txt`. Do: lexical `normpath`, then
  `relative_to`; `realpath` only as the fallback.
- **Count the reviewer, not only the tests.** 12,452 tests and 100% branch
  coverage passed with all of the above present.
  Do: have a reader who did not write the code run adversarial repros, and
  compare against a HEAD archive.
- **One rule, one producer.** Whether a wheel's name was read decides three
  things (registry lookup, harvest, the document uuid seed). The standalone
  wheel and embed routes set the flag, but the embed route that takes a
  project directory built the same document by hand and did not: two wheels
  with different file names got one namespace and a pinned `unknown` id was
  reused. A focused late review found it; 14 tests and 100% coverage had not.
  Do: compute the fields in one helper, and grep every construction of the
  class when adding one.
- **Seed an unidentified artefact with something specific to it.** The
  document namespace was seeded from name, version, dependencies and the
  Merkle root, and the wheel Merkle root covers file digests, not paths, so
  two broken wheels with one payload (`pkg/__init__.py`, same bytes) shared
  every id even with no registry. Adding the archive's base file name to the
  seed only when the name is unknown separates them, leaves every named
  document's bytes unchanged (a pinned uuid proves it) and costs nothing at
  run time. Trade-off stated in the docs: a renamed copy gets new ids.
