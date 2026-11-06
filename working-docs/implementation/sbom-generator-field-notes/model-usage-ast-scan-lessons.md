---
Created: 2026-11-03
Last-Modified: 2026-11-06
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: finding how code uses a model file, from its syntax tree

See also: [README.md](README.md) (index of these notes),
[../ai-model-scan-security-lessons-transparency-and-correctness.md](../ai-model-scan-security-lessons-transparency-and-correctness.md)
(the AI-model half: what a scan may claim),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(caps bound reading, never reporting),
[process-lessons.md](process-lessons.md) (the review rounds and test tiers),
[../model-usage-ast-scan.md](../model-usage-ast-scan.md)
(the design, rules and documented limits) and
[../roadmap-completed.md](../roadmap-completed.md#shipped-in-0221-prs-413-433)
(the shipped item).

PR #413 replaced a substring match ("this `.py` file's text contains
`model.pkl`") with a scan of the Python syntax tree that says how the file uses
the model: read, write, read and write, or unknown. Mentions (a `print`, a log
line, a raised message) give no edge. The work took three review rounds, a
mutation pass and a closing review (commits `0402d6df`, `660d9d8b`,
`c653c96e`, `cf548e57`, `1006cc19`, `3d9947ae`, `a19c1066`), merged on
2026-11-03. PR #432 followed the same day, before the 0.22.1 release (tag
`v0.22.1`, 2026-11-03), and fixed three classes the rounds had not reached: a
parser crash, quadratic time and a message edge (items 10 to 13). The items
below are the non-obvious ones. Each was checked against the code, a live
interpreter or the cited commit on 2026-11-02 to 2026-11-06.

## 1. A path in code is not the file: what the code does decides

- A substring match counts a comment, a docstring and an error message as a
  use. The tree separates them: `open("m.pkl")` reads, `open("m.pkl", "wb")`
  writes, `print("m.pkl")`, `logging.info(...)` and `raise X("m.pkl")` mention.
- **A path written into a string is no longer the path.** `f"{p!r}"` and
  `f"{p:>20}"` render it: whatever then consumes the string, other than a
  mention, is an unknown access, not a read. The scan walks up through the
  f-string to the consumer and marks the access unknown.
- **A data position is not a file position.** In `f.write(path)` and
  `json.dump(path, f)` the path is the text being written. `zf.write(path)`
  reads it. The name alone cannot tell, so these are unknown. `loads` and
  `dumps` build text in memory and are mentions.
- Do: decide the access from the consumer and the argument position, not from
  the callee name alone; when two readings are possible, say unknown.

## 2. Mirror the interpreter's own rules, then probe the interpreter

- `str.format` reads a field made of digits as a position. CPython decides
  "digits" by Unicode decimal digit, not ASCII. On the interpreter used here:
  `"{٣}".format(0, 1, 2, "three")` gives `three`, and `"{²}"` is a
  keyword that raises `KeyError`. The first version tested
  `isascii() and isdigit()`, so the scanner read `{٣}` as a keyword and dropped
  a real match. The fix is `str.isdecimal()`.
- The digits then go through `int()`, which raises `ValueError` past
  `sys.set_int_max_str_digits` (4300 by default). A hostile template with
  thousands of digits must read as "not known", not crash the scan.
- A NUL cannot be in a path, so it is used as the "unknown part" marker inside a
  template, and a string literal that holds one is refused as a path.
- In a `%` dict, an entry with a computed key or `**d` may replace any earlier
  key, so every earlier key is unknown. A later string key sets its value, as
  at run time.
- Do: probe the real interpreter for each rule before writing it, and keep the
  probe as a test (`format_template("{٣}", ...)`).

## 3. Caps fail closed: no edge, not the tail

- An expression deeper than 64 or longer than 4096 characters is not followed.
  An earlier version returned the tail of an over-cap expression, and a tail can
  match a model name that the whole expression never names. The cap now raises
  inside the walk and the entry point returns "no path".
- A cap bounds reading, never what the output claims: an over-cap expression
  gives no edge and no claim about the file.
- Do: when a bound stops a walk, return nothing for the whole expression, not
  the part reached so far.

## 4. A name is a constant only if it is bound once

