---
Created: 2026-11-26
Last-Modified: 2026-11-26
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Message catalogue: consistency rescan

See also: [message-catalogue-finish-plan.md](message-catalogue-finish-plan.md)
(section 4, the scope), [message-catalogue-and-skills.md](message-catalogue-and-skills.md)
(rule N, R1), [message-catalogue-sweep-c2-plan.md](message-catalogue-sweep-c2-plan.md)
(ruling 8, sections 10-11), [message-catalogue-sweep-c1-as-built.md](message-catalogue-sweep-c1-as-built.md),
[../implementation/message-catalogue-sweep-b-plan.md](../implementation/message-catalogue-sweep-b-plan.md),
[known-bugs/messages-and-provenance.md](known-bugs/messages-and-provenance.md).

The last step of the catalogue series: read every catalogued line for shape
(`LEVEL: [SUBJECT=value: ]CONDITION[; ACTION]`), subject keys, sub-prefixes
and frames, codes by cause, `since`, British spelling, and the docs and
skills that quote each line; fix what is inconsistent, record what is a
choice. Measured on main 4f927257: 202 codes, 617 lines.

The work splits into three PRs (the whole is over 1,500 changed lines):

1. **PR 1 (this branch, `message-consistency-rescan`)**: the permanent tests
   and the wording fixes below.
2. **PR 2**: per-surface advice twins (section 6).
3. **PR 3**: library argument validation (section 7).

## 1. Method

- A dump of every entry and line (`code`, level, template, fields, `since`,
  effect, actor) read in full, plus three audits by fresh agents: the
  status of every carried item on 4f927257 (probes and reads), a
  cross-surface parity matrix (CLI, library, hook, loom SDK; probes), and a
  second opinion (Opus) on the twelve wording questions in section 3.
- A near-duplicate audit: every pair of templates from different families
  with `difflib` similarity 0.85 or more (placeholders folded). 30 pairs, none
  a merge candidate: each pair is two causes worded in parallel on purpose
  (`could not read`/`could not write`, `not valid JSON`/`not valid INI`,
  `redirects to <t>; followed`/`not followed`, the fragment trio
  `not found`/`could not be read`/`is not valid JSON`). The one identical
  pair (`option-invalid` and `config-invalid`, `<>: must be <>, got <>`) is a
  recorded choice (section 4).
- A HEAD-vs-tree sweep per changed family (section 5).

## 2. Permanent tests (built)

`tests/messages/test_catalogue_consistency.py`:

| Rule | Test | Fails on main |
| --- | --- | --- |
| A closed subject-key vocabulary: each `KEY=` names one kind of value, from named fields (`SUBJECT_FIELDS`) | `test_every_subject_key_names_its_one_kind_of_value`, `..._is_printed`, `test_no_subject_key_prints_a_literal_value`, `test_a_key_field_takes_only_subject_keys_and_its_one_value` | yes (`MODEL=` held two kinds) |
| R1: an `INFO:`-only entry is a decision nobody acts on, forward-only, 12 ruled outliers | `test_an_info_only_entry_is_a_decision_nobody_acts_on` | no (records today) |
| British spelling over templates, summaries, did and advice (`-ize`, `-or`, `-er`, `-og`, `-ed`/`-ing` doubling, `license` as a noun); quoted spec, tool and key names exempt | `test_an_entry_is_written_in_british_english`, `test_a_summary_...`, `test_the_lint_finds_american_words_only` | no |
| The condition opens in lower case (a name excepted) and no line ends with a full stop | `test_a_condition_opens_in_lower_case_with_no_full_stop` | yes |
| Glossary: `directory`, never `folder`, in lines and prose | `test_an_entry_says_directory_never_folder` | yes |

`since` against the last tag's catalogue (`released-lines.tsv`) and D4, D5,
D7 were built in sweeps A and B. The glossary covers one pair only: `file`,
`path`, `archive`, `member` and `wheel` showed no competing word in the read.

## 3. Rulings (second opinion and mine)

