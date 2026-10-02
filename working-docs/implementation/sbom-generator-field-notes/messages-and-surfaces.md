---
Created: 2026-10-02
Last-Modified: 2026-10-02
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Field notes: messages and usage surfaces

See also: [README.md](README.md) (index of these notes),
[file-scan-unreadable-file.md](../file-scan-unreadable-file.md),
[manual-cli-checks.md](../manual-cli-checks.md),
[skills-trigger-coverage.md](../skills-trigger-coverage.md),
[ai-model-scan-security-lessons.md](../ai-model-scan-security-lessons.md)
sections 3.5 (logs as an output channel) and 3.7 (what the SBOM does not
say).

## 1. What to say, and when

- **Absent data is not an error; a failed read is.** A field the source
  never carries stays empty with no message: a NumPy `.npy`/`.npz` file
  embeds no model name, description or version, so `read_numpy()` leaves
  all three `None` silently. A corrupt file, a truncated archive, a
  network timeout, or a parse failure on data whose own marker promised a
  well-formed value gets one `WARNING:` or `ERROR:`. The test is "did the
  source have an opinion and fail to deliver it" (AGENTS.md design
  principle).
  Do: decide per field which case applies, and keep the absent case
  silent.
- **One unreadable file must not empty the file list.** The file scan
  wrapped its whole loop in `except Exception`, logged at `DEBUG` and
  returned `None`: one `chmod 000` file gave an SBOM with no files and
  nothing on stderr. Now a missing path is skipped silently, an
  `OSError` on one file gives
  `WARNING: FILE=<path>: could not read for file scanning; <error>` and
  skips that file only, and any other exception propagates as the bug it
  is (#244).
  Do: catch the narrowest error per item, never a broad one per batch.
- **Removing a read can remove an error.** With hashing switched off, a
  full `read_bytes()` was no longer needed, but it was also what raised
  `PermissionError` for an unreadable file. A cheap probe,
  `with source.open("rb"): pass`, keeps the failure path. The same option
  made `if not file_entries: return None, []` fire on every run, because
  the list it checked was no longer filled; it now checks a list that
  always is (#213).
  Do: when an optimisation drops work, re-check every failure and
  emptiness test that relied on it.
- **The message text is an interface.** Pitloom's AI skills read
  `; metadata not read` as "a model hit a bound", so the wheel-identity
  messages end `... identity unknown` instead (#266). One constant,
  `UNREADABLE_FILE_WARNING` (`FILE=%s: could not read %s; %s`), serves the
  file scan, the model header read and the licence-file read, so the
  three cannot drift (#244).
  Do: keep each message shape in one constant and grep its consumers
  before rewording.
- **Make every message line parseable.** Archive warnings read
  `ARCHIVE='x.whl' ENTRY='pkg\\mod.py': <what> -- <action>`, both values
  quoted with `%r`, so a name with a space keeps the line `KEY=VALUE`
  parseable. A refusal names the exception type, never its text
  (`could not read (zlib.error) -- wheel refused`) (#251, #266).
  Do: quote untrusted values with an escaping repr; name exception types,
  not messages.
- **A message must describe its own branch.** A discovery function logged
  "using Hatchling-based heuristic, file list may be inaccurate" before
  an early return that never ran Hatchling (no `[project]` table) (#215).
  A gate notice said models "are listed" when no SBOM was written; see
  the lessons doc, 3.7.
  Do: re-read every log line above a new early return.
- **One message per event, not per occurrence.** A process-wide fact
  warns once: `WARNING: licenseid database appears empty` (#243). A run
  reading two archives warns once per archive: `embed-wheel
  --allow-build` names a bad member once plain and once with `Build: `, a
  documented limit (#251). An unfetched Git LFS checkout is one summary
  line per run; see the lessons doc, 3.10.
  Do: name the event first, then decide how many lines it deserves.
- **A deviation is announced, and the truth kept.** When a value has to
  deviate (a ZIP entry floored to 1980, a stale SBOM removed from the
  wheel), Pitloom says so in one `INFO:` line and keeps the true value in
  the SBOM rather than silently aligning the two (#148). Different
  settings give different SBOMs by design; same input plus same settings
  give the same bytes.
  Do: document every setting's effect on output, and print what was done.

## 2. Usage surfaces drift apart

- **A global option must reach every subcommand.** `--debug` was parsed at
  the top level, but 7 of 10 subcommand generators called
  `configure_logging()` again with no arguments and reset the level to
  `INFO`; each subcommand's own tests passed. The flag now sets
  `PITLOOM_DEBUG`, which every no-argument call reads (#201, AGENTS.md).
  Do: carry a cross-cutting choice in one mechanism every surface already
  reads.
- **Choose a config source by presence, not by value.** Selecting
  `pyproject.toml`'s config only when it differed from the defaults
  (`pyproject != PitloomConfig()`) let `setup.cfg`'s `pretty = true` beat
  an explicit `pretty = false`, because `false` is the default. A
  declared, even empty, `[tool.pitloom]` now wins (#232).
  Do: let an explicit default value count as a declaration.
- **A helper shared by two stages needs a stage flag.** A source-stage
  artefact such as `poetry.lock` must not reach a build-stage SBOM just
  because a source reader and the build hook's gap-fill share a function;
  the embed paths pass `include_locked_dependencies=False` rather than
  rely on call-site discipline
  (AGENTS.md; [poetry-support.md](../poetry-support.md)).
  Do: make stage scope an explicit parameter.
- **Read once, pass the result down.** `wheel --embed` read a wheel's
  identity, then the embed read and warned about it again. The identity
  is now passed down (`identity=`), and only `verify-wheel` and
  `embed-wheel --verify` ask for a warning on an unreadable `METADATA`,
  once per run (#266).
  Do: give each fact one reader per run, and thread it to later steps.
- **A refusal must look the same on every command.** A wheel that cannot
  be opened is one `ERROR:` of one shape on `wheel`, `generate`,
  `embed-wheel`, `verify-wheel` and `validate-wheel`; a batch goes on to
  the next wheel and exits 1. Before, embed and verify each built their
  own `Invalid wheel archive` text (#266).
  Do: map archive-open errors in one function every command calls.
- **Test one behaviour on every surface, in one file.**
  `tests/test_archive_member_name_surfaces.py` runs the same raw archives
  through `loom wheel`, `loom wheel --embed`, `loom embed-wheel`,
  `generate_wheel_sbom()`, `embed_wheel_sbom()`, `loom project`,
  `loom generate` and `generate_project_sbom()`, for ZIP and tar, and
  compares output and warnings with a simulated Windows read (#251).
  Do: write the cross-surface test when the behaviour is introduced.
- **In-process tests miss what a real CLI run shows.** pytest does not
  see argv parsing, real stderr wording and counts, environment-variable
  threading, or a subprocess importing a different install. Pitloom's
  `scripts/manual_cli_checks` runs real `loom` processes over a declared
  matrix (subcommand x option x `PITLOOM_DEBUG`/`SOURCE_DATE_EPOCH`); its
  first run found 7 CLI bugs, and `M/completeness` fails CI for any
  option the plan does not classify. A relative `PYTHONPATH` once made
  children run another checkout; the runner now exits if a child's
  `pitloom` differs from its own (#226, #261).
  Do: keep a real-process matrix next to the unit tests, and check which
  code it actually ran.
- **AI skills are a surface with no tests.** A skill is triggered only by
  its frontmatter `description`; a body section documenting a command
  does not make it reachable. A renamed flag or changed output shape goes
  stale there silently. Pitloom enumerates `add_parser(` subcommands
  against every `skills/*/SKILL.md` description and keeps *verify*
  (structure) and *validate* (schema, SHACL) apart, since users treat
  them as synonyms (#223,
  [skills-trigger-coverage.md](../skills-trigger-coverage.md)).
  Do: grep the skills for every command, flag and message you change.
- **One model, recorded differently by surface.** `loom model` kept 1001
  metadata entries silently where scans warned at 1000; see the lessons
  doc, 3.7.
  Do: compare the surfaces' outputs for one input, not each surface
  alone.