- A name assigned once in the file counts as a constant, so `B = A + "/x"`
  finds `A`. Every other binder must count against it, or a name that is
  rebound later still looks constant: among others an import, a function or
  class definition, an `except ... as`, a `match` capture (`MatchAs`,
  `MatchStar`), the `**rest` of a mapping pattern (`MatchMapping.rest`), and on
  Python 3.12 or later a type parameter (`TypeVar`, `ParamSpec`,
  `TypeVarTuple`). The last two were missing until review.
- Counted per file, not per scope; constants are read in source order. Both are
  documented limits, not bugs: a wrong guess gives unknown access or no edge,
  never an invented use.
- The type-parameter cases cannot run below 3.12, so they were checked by hand
  on 3.12 and 3.13 and run in CI only on those legs.
- Do: for each construct that can bind a name, add a test where the name is
  bound once by it and once elsewhere.

## 5. Reaching a model through a chain of names: a worklist, not recursion

- `A = "m.pkl"`, `B = A`, `C = B`, `open(C)`: the use of `C` is a use of every
  name it was built from. The reach is a worklist over the names reached,
  linear in the chain (a test builds a long chain and bounds the time
  generously).
- The reach is per model: a constant shared by two models must not carry the
  access of one to the other.
- Two mutants of the worklist (the line that skips names already reached, and
  the line that queues new ones) loop forever on a cycle
  (`A = Path('m.pkl', x=B)`, `B = Path('m.pkl', x=A)`). No test was kept: a
  test that hangs CI is worse than the mutant surviving.

## 6. Mutation testing found a behaviour bug, not only a missing test

- 107 mutants of the second round's changes: 86 killed, 9 equivalent (checked
  one by one), 12 survivors that a test could kill, 2 of those non-terminating.
- One survivor sat on the `isascii() and isdigit()` guard of item 2. Asking why
  the suite did not mind a change there led to the CPython probe, and the guard
  was wrong, not only untested.
- Others showed untested rules: method names are case-insensitive (`f.Write`,
  `json.Dump`), reach does not leak between models, an f-string restarts after a
  NUL piece, and type-parameter bindings.
- Do: after a review round, mutate the lines it changed; a survivor is a
  question about the code first and about the tests second.

## 7. A skipped input is said, not dropped: `.PY`

- Python imports only a file whose name ends in lower-case `.py`; the scan
  follows that. A file named `RUN.PY` was skipped without a word, so a project
  that kept a model script under that name got no usage edge and no hint why.
- Now one `WARNING:` per such file (`usage-unusable`), and only when a model was
  found: with no model there is nothing the script could be attached to, and
  absent data is quiet. The file is still not read.
- The test table is the boundary: `.PY`, `.Py`, `.pY` say; `.pyc`, `.pyw`,
  `.PYI`, a bare `PY` and `.txt` do not.
- Do: when a rule deliberately skips something the user may expect to be
  covered, say so once, in the catalogue, with what to do about it.

## 8. A new catalogued message names the release that first prints it

- `Message.since` defaults to `0.22.0`. The release 0.22.0 was already tagged,
  and `git ls-tree -r v0.22.0 --name-only` showed no `messages/_usage_*`
  module, so `usage-unparseable`, its `/mention` variant and `usage-unusable`
  all first print in 0.22.1. They shipped to review with the default; a
  reader of `docs/message-codes.md` would have been told they existed a release
  earlier than they did. Fixed in `a19c1066`; 0.22.1 was then released on
  2026-11-03, so the value is right.
- Do: when a catalogue entry has a version field with a default, check the
  default against the last release tag when the entry is added.

## 9. Two process lessons

- **Verify "pre-existing" per changed file.** I reported the remaining pyrefly
  errors as pre-existing. A closing review of the diff found one in the PR's own
  file: `Object of class AST has no attribute name` at `_usage_ast.py:151`, in
  the type-parameter branch. The error count was compared, but not where the
  errors were. An `Any` view of the node fixed it. Do: list the linter's error
  locations and intersect them with the diff's files.
- **Run a test on the base tree with the right path.** Running a new test
  against `git archive HEAD src` with `PYTHONPATH` alone passed silently,
  because the project sets `pythonpath = ["src"]` in `pyproject.toml` and that
  option won. Passing `-o pythonpath=<scratch>/src` as well made the test fail
  on the base, as it should. A "fails without the fix" claim needs the
  failure shown, not assumed.