| # | Question | Opus | Mine | Done |
| --- | --- | --- | --- | --- |
| 1 | `MODEL=` holds a quoted model name (`dataset-conflict`) and a free file name (`usage-unparseable/mention`, released 0.22.1) | quote both | agree | `MODEL=%(model)s` on the mention line, `since` 0.25.0; the `model` field now covers a mentioned file name |
| 2 | ERROR lines with a bare `%(path)s:` subject (`lfs-pointer`, `model-wrong-format`, `project-or-model-not-found`, `model-ambiguous`) vs `FILE=` on their WARNING twins | keep: the ERROR names the user's input, the WARNING a member found | agree | recorded |
| 3 | Capitals and full stops (`No pyproject.toml ... found in`, Git `No file ... branch.`, `Model file not found`, eight `Failed to ...` in `model-field-unreadable`) | normalise all | agree | done, each reworded line `since` 0.25.0; the test in section 2 keeps it |
| 4 | `folder` or `directory` | `directory` everywhere (it is the `DIR=` key, the stdlib word and the `docs/` word) | `folder` for a Git page (GitHub's word), `directory` on disk | Opus's: one word is checkable; templates, summaries and the `folders` field's shown placeholder (`<directories>`) changed; the field name kept |
| 5 | `dataset metadata: ` is the only lower-case sub-prefix | capitalise | agree | **deferred**: its tests are in a licence-fenced file (`tests/extract/dataset/test_licence.py`); follow-up |
| 6 | `over-cap` ERROR `config file %(path)s:` for an sdist member, no `FILE=` | `FILE=<sdist>:<member>` through the source line | agree | the special line removed; `FILE=<sdist>:pyproject.toml: larger than the 1048576-byte config-member cap for the project metadata; not read` |
| 7 | `fragment-invalid` says `not valid JSON`, a `json-malformed` condition | rename to `json-malformed/fragment` | keep | kept: the maintainer ruled the code in PR 15 (Q3): a fragment's advice (fix the fragment, the merge fails) differs from a document's, rule D |
| 8 | `PATH %(path)s` (no `=`) in `option-invalid`, `index-path-no-effect`, `text-malformed/registry` | keep: the CLI metavar, not a subject | agree | recorded |
| 9 | `text-malformed` names a non-file SBOM element under `FILE=` | `ELEMENT=<spdxId>` for every element | a file by `FILE=<name>`, any other element by `ELEMENT=<spdxId>` | mine: the opinion's reason (an escaped file name cannot be found) is weak, since `FILE='a\udcff'` is the text the SBOM holds; a file's name is what the user searches for. New `ELEMENT=` line `since` 0.25.0; files sort first, then the least label; a blank node is named by its `@id` as read (the CreationInfo dedup may renumber it in the output), an element with neither id by its type |
| 10 | `ID registry: loom model %(entity)s` reads as the CLI command | `loom SDK model` | agree | done (`registry-hash-missing`, two lines) |
| 11 | `registry-hash-conflict`: `minting a new spdxId` and `a new id is used` under one code | `minting a new spdxId` | agree | done |
| 12 | `option-invalid` special lines for `CredentialPolicy.refuse` and `PitloomConfig.url_credentials` lacked `, got` | fold into the `VALUE_LINE` | agree | done; a secret-bearing value prints its kind only (`got a string`); a library bool says Python's `True or False` (new `python-bool` id), a configuration one TOML's `true or false` |

## 4. Recorded design choices (no change)

- **`FIELD=` has two value domains**: a project metadata key (free) or a
  dataset field (constrained). One key, two fields; `SUBJECT_FIELDS` says so.
- **`option-invalid` and `config-invalid` share a template**: the caller's
  argument vs the user's `pyproject.toml`; the code tells the actor.
- **`text-malformed/registry` vs `registry-malformed` (lone surrogate)**:
  different causes (an input name the registry cannot store vs a corrupt
  registry file). They now share one literal (`UNENCODABLE`).
- **`; %(failure)s` in the action position** (`file-unreadable` and others)
  vs `(%(failure)s)` elsewhere: a released pattern; the parenthesis is for a
  detail inside the condition, the `; ` for a relayed failure that ends it.
- **`%(key)s=%(name)s` in `over-cap`**: one line for any keyed subject; the
  key field takes subject keys only (tested).
- **Two argparse refusal details stay out of the value line**:
  `build timeout must be 1-604800 seconds, got 0` and `not a fingerprint
  (...)`. argparse prints them after `argument --build-timeout: `, which is
  their subject; the value line would name the option twice.
- **The Hub model `MODEL=<name>`** (C2 left open): the model's repository
  id is its name on the Hub, the same value a user types.
- **R1 outliers** (12, each with its ruling in `R1_OUTLIERS`):
  `reader-unsafe`, `reader-unsafe/remote`, `field-not-recordable`,
  `usage-unparseable/mention`, `release-unpinned` (and `/prerelease`,
  `/yanked`), `release-unusable`, `file-ambiguous` (released);
  `git-link-unsafe` (PR 13 Q13), `dependency-name-ambiguous` (PR 10-11 Q6),
  `option-missing/project-dir` (PR 16 E5).

## 5. Fixed slips, and the HEAD-vs-tree sweep

Slips (unreleased or plainly inconsistent), fixed with the rulings above:

- `credentials-unsafe/git-userinfo` quoted its URL (`quote_source`) unlike
  every `URL=` sibling: now `url_text`.
- One `model file` input kind: the special `Model file not found` line folded
  into the generic `%(input)s not found` line (`input_not_found(MODEL_FILE_KIND,
  ...)` at five sites).
- `project-not-found` reworded to the subject-first shape its sibling
  `project-or-model-not-found` already had (`'<path>': no Python project
  (pyproject.toml, setup.cfg or setup.py)`).
- `export/spdx3_json.py`'s lone-surrogate pass is public
  (`escape_lone_surrogates_in_graph`), so its test needs no private access;
  the test asserts the exact line for a file with a non-ASCII name, a
  package, a blank node and an element with no id; a printable non-ASCII
  file name kills K16's `repr(min(changed))` mutant (section 9).

Sweep (a HEAD archive vs the tree, real CLI argv and library calls): 22
probes (9 Git URL, 13 local), 12 changed; every difference is a reworded
line of this PR
(`model`, `enrich` missing model file; `project`, `generate` on an empty or
model-only directory; sdist config member over the cap; both credential
policy refusals; Git userinfo, quoting only). No probe lost a line, gained a
line or changed a code or exit status. The usage mention and surrogate lines
need inputs the CLI probe could not build here (a package that ships the
model, a non-UTF-8 name on APFS); their tests assert the new text and fail on
main.

## 6. PR 2: per-surface advice twins

A line's action named a CLI flag on every surface (`BuildOptions(timeout=5)`
from the library said `--build-timeout`). The surface that runs now picks the
wording through one mechanism; no call site chooses.

