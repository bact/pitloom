---
Created: 2026-11-10
Last-Modified: 2026-11-10
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: lessons of the model-SBOM-from-Git round (PR #464, 2026-11-09)

See also: [README.md](README.md) (index of these notes),
[../model-sbom-from-git.md](../model-sbom-from-git.md) (what was built and
decided), [agent-work-lessons-nov10.md](agent-work-lessons-nov10.md) (the
next round),
[../ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
(the paper notes on untrusted packages),
[../recurring-bug-patterns-ci-matrix.md](../recurring-bug-patterns-ci-matrix.md),
[../recurring-bug-patterns-platform-windows.md](../recurring-bug-patterns-platform-windows.md).

PR #464 made a model file, folder or Git URL enough for an SBOM, for all ten
model formats, and went through five review rounds before release 0.23.4.
Items marked *session record* are the lead agent's account; items with a
file or commit are checked in Git.

## 1. In a clone, listing the files is running the repository's code

- **Checked in Git** (`model-sbom-from-git.md`, D7 to D11; `git.py`,
  `_models_wheel_*` modules). Pitloom lists a project's files by asking its
  build backend. For a repository fetched from a URL that is untrusted code:
  Hatchling metadata hooks, setuptools `cmdclass` and `setup.cfg` `[global]`,
  PDM hooks and the working directory or the clone on `sys.path` all run or
  import the repository's own modules. Round 4 of the reviews found the
  rest: the clone's `.git/config` kept the URL's user and password, a
  `force-include` entry or an encoded slash in a URL named a file outside the
  clone, and two folder links to `.` made every directory walk endless.
- Fixed by confinement, not by trust: an import-path guard (no relative entry,
  no entry in the clone), links that leave the clone or point to a folder
  removed after the checkout, credentials scrubbed from the clone's config, a
  build entry outside the clone dropped before discovery, and a 60 s cap on
  discovery. The cap is a profile hook (`sys.setprofile`): cooperative, it
  cannot stop a call blocked in C, and a library that swallows
  `BaseException` could outlive it. An exception raised into the thread from a
  timer (`PyThreadState_SetAsyncExc`) was rejected: it escapes `try` blocks on
  Python 3.13.
- Paper-worthy: for an SBOM generator the attack surface of an untrusted
  repository is the file list and the project metadata, not only the model
  parsers that earlier notes cover.

## 2. Gate by route, not by format, with one object

- **Checked in Git.** In a Git clone the native-library readers (fastText,
  GGUF, HDF5, ONNX, PyTorch) are not run: the model is listed by name, format
  and hash, with one `INFO:` (`reader-unsafe/remote`). The first version
  gated only the model route; a user's request to "gate the project route's
  native readers too" exposed the same gap in the project route. One shared
  gate, built once per scan and reported once, now serves the model, project
  and wheel scans, so the routes cannot drift.
- Hostile fixtures (`hdf5-hang.h5`, `hdf5-segfault.h5`) are the argument for
  the gate: a hang or a crash of a native reader from a URL a web service
  accepts is the service's outage.

## 3. Five review rounds, and what made them converge

- *Session record.* Rounds ran as write, review, fix, add a test, repeat.
  Reviewers were read-only and each got an area (safety and correctness,
  Windows and Python 3.10, docs and skills against behaviour, test quality).
  Round 4 found the High items of section 1. Round 5 was limited by the
  maintainer to correctness and consistency; it found no High item, which
  was the stop signal.
- Mutation testing of the gate and resolver conditions found assertions that
  held with the condition removed; each got a test.
- Do: scope a final round narrowly, so its silence means something, and stop
  on "no High" rather than on a round count.

## 4. What CI showed that local runs did not

- **Checked in Git** (CI logs of 2026-11-09; details in the two pattern
  files above). CI installed the newest `licenseid` in range (0.8.4) while
  the local environment had 0.8.3; the 0.8.4 reading of `MIT/Apache-2.0`
  broke a test on one leg. A nested-JSON test pinned wording that differs
  between Python 3.14.6 and 3.14.10 and failed on 3.10 and 3.11 for a
  different reason. Two Windows-only failures were a NUL path that
  `realpath` accepts and a zero-second deadline missed by a 15.6 ms clock.
  Fail-fast cancelled the other legs each time.
- Do: read the versions CI installed, run changed tests on those
  interpreters, and read the cancelled legs.

## 5. Claims checked against code, and a wrong commit identity

- *Session record.* A plan's note, "a symlink in a cloned project can still
  make the sniff and hash read a file outside the clone", was stale: the
  checkout already removes such links (`_drop_outside_links`), and the
  implementation record said so. The lead repeated the note to the
  maintainer before checking. Do: verify a claimed open hole in the code
  before reporting it, and fix the plan text when it is disproved.
- *Session record.* The sandbox's git identity had been reset to the AI
  identity, so one commit went out, signed off and pushed, under it; the
  repository's rule is that no AI is author or co-author. Repair needed a
  force-push, which the maintainer allowed after two denials by the
  sandbox's permission classifier. Do: set the identity first and read
  `git log -1 --format=%an` before every push.

## 6. What was left out on purpose

- A Hub model file read by HTTP range requests: a second host behind
  redirects, no Pitloom client with a per-hop URL check and byte budget, and
  a conflict with "model files are never downloaded" (design note, roadmap
  medium term). Recursive model discovery, the commit and URL in the SBOM,
  and `raw.githubusercontent.com` stay open.

## 7. Working preferences recorded

- Summaries to the maintainer in bullets; a PR title of at most 60
  characters and a summary of at most 280.
- `roadmap-completed.md` lists what was built and the design choices only: no
  release preparation, post-release verification or CI detail.
