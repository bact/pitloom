---
Created: 2026-10-30
Last-Modified: 2026-10-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: raw exception text leaks paths and forges lines

See also: [README.md](README.md) (index of these notes),
[message-catalogue-decisions.md](message-catalogue-decisions.md) (the
catalogue's taxonomy, trust rule and ratchet),
[provenance-injection-and-message-contract.md](provenance-injection-and-message-contract.md)
(the same hostile-name class in provenance),
[evidence-levels-and-provenance-of-absence.md](evidence-levels-and-provenance-of-absence.md)
(the `unreadable-file` reason, now equal to a code),
[messages-and-surfaces.md](messages-and-surfaces.md) (absent versus failed),
[message-catalogue-and-skills.md](../../design/message-catalogue-and-skills.md),
[testing-traps.md](testing-traps.md).

**Status: #408 is in review, not merged** (branch `family-file-unreadable`,
head c53ad977, 2026-10-30; catalogue PR 2a). Everything below about code
is read from that branch.

## 1. The bug

- **What was logged.** The skip of an unreadable project file in
  `core/_models_wheel.py` logged the exception itself. The text of an
  `OSError` is `[Errno 13] Permission denied: '/abs/path'`: the absolute
  path of the file. Under `--allow-build` that is a temporary build
  directory; otherwise it is the user's home. The message was therefore not
  reproducible between runs and leaked the path into stderr, a stream the
  AI skills read (known-bugs, "Found 2026-10-29 (evidence-levels review)",
  fixed on the branch).
- **It was not one site.** The plan (session scratch, on tree dfd0047a)
  lists the same raw or `one_line(exc)` text at the dataset hash, the
  loom script hash, the loom model and model-generator hashes, licence
  detection, the `setup.cfg` and `pyproject` directives, the usage scan,
  the ID registry, a lock file, `fetch_json` and the README card reader.
  `one_line()` escapes control characters but keeps the text, so it does
  not remove a path.
- **A second bug beside it: a directory name could forge a line.**
  `OSError.__str__` quotes the file name with `%R`, so a newline in a file
  name cannot escape the quotes. The directory warning in
  `_models_wheel_unlistable` logged the directory's relative name raw, with
  no `loggable()`: a directory called `a\nWARNING: x` wrote a second
  `WARNING:` line. (Plan, section 3; the regression test creates such a
  directory, POSIX only.)

## 2. The decision: the unsafe value cannot be passed

- **A typed field, not a lint.** The catalogue's new `failure` field takes a
  `BaseException`, never a string. An `OSError` with a `strerror` is
  written as that description only (`Permission denied`); any other
  exception as its one-line text, or its class name when it has none
  (`messages/_fields.py::_failure`). A `str` raises `ValueError`. So no
  call site can pass `str(exc)`: the bug is fixed at every site by
  construction, where the earlier provenance fix (#389) needed a builder,
  an AST lint and a runtime key-set test.
  Do: when the safe form can be the only form a helper accepts, do that
  before writing a lint.
- **Paths go through one field.** `file` and the new `dir` write a path as
  `loggable()` does (escaped, quoted when it holds a control character), so
  the directory-name forgery ends with the same change. Trust follows the
  catalogue's rule: a file name is attacker text printed as data; the
  advice comes from the entry, never from the line.
- **The exception picks the entry.** `warn_file_unreadable` and
  `warn_dir_unlistable` read the exception: an `OutsideRootError` is the
  variant `file-unreadable/outside-project`, a `UnicodeDecodeError`
  `file-unreadable/not-utf8`; the advice differs (move the file into the
  project; save it as UTF-8), the effect does not, so the condition stays
  `unreadable` (decision D of the catalogue).
- **Text kept, but the detail** ("code first, wording later"): the
  not-UTF-8 lines of a `setup.cfg` directive and of the usage scan gain
  the variant's `not UTF-8:` prefix; the model hash's parenthesis
  (`no verifiedUsing, registry lookup not gated`) moved to the entry's
  "did" text; a licence file is named relative to its project.
- **Residual, read from the code, not tested:** an `OSError` with no
  `strerror` falls to its one-line text. `OSError("x")` carries no path
  unless the raiser put one in; the guard is the typed field, not a
  scrub of the text.

## 3. Absent is quiet, now enforced

- A file that vanished between discovery and read is an absent file, not
  an unreadable one. The helpers raise `InternalError` for an `OSError`
  whose errno means "missing", so a vanished file can never be coded
  `file-unreadable`; every caller asks `is_missing_errno` first. The
  visible change: a dataset member, a registry file or a usage source gone
  since it was found now says nothing (commit a23a1023).
- This is the project's rule (absent source data is not an error; a read
  failure is) applied at the helper, so the next caller cannot forget it.
- Two lines were deliberately left uncoded: a listed requirements file
  that is not found (that is a missing input, another family) and a name an
  ID registry cannot hold. The ID registry's explicit `PATH` error stays
  uncoded until the registry PRs (no `ERROR` line is catalogued before a
  site prints one). Each has an allow-list entry by name in
  `tests/messages/test_file_unreadable.py`.

## 4. The reason and the code are one word

The evidence reasons for an omitted dataset hash (`file-unreadable`,
`dir-unlistable`) are written by this PR (evidence "PR-D", paired with the
family in the plan): a loom dataset that is not hashed for one of these
reasons gives the same code as its `Reason:` in the provenance. A drift
test holds the two lists equal (`tests/messages/test_drift_sources.py`),
so the evidence segment and the stderr code cannot name one cause two
ways. The codes were renamed to match earlier
([message-catalogue-decisions.md](message-catalogue-decisions.md),
section 1).

## 5. Evidence and numbers

| Fact | Value | Source |
| --- | --- | --- |
| Uncoded in-scope sites | 511 to 498 | commit a23a1023 (measured by the ratchet) |
| Modules with an uncoded site | 160 to 155 | design record on the branch |
| Sites the plan coded in 2a | 16 counted, 2 new uncoded lines | plan (*estimate*, before the build) |
| Manual check 25 | one coded line per `chmod 000` file and directory, exit 0, no absolute path on stderr | commit 378d6d91 |
| Regression tests | the record's `pitloom_code`; `str(tmp_path)` not in the message; a newline-named directory; the `failure` writer refuses a `str` | plan, section 3 |

The plan's own count of 511 to about 497 was off by one from the built
498: the ratchet is the measurement, the plan only an estimate.

## 6. What generalises

- Never interpolate an exception's text into an operator-facing line.
  Interpolate the part you mean (the description of the failure), and the
  path through one function that escapes it. This closes a leak
  (absolute paths, user names in home directories, temporary directory
  names) and a forgery with one rule, and makes stderr reproducible
  across machines, which a skill that quotes stderr needs.
- A "could not read" family should hold only failures of a thing that
  exists. A vanished file is a race, not a fault.
- Test with the real permission bits where the platform allows it, and
  with a monkeypatched syscall where it does not (see
  [agent-work-lessons-oct30.md](agent-work-lessons-oct30.md)).

## 7. Open

- Is `strerror` stable enough to quote? On POSIX it is the C library's
  English text; on Windows the system message may follow the user's
  language. *Unverified*: no non-English Windows run was made. If it is
  not stable, a skill that matches on the text breaks; the code does not.
- The remaining raw-exception sites (fragment reads, wheel members,
  project metadata, fastText and PT2 `Failed to read`) are listed in the
  plan as deferred to later catalogue PRs; each still logs `{exc}`. How
  many of them hold a path is not measured.
- PR 2b (cards, `fetch_json`, `text-malformed`) is planned, not built.
