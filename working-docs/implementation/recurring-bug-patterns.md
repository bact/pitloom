---
Created: 2026-09-17
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Recurring bug patterns

See also: [CLAUDE.md](../../CLAUDE.md) ("Recurring bug patterns" section --
short summary list; this doc holds the full detail),
[recurring-bug-patterns-platform.md](recurring-bug-patterns-platform.md)
(the same kind of list for platform, concurrency, test-harness and CI
traps -- this file keeps the data-and-semantics ones).

General-purpose failure modes that have recurred across more than one
subsystem -- worth checking for by name in any code that resembles the
shape described, not just the module where each was first found.

- **`None` vs `[]`/`{}` (empty-but-present) is a distinct signal, not two
  spellings of the same thing.** In a cascade/fallback/gap-fill chain,
  `None` (or "absent key") means "this source doesn't apply here, try
  the next one"; an empty-but-real container means "this source is
  valid and authoritative, with zero results -- stop looking." Confusing
  them has recurred in unrelated places: a truthiness check
  (`if some_list:`) used where "was a result produced at all" was
  needed, silently colliding two cases that should stay distinct; a
  `dict.get(key, [])`-style default that treated "key legitimately
  absent" the same as "key present with an empty value"; a source-
  priority cascade that couldn't tell "this source is real but empty"
  from "this source doesn't apply." Before writing `x or default`,
  `dict.get(key, [])`, or `if some_container:`, ask whether the empty
  case and the absent case are supposed to behave the same -- they
  usually aren't.
  - **Same bug, provenance-flavoured: gate a "was this field explicitly
    declared" check on presence of the raw source key, never on the
    resolved value's truthiness.** A metadata producer building a
    `provenance` dict for a container field (`keywords`, `urls`,
    `dependencies`, `authors`, `license_files`, ...) with `if parsed_value:
    provenance["field"] = ...` silently fails to record provenance for an
    explicitly-declared-but-empty value (`dependencies = []`,
    `install_requires =`) -- indistinguishable downstream from the field
    never having been mentioned at all. This recurred independently across
    five separate `ProjectMetadata` producers in one PR
    (`project/pyproject.py`, `project/setuptools_py.py`, `project/setuptools_cfg.py`,
    `project/poetry.py`, `project/hatchling.py`) before all five were fixed to check
    presence in the raw source (`"key" in raw_dict`/`kwargs`/`core.config`)
    instead. When adding a new container field or a new metadata producer,
    grep every existing producer's `provenance[...]` assignments for the
    same field and match whichever check style they already settled on.
  - **The presence signal must survive every merge/inheritance boundary,
    or the fix is cosmetic.** `merge_project_metadata()` only treats a
    falsy value (empty container **or** `None`/other falsy scalar) as
    authoritative when *its own* provenance key says so -- so a producer
    that resolves the presence check correctly but is never checked
    against real merge call sites can still lose the signal in practice.
    The same masking happens one layer down: `configparser`'s `[DEFAULT]`-
    section value inheritance makes `"key" in cfg.items(section)` true even
    when *that section* never declared `key` -- a presence check must
    read the section's own keys only (not the merged view) or a shared
    default gets misread as an explicit per-section declaration. And an
    upstream resolver that silently collapses "couldn't fully resolve" to
    the same empty container as "genuinely empty" (e.g. an AST list
    literal with one unresolvable element silently dropping just that
    element instead of invalidating the whole literal) reintroduces the
    exact ambiguity a presence check downstream is trying to eliminate --
    propagate "unresolvable" as its own outcome, distinct from both
    "absent" and "empty".
  - **The provenance dict's tri-state signal isn't container-specific --
    it's the same rule for a scalar that can legitimately resolve to
    `None`.** `merge_project_metadata()`'s "was this explicitly declared"
    check special-cased `primary_value is None` unconditionally, so no
    scalar field's `None` could ever be protected as a deliberate answer,
    only an absent one -- even when its own producer had confirmed
    provenance for it. Three producers worked around this instead of
    fixing it: `project/poetry.py`'s `python = "*"` (Poetry's "explicitly no
    constraint" convention), `project/setuptools_cfg.py`'s `python_requires =`,
    and `project/setuptools_py.py`'s `python_requires=""` all truthy-gated their
    own `provenance["requires_python"]` write -- correctly avoiding a
    provenance/value mismatch (claiming "declared" for a field the merge
    would then silently overwrite anyway), but at the cost of that field
    never being protected against a lower-priority source's real,
    possibly wrong, constraint. A producer that gates a scalar's
    provenance on the *resolved value's truthiness* rather than the *raw
    source key's presence* is treating a symptom of an asymmetric merge
    condition, not a genuine ambiguity in its own data -- the fix belongs
    in the shared merge function once, so every field type (present or
    future, scalar or container) gets the same rule, not a per-producer
    workaround that has to be independently rediscovered next time.
  - **A None-collapse fix applied to one field in a same-shaped set
    commonly misses its siblings -- grep the whole set, not just the
    field that triggered the bug report.** `extract/project/installed.py`'s
    parser handles `requires_python`/`license_name`/`version` with
    near-identical `if field_declared(...): metadata.x = msg.get(...) or
    None` blocks, all three in `_CONFLICT_CHECKED_FIELDS` and needing the
    same collapse (their reconciler compares via `SpecifierSet`/
    `normalize_license_expression`/`is_same_version`, none of which
    tolerate the raw uncollapsed value consistently). A fix for
    `requires_python`+`license_name` shipped without `version`, and it
    took two independent full-PR review passes (not the pass that made
    the original fix) to catch the gap. When a None-vs-empty fix lands
    on one field, immediately check every other field in the same
    frozenset/dict/match-arm for the identical pattern in the same
    change, rather than relying on a later review round to notice.