### 6.1 Mechanism (as built)

- `pitloom.messages._surface` (new): the surfaces `cli`, `hook`, `library`;
  a `ContextVar` (default `library`) set by `advice_surface(surface)`, which
  replaces `credential_advice()`. Entry points open it: `__main__.main()`
  and `cli_error_handler` (`cli`, so a handler called without `main()` says
  the CLI's wording too; the GitHub Action runs the CLI) and
  `PitloomBuildHook.initialize()` (`hook`); a library call, `loom.run()`
  included, keeps the default.
- `Twins(cli=, library=, hook=)`: one wording per surface, of `Line` or
  `Summary`, all members of one level and one field set (checked when
  built), so one call says any of them. `Twins.no_hook(cli, library)` marks
  a line the hook cannot reach: the hook gets the library's wording, and
  resolving it there raises `InternalError` only under `strict_surfaces()`,
  which the test suite opens for every test (`tests/conftest.py`); a user's
  build never fails over a line's wording. `emit()`, `CodedValueError`,
  `Message.line_for()`, `say_summary()`, `remote_error()` and
  `warn_discovery()` take a `Twins` and resolve it; no call site picks a
  member (a test walks `src/` for `<NAME>_LINES.cli` and the like).
- Option names: `pitloom.core.option_names` (new; `PARAM_TO_FLAG` moved
  there) names an option as the surface spells it: `option_name(param)`
  gives `--use-lockfile/--no-use-lockfile` (CLI) or `use_lockfile`
  (library, also under the hook, which settles configured keys only). A
  `[tool.pitloom]` setting (`settle_inert(..., configured=True)`, an explicit
  source, not the log level) is named by its TOML key on every surface,
  `tool.pitloom.describe-relationship`: the `option` field is one token.
  A reason that names an option holds a placeholder (`without
  {allow_build}`, `for an externally-supplied {sbom}`, `without
  {enrich_project_dir}`), written when the warning is said
  (`named_reason()`), never at import. `BuildOptions.given` names
  `BuildOptions.allow`, `.no_isolation`, `.timeout` in the library.
- The build switch spellings live once in the catalogue
  (`ALLOW_BUILD_NAMES`, `NO_BUILD_ISOLATION_NAMES`, `BUILD_TIMEOUT_NAMES`);
  the build lines and `option_names` read them.
- Library wording rule: a condition names the attribute or parameter as
  given (`BuildOptions.timeout ... without BuildOptions.allow`); an action
  names a form to copy that fits any carrier (`pass BuildOptions(allow=True)`,
  `set trust_model_files=True`).
- The credentials triple keeps its branch (its lines take other fields per
  surface: `option=`, `setting=`, none); it reads `current_surface()`.
- A `ContextVar` does not reach a `threading.Thread` (unless
  `sys.flags.thread_inherit_context`): no twinned line is said off the
  thread that entered the surface (checked: the Git size watcher and drain,
  the redirect probe, the `_usage_parse` thread, the PyPI dependency pool;
  signal handlers run on the main thread; the PEP 517 build is a
  subprocess). A test pins the behaviour.
- `IdRegistry.require_namespace()` moved to the CLI (`cli/id.py`), its only
  caller: no library call gives a second namespace.

### 6.2 Surface x message matrix

`-` the surface cannot reach the line (verified at the entry point; its
twin is the library's, named explicitly). Probe: a library call, `loom`,
and a Hatchling build.

| Code (line) | CLI | Library | Hook |
| --- | --- | --- | --- |
| `option-no-effect` WARNING (`%(option)s`) | `--use-lockfile/--no-use-lockfile` | `use_lockfile` | - (the hook settles config keys only) |
| `option-no-effect` INFO (config key) | `tool.pitloom.describe-relationship` (`embed-wheel`) | same (`embed_wheel_sbom()`) | same (was the flag) |
| `option-no-effect` `Build:` | `--build-timeout`, `--no-build-isolation` `... without --allow-build` | `BuildOptions.timeout`, `BuildOptions.no_isolation` `... without BuildOptions.allow` | - (no build option) |
| reasons naming an option (`without --project-dir`, `with --project-dir`, `--sbom`) | the flag | `project_target` (`enrich_model()`), `project_dir`, `sbom_path` | - |
| `reader-unsafe` | `pass --trust-model-files` | `set trust_model_files=True` (a keyword, or `ConfigOverrides` for `embed_wheel_sbom()`) | - (the hook reads the project directory, not a wheel) |
| `reader-unsafe/remote` (Git, PyPI lines) | `pass --trust-model-files` | `set trust_model_files=True` | - |
| `file-discovery-needs-build` (uv overrides) | `pass --allow-build` | `pass BuildOptions(allow=True)` (`build_options=`, or `ConfigOverrides.build_options` for `embed_wheel_sbom()`) | - (the hook assumes Hatchling) |
| `wheel-sbom-ambiguous` | `pass --sbom-filename` | `pass sbom_filename` (`find_embedded_sbom()`) | - |
| `target-wrong-format` (Hub model) | `use 'loom model'` | `use generate_model_sbom()` | - |
| `pypi-url-unusable` (model line) | `'loom wheel' reads its wheel, 'loom project' its sdist` | `generate_pypi_sbom() reads its wheel, generate_pypi_sbom(kind='sdist') its sdist` | - |
| `release-file-not-found` | `'loom project <url>' reads its sdist` | `generate_pypi_sbom('<url>', kind='sdist') reads its sdist` | - |
| `release-file-not-found/compatible-wheel` | as above | as above | - |
| `release-file-not-found/sdist` | `'loom wheel <url>' reads a wheel` | `generate_pypi_sbom('<url>') reads a wheel` | - |
| `project-not-found/model-files` | `use 'loom model <url>' or 'loom generate <url>'` | `use generate_git_sbom(url, sbom_kind='model') or generate(url)` | - |
| `option-conflict` (namespace) | `--namespace` | - (`IdRegistry.require_namespace()` moved to the CLI: no library caller gives a second namespace) | - |
| `build-code-unsafe` (4 lines) | `--allow-build runs ... (--build-timeout)` | `BuildOptions.allow runs ... (BuildOptions.timeout)` | - |
| `build-timeout` (2 lines) | `(--build-timeout)` | `(BuildOptions.timeout)` | - |
| usage hint, project (summary) | `pass --scan-model-usage (or set scan-model-usage = true)` | `pass scan_model_usage=True (or set ...)` | `set scan-model-usage = true in [tool.pitloom]` |
| usage hint, wheel (summary) | `... in a --config file` | `... in pitloom_config` | - |
| `pypi-url-unusable` (Git line, library only) | - | `generate_pypi_sbom() reads it` (was `generate_pypi_sbom(), 'loom wheel' or 'loom project' reads it`) | - |
| `file-ambiguous` (generate line), existing twin | `loom generate reads the wheel` | `generate() reads the wheel` | - |
| `credentials-unsafe/refused`, `/written`, existing triple | flag | `CredentialPolicy` | `pyproject.toml` list |

The last two rows were picked per call site (`sdist_hint(library=)`, a
branch in each `say_*`); they move to the mechanism.

Found while building it, recorded (not fixed here): for a Git URL's
`uv_build` project with overrides, the uv-overrides line says `pass
--allow-build` (or `BuildOptions(allow=True)`), but a build never runs for
a remote repository (`REMOTE_REPOSITORY_REASON`); the hint should be left
out in a remote clone. `checked_embed_basename(where=)` is another
per-call-site choice of a surface's spelling (argument validation, section
7).

Out of scope, recorded: `config-unsafe` says `--config or pitloom_config=`
on both surfaces (one merged line); `option-missing` `pass --id-registry
FILE` and `PATH ... outside --project-dir` are CLI-only; the GitHub Action
names its input (`trust-model-files`) only in the advice prose; `-v/--verbose`,
`--embed`, `--allow-signed-wheel` reasons are CLI-only.

## 7. PR 3: library argument validation (planned)

1. An empty ID registry path: four codes by route (`PitloomConfig(id_registry='')`
   and `IdRegistry.load('')` say `input-not-found`, `save('')`
   `option-invalid`); one rule: `option-invalid` at the API boundary.
2. `--config ''` says `input-not-found` (exit 1); `-o ''` and the other empty
   options `option-invalid` (exit 2).
3. Plain `TypeError` from `BuildOptions(allow="false")`, `timeout="90"`
   (`validate_build_timeout`, `core/_models_wheel_types.py`), `IdRegistry.load(b'x')`,
   `refuse_credentials=1`; plain `ValueError` from `IdRegistry.save()`.
4. Unvalidated bools: `pretty='false'` writes a pretty SBOM, silently.
5. `loom generate ''` reports the missing `-o` first, not the empty target.
6. Input-kind wording: `project directory` (CLI `project`) vs `project path`
   (library, `generate`) for one input.

## 8. Follow-ups

Fenced off from this rescan (licence-detection modules and tests):

- `dataset metadata: ` capitalisation (ruling 5).
- `READ_USES` "for license files" (British: licence), used by
  `extract/_license_detect.py`.
- `license-db-missing`, `license-db-unusable`: `licenseid database` in prose
  (the product is LicenseID).
- `license-ambiguous`: "license" in prose; `license-relationship-invalid`'s
  ERROR line opens `Fragment merge left ...` (capital; exempt in the test).

Seen in this rescan, outside its scope:

- The ONNX reader's relayed failure reads `Failed to load ONNX model from
  '<path>': ...` (capital, the path a second time) inside a coded
  `model-unreadable` line (`extract/ai_model/onnx.py:375`); other readers'
  relayed texts unchecked.
- `loom generate <dir>` names one model `FILE=a.gguf` (relative) and the next
  `FILE=<absolute path>` in the same run.
- `loom project <dir>` quotes the resolved path (`/private/tmp/...` on
  macOS), `loom generate <dir>` the path as given.
- `download-network-failed` says `git <cmd> failed: <why>`,
  `git-repository-unusable` `git <cmd>: <why>`.
- `loom verify-wheel "" --offline` frames the unknown option `loom:`, not
  `loom verify-wheel:` (also `validate-wheel`, `enrich`).
- `input_datasets=[["x"]]` says `got an array`: it names the list, not the
  entry.

Carried items still open on 4f927257 (status audit; S unless noted):

- Tooling: SB2 inventory misses a `global` rebinding; SB4 the summary
  regex takes 1.43 s on a 65,530-character line; SB5 manual checks test
  `startswith(TAGS)` themselves; RR20 no lint for `warnings.warn`,
  `sys.stderr.write`, an aliased `print`; C1a-4 inventory "best kind";
  C2a-L2 the plural lint checks only the next word.
- Messages: C1a-6 every gone-cwd line says "for resolving relative paths",
  also for an absolute path; C1b-1 a top-level `InternalError` prints with
  no code; C1b-2 an `InternalError` in an argparse `type=` reads as an
  invalid value; C1b-3 a relayed control-character path is quoted twice
  (`FILE=''sub/a\x1bb.gguf''`); K3 `file-unreadable` missing from the
  generated models table; K6 a non-mapping card frontmatter is silent; K11
  `ELOOP` still counts as absent; K12 deep frontmatter reads as malformed;
  K19 the raw `model_config` cut has no `over-cap`; K20 a package directory
  gone says `library-missing`.
- Code and docs: RR10c `generate_env_sbom` `Raises:` omits
  `CodedRuntimeError`; RR10f `_counted_entries` duplicates `_entries_text`;
  K1 `Source: Pitloom generator` hand-written; K18 the Hub dataset reader
  raises an uncoded `ModuleNotFoundError` without `huggingface_hub`;
  `docs/python-api.md` is 31,202 B (over the cap); the C2 plan is 34,634 B;
  K15 the 50 MiB Croissant cap is on no docs page.
- Behaviour: C1a-3 a hostile-input test fails under a long `--basetemp`;
  C1a-8 `NAME_MAX_BYTES` counts bytes (not probed on APFS); C1b-5 a
  relative `-o` with the cwd gone fails only at the write; C1b-6
  `discovery_chdir` reads the cwd for an absolute project; C1b-7 library
  `generate(" ./ ")` reads the project, the CLI refuses it; C1b-8 the
  `_watch_size` thread has no handler; C1b-9 `_probe_within` drops a late
  `InternalError`; SB7 no debug line for a Hub request id; C2-5
  `Ann <a@x.org> extra` drops a valid address.

## 9. Gates and reviews (PR 1)

- Gate A: full suite `-n 4` 30,965 passed, 1 failed: C1a-3 (a long
  `--basetemp`), which passes with a short one. Every CI linter clean (ruff,
  flake8, pylint, mypy, pyright, pyrefly, bandit). Branch coverage: no
  changed line missed. Each new regression test fails on a HEAD archive.
- Gate B: manual checks `-j 8`: 620 pass, 0 fail, 29 known, 30 skip.
- Review round 1 (Opus): the condition check skipped a sub-prefix followed
  by a subject; the camel-case name branch matched nothing; a library bool
  said TOML's `true or false`; one working doc quoted a removed line. All
  fixed.
- Review round 2 (Opus): the `ELEMENT=` fallback for an element with no
  spdxId (now stated in the summary and tested); the glossary test checked
  lines only (now prose too); lint gaps (`colors`, `-ing` doublings,
  `favor`, `honor`) and a false positive (`licensed`); a `(KEY=` subject
  escaped the key check; a `KEY=` with no `: ` passed as an acronym. All
  fixed. Not fixed (latent, no such template): a template that opens
  `%(path)s` with no `: ` is never case-checked.
- Mutation (17 mutants on a scratch copy): 15 killed. Two were not:
  - one is equivalent (the mention line's `model=` passed through an
    identity f-string);
  - the folder-in-prose guard is equivalent on today's catalogue, which
    holds no such prose.

  A one-pass `_condition` survived, so the loop it replaced was dropped as
  dead code. Mutants that survived the first pass and were then killed by a
  new case:
  - K16's `repr` (a non-ASCII file name);
  - `model file` probed as a file kind (pinned as an either kind: a model
    input may be a directory).
