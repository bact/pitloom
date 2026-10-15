---
Created: 2026-10-15
Last-Modified: 2026-10-15
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Lock/pin cascade: per-format extraction and shared code

See also:

- [The cascade][main] (priority order, wiring, provenance)
- [Opt-out][opt] (`--no-use-lockfile`)

[main]: lock-file-cascade.md
[opt]: lock-file-cascade-opt-out.md

## Per-format extraction notes

Most formats' extractors are a simple flat scan (`pylock.py`,
`poetry.py`): every locked entry is either included or excluded,
independently of the others. `uv.py` is the one exception so far,
because `uv.lock` resolves *every* Python-version/platform combination
its `resolution-markers` cover in one file -- its top-level `[[package]]`
table is a flat union across all of them, so the same package name can
legitimately appear more than once, at different versions, restricted
to different marker conditions (e.g. one entry for
`python_full_version < '3.10'`, another for `>= '3.10'`). Since this
cascade (like every sibling extractor) doesn't evaluate markers against
a real environment, `uv.py`:

1. Identifies the project's own package entry (via a `source.editable`/
   `source.virtual` marker -- how uv distinguishes "this is the local
   project" from a PyPI download) instead of scanning every
   `[[package]]` entry directly.
2. Breadth-first walks the dependency graph starting from that entry's
   own `dependencies` list (main/runtime only -- the *root* package's
   own `optional-dependencies` and `dev-dependencies` groups are the
   project's own extras/dev groups, excluded the same way `poetry.lock`'s
   non-main groups are; since #300 the extras' direct requirements get
   their pins in a separate pass, `extract/lock/_extra_pins.py`).
3. If a dependency appears more than once in that reachable subgraph,
   compares their versions: if they agree (PEP 440), collapses them to
   one entry; if they disagree, skips the package with a `WARNING:`
   explaining that resolving marker conditionals requires environment
   information Pitloom doesn't have.

This means a project depending on `foo` whose lock file specifies `foo==1.0`
for Python 3.10 and `foo==2.0` for Python 3.11 won't get a silent guess --
`foo` is omitted with an explicit `WARNING:` naming the package and how many
versions were found, rather than choosing one at random or emitting both as
conflicting pins. Real-world confirmation: `urllib3` (which locks both
`urllib3-future` and other conditional dependencies across Python versions)
exercised this path cleanly during fixture validation.

A future format that shares this same "multiple resolutions in one
file" shape should follow this same pattern rather than inventing a new
one.