- **Compare domain identifiers the way the ecosystem/spec does, not as
  raw strings.** A raw `==`/dict-key comparison silently fails to match
  values that a spec treats as equivalent (e.g. PEP 503 package-name
  canonicalization: case-fold, `-`/`_`/`.` treated as interchangeable).
  Whenever two identifiers of the same kind are compared or one is used
  as a dict key, canonicalize both sides first per the format/spec that
  defines them, rather than assuming byte-for-byte equality is enough.
  - **Version equality is PEP 440, never SemVer, and the two must not be
    conflated in an explanation or a docstring.** Pitloom's own
    `is_same_version()` compares two version strings via
    `packaging.version.Version` equality: `"1.0"` == `"1.0.0"` ==
    `"1.0.0.0"` (trailing-zero-padded normalization), a fixed, narrow
    notion of "the same release" -- not "the latest release compatible
    with 1.0" and not a caret/tilde-style range (`^1.0.0` accepting
    `1.0.1`). The two are easy to blur in prose (a reader's SemVer
    intuition reads "same version" as "compatible version"), so an
    explanation of a version-equality check must say "PEP 440 equality",
    not bare "same version", and must not describe it in range/
    compatibility terms. See "Version comparison: PEP 440, not SemVer"
    in `docs/dependency-sources.md` for the user-facing version of this
    same distinction.
  - **The same PEP 440-not-raw-string rule applies to detecting version
    *conflicts*, not just equality checks in prose.** A duplicate-name
    entry across a lock file's own `[[package]]` list (the same
    canonical name appearing more than once, e.g. once per marker
    branch) needs `is_same_version()` before being treated as a real
    conflict -- `"1.0"` and `"1.0.0"` from two different branches are the
    same release, not a conflict to warn about and drop. A sibling that
    skips this check (comparing the raw version strings, or dropping
    every duplicate name outright regardless of whether the versions
    agree) both over-warns on non-conflicts and under-reports a real,
    agreeing dependency that every other sibling format would have kept.