- One unrelated LFS-pointer test
  (`test_a_pointer_licence_file_is_not_read[pointer]`) failed in each parallel
  full run and passed alone; it came from a different PR already on `main`.
  Name such a flake in the hand-back so it is not mistaken for a regression.

## 10. A text cap does not bound the parser's recursion (#432)

- A long left-recursive chain (`a.b.b...`, `f()()...`, `a[0][0]...`,
  `"a" + "a" + ...`) in a script that names a model made Python 3.10 die with no
  message. The parser builds the tree with one C call per link and checks no
  depth. Measured in the module's own notes: about 40,000 links on a 2 MiB stack
  (the main thread on Windows), 130,000 on 8 MiB. Python 3.11 to 3.13 raise
  `RecursionError` on a stack of 2 MiB or more, but still crash on a thread of
  512 KiB.
- The 1 MiB size cap on the text bounds the bytes read, not this depth: a link
  takes two characters or more, so a script within the cap holds hundreds of
  thousands of links.
- Fix: parse in a thread of its own with an 8 MiB stack; on 3.10 the stack grows
  with the text (`_PARSE_STACK_PER_CHAR`, a fourfold margin for the 1 MiB read).
  Later versions refuse the script with the `usage-unparseable` warning.
- Do: measure, per Python version and stack size, the depth the parser survives,
  and treat a crash as a failure the size cap cannot see.

## 11. `threading.stack_size` is process-wide: set, start, restore in one call (#432)

- The first fix set the stack size, started the thread and waited for it to
  start. Any other thread could run during that wait and start threads of its
  own with the parse stack, up to 255 MiB each. The size is now set, the thread
  started with `_thread.start_new_thread` (which returns without waiting) and
  the size put back in one call.
- A thread started that way misses the hooks of `threading.settrace` and
  `threading.setprofile`, so coverage and profilers did not see the parse. The
  hooks are now passed on.
- **A docstring claim was wrong on one version.** "No other Python code runs
  while the size is set" holds on 3.10 and 3.11. From 3.12
  `_thread.start_new_thread` raises an audit event, so an audit hook (Pitloom's
  wheel file discovery installs one) runs in between. Only the 8 MiB floor is
  ever set there, since the larger sizes are 3.10's. The race test and the
  docstrings were corrected (`189ff5c7`).
- When no thread starts, the parse used to run on the caller's own stack, where
  3.10 still crashed. A text that wants more stack is now tried on a thread with
  the floor, and otherwise warned of as unparseable.
- Do: a docstring that says "no window" names the versions it was checked on;
  and a fallback must not be the very path that crashes.

## 12. Cost in the size of one call, squared (#432)

- Each of these cost time in the square of its size: a call with many
  arguments naming a model, an open-like call with many keywords, a long callee,
  and nested conditional expressions. A 120 KB script took close to a minute.
- Fix: remember per call its argument positions, mode and callee, and per node
  where a value climbs to. A cost test was added (`test_usage_ast_cost.py`).
- Item 5 was a chain of names; these are wide or nested nodes.
- Do: for each construct the walk visits repeatedly, a test that doubles the
  size and bounds the time generously.

## 13. A constant used only in a message gives no edge (#432)

- `print(P)` is a mention and gives no edge. `print(f"loading {P}")`,
  `log.info("%s" % P)` and `"x " + P` still gave an unknown-access edge when `P`
  is a constant naming a model, because the constant was read inside a larger
  expression. Its reads inside such a message now count as reached, as
  `print(P)` does.
- Do: apply a consumer's rule at every depth the value can sit in, not only to
  the value passed directly.

## Final state

At #413 the closing full run showed 18599 tests passed and the one known flake
failed; branch coverage of the changed modules was 100% apart from the single
type-parameter line that only Python 3.12 or later reaches. #413 and #432 both
shipped in 0.22.1. Design limits that stay open are in the design page:
bindings counted per file, constants in source order, per-file import aliases,
library-specific open modes (`h5py`/`zipfile` `"a"`, `shelve`/`zarr`
defaults).