`pdm.py` hits a *milder* version of the same "same name, more than
one entry" shape, but for a different, harmless reason: PDM records a
separate `[[package]]` entry per requested extra variant of a package
(e.g. a bare `httpx` entry alongside one with `extras = ["socks"]`),
always agreeing on `version` -- unlike `uv.lock`'s genuinely conflicting
duplicates. It uses `group_versions_by_canonical_name()` (see "Sharing
code across formats" below) to group its `(name, version)` pairs by
PEP 503-canonicalized name, then only treats a name as ambiguous (skip,
`WARNING:`) when its entries actually *disagree* on `version`; entries
that agree are collapsed to one `name==version`, not two.

`pipfile.py` is the one format in the cascade that's **JSON, not
TOML** -- `pitloom.extract.lock._common.load_lock_json()` is its
counterpart to `load_lock_toml()`, same absent/malformed-file contract.
Its `version` field is also shaped differently from every sibling
format: a full PEP 440 specifier string (typically `"==2.31.0"`, since
`pipenv lock` always resolves to an exact pin) rather than a bare
version number, so the extractor parses it with
`packaging.specifiers.SpecifierSet` and requires exactly one `==`
specifier -- anything looser (a range, an excluded-version specifier, or
an unparseable string) is skipped with a `WARNING:`, the same
"don't guess" policy as `uv.lock`'s marker-ambiguity skip. It has no
`groups`-style per-package tag the way `poetry.lock`/`pdm.lock` do;
instead the whole top level splits into `"default"` (included) and
`"develop"` (excluded) sections.

`requirements.py` is the one format that isn't a real lock file at
all -- a `requirements.txt` is just lines a human or `pip freeze` wrote,
with no resolver metadata guaranteed. Its policy is **all-or-nothing**:
every real dependency line must already be a single exact `==` pin, or
the *entire file* is ignored with one `WARNING:` naming the first
disqualifying line (an option line like `-e`/`-r`/`--hash`, an unpinned
or ranged specifier, or a malformed line) -- never partially included,
since a subset of a `requirements.txt` carries no more confidence than
the subset itself would on its own. This is why it's ranked lowest and
tagged `"pinned_requirements"` rather than `"resolved_lockfile"` (see
[the cascade](lock-file-cascade.md#the-cascade)). Unlike `pdm.lock`/`uv.lock`,
there's no `[[package]]`-style
table to group by name -- so the extractor collects every line's
`(name, version)` pair first, then feeds them to the same
`group_versions_by_canonical_name()` helper `pdm.py` uses, once
all lines have parsed: a name repeating with agreeing versions
collapses to one entry, a genuine conflict rejects the whole file. The
grouping compares PEP 503-canonicalized names, not the literal spelling
on each line -- a hand-written file mixing `Flask==1.0` and
`flask==2.0` is a real conflict between two spellings of one PyPI
package, not two different packages.

Two pip file-format quirks are handled before per-line parsing, both
matching pip's own preprocessing: a leading UTF-8 BOM (`encoding=
"utf-8-sig"` instead of `"utf-8"`) and backslash line-continuation
(`_join_continuation_lines()` merges a physical line ending in `\` with
the next before splitting on `#`). Continuation-joining doesn't extend
to `pip-compile --generate-hashes` output specifically -- a joined line
still carries `--hash=...` tokens, which aren't valid PEP 508 syntax
and correctly disqualify the file the same as any other malformed
line, just for that reason instead of failing on the raw backslash.

**A URL-based requirement line (`name @ https://...`, or the legacy
`git+https://...#egg=name` pip also accepts) always disqualifies, even
one that looks like it points at a tagged release** (e.g.
`.../archive/refs/tags/v2.31.0.zip`). This was an explicit design
question, not an oversight: PEP 508 defines a URL requirement as a
*direct reference*, a wholly separate concept from a PEP 440 version
specifier -- neither spec defines how to derive a normalized version
from a URL. A git tag or filename that merely looks version-shaped is
an arbitrary string the maintainer chose, with no guarantee it
round-trips to a real PEP 440 version (capitalization, a leading `v`,
a non-version tag like `stable`, ...). Confirming the real version
would mean fetching the URL and inspecting the installed package's own
metadata -- against this repo's "prevent excessive network access"
principle -- and every sibling lock format already skips its own
VCS/path/URL-sourced entries the same way, never guessing from context.
So this format doesn't special-case a release-shaped URL either.
`packaging.requirements.Requirement.url` being non-`None` catches the
PEP 508 `name @ url` form directly; the legacy `git+...`/bare-URL forms
pip also accepts aren't valid PEP 508 at all, so `Requirement()` itself
raises `InvalidRequirement` for them -- caught the same way as any other
malformed line, still disqualifying, just via a different message.

## Sharing code across formats (`_common.py`)

Two steps turned out to be identical across every extractor, not just
similar in spirit:

- **Loading the lock file.** "Try to read/parse it; absent -> empty
  result, silently; malformed -> empty result, with a `WARNING:`" was
  factored into `pitloom.extract.lock._common.load_lock_toml()`, which every
  TOML-based format extractor uses (`poetry.py`, `pylock.py`,
  `uv.py`, `pdm.py`). `pipfile.py` (JSON, not TOML)
  needed the same contract but couldn't reuse a TOML-specific parser, so
  it's `load_lock_json()` beside it -- same absent/malformed-file
  behaviour (including rejecting a non-object JSON top level with a
  `WARNING:`, the one shape TOML's grammar rules out for
  `load_lock_toml()` but JSON doesn't), different underlying
  `json`/`tomllib` call.
- **Grouping a flat package list by name.** `uv.py`'s ambiguity
  check groups full `[[package]]` table entries by their raw `name`
  field -- `pitloom.extract.lock._common.index_packages_by_name()`.
  Every format whose conflict check only needs a `(name, version)`
  pair grouped by *canonicalized* name (`Flask`/`flask` must count as
  the same package) uses
  `pitloom.extract.lock._common.group_versions_by_canonical_name()`
  instead: `poetry.py`, `pdm.py`, and `pylock.py`.
  `pipfile.py` and `requirements.py` need the pin's operator
  (`==` vs `===`) to survive grouping too, since their `version` field
  is a full specifier rather than a bare version number (see below) --
  they use the `(name, operator, version)` sibling,
  `pitloom.extract.lock._common.group_pin_triples_by_canonical_name()`.
  Every one of these groupings compares versions with
  `pitloom.extract.lock._common.is_same_version()` (PEP 440 equality,
  e.g. `"1.0"` == `"1.0.0"`), not raw string equality, so two spellings
  of the same release never trigger a false-positive conflict warning.
- **Validating a `version` field is a usable PEP 440 version.**
  `pitloom.extract.lock._common.is_usable_version()` checks a field is a
  non-empty string *and* parses as a valid `packaging.version.Version`
  -- rejecting not just non-strings but a syntactically-string-yet-not-a-
  version value too (a wildcard like `"*"`, whitespace, arbitrary text),
  which a bare non-empty-string check would let through into an invalid
  `name==<garbage>` pin. Shared by `poetry.py`, `pylock.py`,
  `uv.py`, and `pdm.py`, whose `version` fields are plain
  version numbers. `pipfile.py` does **not** use it: its own
  `version` field is already a full PEP 440 *specifier* string (e.g.
  `"==2.31.0"`), not a bare version, so it does its own
  `isinstance`/non-empty check directly before parsing that specifier
  with `packaging.specifiers.SpecifierSet` and `single_exact_pin()`.
- **The non-registry-source `WARNING:` message.** `"Skipping <lock
  file> entry %r: %s-sourced dependencies cannot be represented as a
  PEP 508 specifier"` is shared across all five extractors that have
  this concept (every format except `requirements.txt`, whose URL check
  is shaped differently -- see above) via
  `pitloom.extract.lock._common.warn_non_registry_source(lock_file,
  name, source_key)`. Each extractor still does its own lookup of
  *which* key triggered it (see below) and only calls this once it has
  the answer.
- **Judging whether a specifier is a single exact `==`/`===` pin.**
  `pipfile.py` and `requirements.py` both need this --
  Pipfile.lock's `version` field and a `requirements.txt` line's
  specifier are both full PEP 440 specifier strings, not bare version
  numbers the way every TOML-based format's `version` field is. Lives
  as `pitloom.extract.lock._common.single_exact_pin(specifier_set)`,
  taking an already-built `SpecifierSet` rather than a raw string --
  each caller parses the raw string itself (`SpecifierSet(...)` for
  Pipfile.lock, `Requirement(...).specifier` for `requirements.txt`)
  and catches its own parse failure with its own `WARNING:` wording,
  since the two call sites want different messages for "unparseable" vs.
  "parseable but not a single exact pin." Returns `(operator, version)`,
  not just `version` -- `===` (PEP 440 arbitrary-equality, for a legacy
  version string that doesn't parse as a normal `Version` at all) is as
  valid a single exact pin as `==`, and the caller needs the operator
  back to format `f"{name}{operator}{version}"` rather than assuming
  `==`.

What's deliberately **not** shared: the per-entry lookup for which key
marks a non-registry source, and what the `groups`/`dependencies`
filtering looks like. Each format's own field names and conventions
differ enough (`poetry.lock`'s `source.type` vs `pylock.toml`'s
top-level `vcs`/`directory`/`archive` keys vs `uv.lock`'s nested
`source.{key}` vs `pdm.lock`'s flat `git`/`path` keys) that forcing one
shared function across all of them
would hurt clarity more than it would save -- consistent *wording*
across their `WARNING:` messages matters more here than a single shared
implementation, per this repo's message-style convention.