- **A private third-party API (`obj._attr`) does not owe you any
  structural guarantee beyond what it happens to return today.** E.g.
  `packaging.markers.Marker()._markers` does not pre-group same-
  precedence-level boolean terms -- an unparenthesized `A or B and C`
  parses to the flat list `[A, 'or', B, 'and', C]`, and the spec's real
  precedence has to be reconstructed by the caller, not assumed from the
  shape of the list. When consuming a private/internal structure,
  verify its actual shape interactively before writing logic that folds
  over it, and prefer mirroring that same library's own *public*
  algorithm for the equivalent operation over inventing a new one.
- **Warning/error/log wording drifts across sibling modules that perform
  the same kind of check.** When several modules of the same family
  (e.g. one per supported file format) each need to warn about the same
  handful of malformed-input shapes, factor the shared message into one
  helper/constant and have every sibling call it, instead of hand-
  rolling a similarly-worded message per module. When adding a new check
  to one sibling, check whether the others need the identical check
  too.
- **A decode/parse helper that only catches the format-specific
  exception can still crash on a lower-level encoding failure.**
  `tomllib`/`tomli`, `json`, and text-mode `open(..., encoding="utf-8")`
  all raise a bare `UnicodeDecodeError` for invalid bytes -- separate
  from `TOMLDecodeError`/`json.JSONDecodeError`. A "load and gracefully
  degrade on bad input" helper needs to catch the encoding-level
  exception alongside the format-level one, or a bad-encoding file
  crashes instead of degrading like every other malformed-input case.
- **A doc/docstring claim about "how this mechanism decides" needs to be
  re-verified against the actual code before being trusted or restated**
  (see the `physical_path`/`distribution_path` and "how surface X does
  Y" rules in CLAUDE.md -- the same failure mode recurs in any doc
  describing a cascade, fallback, or precedence order: re-read the
  current implementation before repeating or extending a prior
  description of its behavior, rather than assuming an existing doc
  still matches it).
- **Picking one candidate from an unordered collection needs an explicit,
  stable tie-break whenever the result must be deterministic** (see "SBOM
  output" in CLAUDE.md). `{u.get("packagetype"): u for u in urls}`-style
  dict-comprehension overwrite, or "first item in a list", silently makes
  the choice depend on whatever order an external API/dict/set happens to
  produce -- not a contract Pitloom controls. Sort candidates by a stable
  key (filename, name, version) before picking one; never rely on
  insertion/iteration order as the tie-break.
- **Reusing a helper outside the contract it was actually built for
  silently narrows behavior.** A helper written for one caller's specific
  shape (`single_exact_pin()`: a lock file's `version` field, which is
  always *exactly one* PEP 440 specifier clause) can look like a
  reasonable fit for a superficially similar but looser case (a general
  PEP 508 dependency string, which may legally combine an exact `==`
  clause with another, non-conflicting clause, e.g. `foo==1.0,!=1.0.dev0`)
  -- and silently reject valid input the narrower helper was never asked
  to handle. Before reusing a helper in a new call site, check its
  docstring's stated preconditions against what the new call site can
  actually receive, not just whether the return type matches.
- **A dedup/conflict-exclusion fix must check every path that can produce
  an entry for the same identity, not just the path the original bug was
  in.** A fix that partitions input into "the bucket the bug lived in"
  (now correctly deduplicated) and "everything else, passed through
  unfiltered" can silently reintroduce the exact double-emission bug it
  was meant to fix, via the passthrough bucket, the moment the same
  identity (e.g. a canonicalized package name) can appear in *both*
  buckets. After adding conflict-exclusion logic for one shape of
  duplicate, ask whether the same identity could also reach the output
  through an entirely different, unfiltered code path.
- **A test fixture/mock that models an external system's shape must be
  updated in lockstep with what the production code under test actually
  inspects.** A duck-typed stand-in (e.g. a fake Hatchling `core.config`)
  that only populates the one field an earlier version of the code
  happened to check gives false confidence once the code is fixed to
  check more fields the same way -- the fixture still returns all-green
  because it was never asked to model the new field, not because the fix
  is correct. When broadening a check across several fields, broaden the
  fixture that backs its tests across the same fields in the same change,
  or the new branches go untested despite "the tests pass."
- **A source that can legitimately resolve to zero entries needs its own
  "is this genuinely a file of this format" check, or an empty result
  becomes indistinguishable from a wrong file.** In a priority cascade
  (e.g. `lock/cascade.py` picking among `poetry.lock`/`pdm.lock`/
  `pylock.toml`/`uv.lock`/`Pipfile.lock`/`requirements.txt`), a resolver
  that genuinely produces zero packages must still look different from an
  unrelated/truncated/hand-edited file that merely happens to be found
  under that format's filename -- otherwise the latter silently wins the
  cascade over a real, lower-priority lock file via a spurious
  authoritative-empty result. Check for the format's own identifying
  top-level marker (`poetry.lock`'s string `metadata.lock-version`,
  `pdm.lock`'s string `metadata.lock_version`, `Pipfile.lock`'s int
  `_meta.pipfile-spec`, `uv.lock`'s flat int `version`) before trusting an
  empty package list as real, not just when it's non-empty. This was
  missed for `uv.lock` well after the identical check had already been
  added to three sibling formats -- when a new source joins an existing
  cascade/fallback family, check whether it needs the same class of guard
  every existing sibling already has, not just the guards relevant to
  the bug that prompted adding the new source.
- **A presence-only check (`find_first_present_key()`-style: "is any of
  these keys present at all") silently misfires the moment one key in
  the set is genuinely boolean-valued instead of presence-implies-true.**
  `Pipfile.lock`'s non-registry-source keys are almost all presence-only
  (a `"git"` (also `hg`/`bzr`/`svn`), `"path"` or `"file"` string means
  "non-registry, full stop"),
  but `"editable"` is schema-legal as an explicit `false` -- a naive
  presence check would misread `"editable": false` as "editable source,
  exclude" instead of "not editable, no exemption needed here." Before
  reusing a presence-only helper across a whole key set, check each key's
  real schema: a key that can legitimately carry a meaningful `false` (or
  any other falsy-but-real value) needs its own value check, not just a
  presence check, even when every other key in the same set is fine with
  presence alone.
- **An opt-out flag that makes a helper skip populating an accumulator
  list breaks any pre-existing emptiness/exit check still keyed off
  that same list.** A check like `if not <accumulator>: return <empty>`
  implicitly assumes the accumulator is populated 1:1 with real work
  done on every call -- once a flag makes population conditional (e.g.
  a per-file hash list only appended to when hashing isn't skipped),
  the check fires unconditionally whenever the flag is set, discarding
  every real result instead of only a genuinely empty one. Caught in
  `get_wheel_files()`'s `skip_merkle_root` option (PR #213) before
  merge: `if not file_entries: return None, []` had to become
  `if not project_files: return None, []`, re-keyed to the list still
  populated regardless of the flag. When adding an opt-out that skips
  populating an existing accumulator, grep every downstream emptiness/
  length check on that accumulator in the same function and re-derive
  it from a proxy that's still unconditionally populated.
- **Removing a read/computation to save cost can silently remove an
  error-surfacing side effect that read was also providing.** A full
  `read_bytes()`/similar call kept only for its return value may also
  be the one thing raising `PermissionError`/`OSError` for an
  inaccessible file, caught by a broad outer `except` that degrades the
  whole operation loudly and safely. Skipping the read because the
  return value is no longer needed (e.g. hashing turned off) removes
  that detection too, turning a loud whole-operation failure into a
  silently-wrong per-item result instead. Caught in the same
  `skip_merkle_root` option (PR #213): the full read was replaced with
  a cheap access probe (`with source.open("rb"): pass`) that still
  triggers the same failure path without paying for the read. When an
  optimization removes a read/computation, check whether anything
  downstream (an outer `except`, a caller's fail-loud contract) was
  implicitly relying on that operation's failure mode, not just its
  return value.
- **A guard added for one direction of a symmetric hazard often leaves
  the mirror direction open.** `_DiscoveryLock`'s (PR #215)
  reentrancy guard was first added only to `write()` (same-thread
  write-then-write re-acquisition), which reads like the complete fix --
  but the identical deadlock is equally reachable via write-then-read (a
  thread holding the write lock calling back into discovery through a
  *reader* backend, actually the more common path since three of four
  registered backends are readers). Only caught by a follow-up review
  that empirically reproduced the write-then-read hang with a live,
  timeout-bounded repro script, not by re-reading the code. When adding
  a guard for one specific interaction of a shared resource (a lock's
  two acquisition modes, a cascade's two directions, a cache's read vs.
  invalidate path), explicitly enumerate every symmetric interaction
  before considering the fix complete -- for a concurrency/reentrancy
  claim specifically, write a minimal `threading.Event`/timeout-bounded
  repro (`done.wait(timeout=N)`) before and after the fix; it's faster
  and more convincing than static reasoning, and doubles as the shape
  for the regression test.
- **A log message inside a function with multiple exit branches must
  describe what that branch actually did, not the function's typical
  behavior.** `_discover_with_no_static_module()` (PR #215)
  unconditionally logged `"...using Hatchling-based heuristic, file
  list may be inaccurate"` even on the branch that returns `[]` without
  ever invoking Hatchling (no `[project]` table present) -- true only of
  the function's *other* exit branch. When a function gains a new
  early-return branch, re-check every log call that executes before it
  reads correctly on that new branch too, not just the branch that
  motivated adding the log call originally.
- **A shared helper's return type should match what every caller needs,
  not force each one to re-narrow it.** `_resolve_bool_cascade()` (PR
  #215) initially returned `bool | None` -- correct given one input can
  itself be `None` -- which pushed a `bool(...)` wrap onto all 4 of its
  call sites, exactly the per-call-site repetition the helper was
  extracted to eliminate. Fixed by having the helper return `bool`
  directly. When extracting a helper specifically to deduplicate a
  pattern, check whether every caller ends up coercing its return value
  the same way -- if so, that coercion belongs inside the helper.
- **Reaching into another module's leading-underscore (module-private)
  name from outside that module is a maintenance trap even when it
  currently works.** `extract/project/_installed_reconcile.py` (PR
  #215) imported `core.project._PROVENANCE_KEY_ALIASES` directly across
  the module boundary; nothing stopped `core.project` from
  restructuring that internal detail later, silently breaking a
  consumer the underscore convention implied didn't exist. Fixed by
  adding a small public wrapper (`provenance_key_for()`) next to the
  private data, called by both the defining module and the external
  consumer. When a genuine cross-module dependency exists on a private
  name, promote a narrow accessor function rather than importing the
  private name itself.
- **A circular-import claim needs a live interpreter test, not static
  reasoning about import order.** A review agent flagged
  `assemble/__init__.py`'s `from pitloom.extract.project import
  warn_use_lockfile_no_effect` as "only avoiding a real circular-import
  `ImportError` by luck of ordering" -- plausible from reading the
  import graph alone (`extract.project` -> `extract._locked_dependencies`
  -> `assemble.spdx3._provenance_encoders`, which forces
  `assemble/__init__.py` to execute). Tracing it statically is error-prone:
  what actually settles it is that `assemble/__init__.py`'s *own* earlier
  import (`_generators` -> `_model_generator` -> `assemble.spdx3.document`,
  several lines above the flagged import) already fully loads
  `extract.project` before the flagged line runs -- deterministic
  same-file ordering, not luck. Confirmed by running
  `python -c "import pitloom.extract.project; import pitloom.assemble"`
  (and the reverse order) directly rather than re-deriving the import
  graph by eye. Before accepting or reporting a circular-import
  fragility finding, run the actual import in a fresh interpreter (both
  orders) -- it's faster and more conclusive than manually tracing which
  module's `__init__.py` reaches which line first.
