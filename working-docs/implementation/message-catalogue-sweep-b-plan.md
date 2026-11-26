---
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-25
Last-Modified: 2026-11-26
---

# Message catalogue sweep B ("strict"): plan and rulings

See also: [message-catalogue-sweep-plan.md](message-catalogue-sweep-plan.md)
(sweep A, built), [message-catalogue-sweep-b-evidence.md](message-catalogue-sweep-b-evidence.md)
(measured state, proof table), [message-catalogue-finish-plan.md](../design/message-catalogue-finish-plan.md).

Status 2026-11-25: planned by Opus (read-only), reviewed by Fable (read-only);
the maintainer ruled "go with the recommendations", split B into B1 and B2, and
asked that every sweep A leftover be fixed or carried. Reference tree: main
3be02626 (after #536). Counts are in the evidence page. Built: B1 merged
2026-11-25 as #541; B2 is #542 (one PR, not split into B2a and B2b). The
sweep A leftovers routed to their own PRs merged as #539 (usage-parse hang)
and #540 (GGUF dataset provenance). What is still open is under "Carried to
sweep C or the rescan" at the end.

## Rulings (all taken as recommended)

- **R1** Prune `DETAIL_EXC` to the 21 names that need proof; rename
  `_usage_ast._OverCap` to `_UsageOverCap`. (`_over_cap` is a helper that
  returns `ParameterCountRejected`, not a dead name: dropping it is
  count-neutral, measured 630 -> 630.)
- **R2** D5 is strict from INFO upward, with the kinds `summary`, `detail`,
  `relay`.
- **R3** D5 is on by default; per-test `uncoded_output` markers, a stale
  allowance fails.
- **R4** `line_kind` and `RELAY_PREFIXES` live in `pitloom.messages`; relay
  modules keep their own constant; a drift test checks the two agree.
- **R5** An `UNSHOWN_MESSAGE` `ERROR:` line stays uncoded, allowed by marker.
- **R6** Update the hand-written prose (`docs/messages.md:19`, both skills'
  `references/messages.md:20`): a line without a code is a summary, a `-v`
  `KEY=VALUE` detail, another tool's words after its name, an unexpected
  error's own text, the unshown-message line, or an untagged usage or traceback
  line (Fable 9).
- **R7** Two PRs: **B1** (D4, test-only) and **B2** (D5, D6, per-wheel fix).
  If B2 must obey the 30-file cap, split it: B2a (kinds, classifier, inventory
  rule, D6; strict off) and B2b (strict on, markers, per-wheel fix, docs).

## Amendments from the Fable review

1. **Reader relay (B2).** `extract/_reader_relay.py:93` re-says a captured
   reader record (e.g. `fickling: `) with `extra=None`: copy `pitloom_kind`
   through, and let `line_kind` accept `RELAY_FRAME` before a relay prefix.
   Add `_reader_relay.py` and its test to the Opus M fence.
2. **D4 has three kinds, not two.** `detail` (the exception text reaches a
   coded line), `carrier` (a coded line is said from the payload, e.g. a
   `Cap`; the text is neither required nor forbidden) and `signal` (control
   flow, text never shown). Drop the "text appears nowhere" assertion. Carriers:
   `_OverCap`, `HeaderBlockOverCap`, `ModelOverCap`, `NotAModel`,
   `LockFileRefusedError(cap=)`, and (built in B1) `_Unlistable`: its
   `dir-unlistable` line names the directory and the OS error's `strerror`,
   never `str(_Unlistable)`. `_DuplicateKeyError` is `detail`, not `signal`.
3. **D4 proves sites, not only names.** Add a meta-test: every `raise X` in
   `src/` for a table name sits in a (file, function) the table lists, one
   case per catching path. Several names are mixed per site
   (`InvalidRequirement`, `InvalidMarker`, `LockFileRefusedError`).
4. **Packaging classes.** A spy on `__init__` cannot tell Pitloom's raise from
   packaging's: trigger Pitloom's own refusal (nesting, overlong number) and
   assert the reason text. The `_TOO_DEEP` raises (`pep508.py:169,188`) need a
   monkeypatch to reach.
5. **Allowances.** Marks go on `pytest.param` (a marker on a parametrised test
   fails for parameters that emit nothing); read `own_markers` only
   (`get_closest_marker` also sees a module `pytestmark`); run the B2 suite on
   the 3.14 leg and with `test-all-os` before push.
6. **Rulings still needed inside B2 (maintainer or Opus, recorded in the PR):**
   uncoded argparse wording on a Python whose usage text has no catalogue line
   (`usage_code()` returns `None` by design): declare a kind, not an alarm;
   `InternalError` has no code, so the per-wheel fix prints an uncoded `ERROR:`
   in its test, allowed by marker; a coded line over 65,536 characters
   (`trusted_message` returns `None`) gets its own `overlong` kind.
7. **State the INFO gap.** `Logger.handle` runs after `isEnabledFor`, so INFO
   records never reach the hook while the `pitloom` logger is unconfigured.
   That is a silent gap; D6 `-v` runs cover the rest.
8. **No `pytester`** (not enabled). The stale-allowance logic is a pure
   `check(lines, allowances)` function tested directly, plus at most one
   `runpytest_subprocess` smoke test. Put the strict logic in a new module
   (`tests/_message_drift.py` is 429 lines).
9. **Relay prefix list.** Drift test that the prose names each prefix, or
   generate the list into the message reference.
10. **PR #537 conflict is small.** #537 edits `logging_config.py` lines 26 and
    412-470; B2 edits about 51 and 207-225. Do not touch the import line.

## Sweep A leftovers: routing

| Leftover | Goes to |
| --- | --- |
| Per-wheel `except (ValueError, OSError)` swallowing `InternalError` (`cli/commands/utils.py:282`, `cli/commands/verify_wheel.py:119`) | B2 |
| R0911 in `scripts/message_inventory/_relay.py:relay_kind` | B2 |
| `test_usage_parse` hang (a `sys.settrace` that raises leaves `work` unrun; production hang, not only a flake) | Own tiny PR `usage-parse-settrace-hang`, before B's Gate A |
| GGUF dataset provenance names the temp copy (`extract/scanner.py:207-219`, `_restore_source_name`); changes SBOM output | Own PR `gguf-dataset-provenance-source`, before 0.25.0 |
| loom SDK fragment write not `file-unwritable` (`_loom_active_run.py:460`) | Sweep C |
| `os.path.abspath(script_path)` with the cwd gone (`_loom_active_run.py:153`) | Sweep C (same file as the line above) |
| Floor-docs test reads only the first `licenseid>=` | Sweep C |
| Inventory does not follow tuple unpacking or returned values | Consistency rescan |
| Mutation survivors (`_loom_dataset_meta` merge helpers, `_sbom_io` stdout/replace) | Mutation-backfill PR after the rescan (done: [mutation-backfill.md](mutation-backfill.md)) |

## Size and fences

B1 about 550 lines, 6 files; B2 about 750 lines, about 40 files (26 are
one-line markers). B1 and B2 are file-disjoint (`_scope.py` versus
`_relay.py`).

- **B1 fence:** `scripts/message_inventory/_scope.py`,
  `src/pitloom/extract/_usage_ast.py` (rename), `tests/messages/test_detail_classes*.py`,
  `tests/scripts/message_inventory/test_scope_detail.py`.
- **B2, Opus M (first, sequential):** `src/pitloom/logging_config.py`,
  `messages/_summary.py`, `messages/_line_kind.py` (new), `messages/_relays.py`,
  `messages/__init__.py`, `cli/kv_output.py`, `extract/_licenseid_relay.py`,
  `extract/_reader_relay.py`, `core/_models_wheel_setuptools_relay.py`,
  `extract/ai_model/pytorch.py`, `scripts/message_inventory/_relay.py`, their
  tests, `tests/messages/test_line_kind.py`.
- **B2, then in parallel:** Opus S (strict check: a new test module,
  `tests/conftest.py`, `pyproject.toml` markers only, `tests/_loom_child.py`);
  Sonnet D6 (`scripts/manual_cli_checks/_harness.py`, `_matrix_run.py`,
  `tests/scripts/test_manual_cli_checks.py`); Sonnet W (per-wheel fix in
  `cli/commands/utils.py`, `verify_wheel.py` and their tests). Then Sonnet
  markers for the 24 other files, then docs.

Gates and risks: see the evidence page, sections "Gates" and "Risks".

## Carried to sweep C or the rescan (found in the B2 reviews, 2026-11-25)

- **More `InternalError` swallowing** (read, not run): `_embed_overlay.py:111`
  (per wheel, said as "authors unread"), `assemble/spdx3/deps_pypi.py:192`,
  `extract/scanner.py:431` (per-file usage scan), `cli/_id_target.py:104,184`,
  `cli/id.py:231`, `_loom_model.py:322`,
  `extract/project/_requirements_files.py:295`. Already guarded:
  `scanner.py:338`, `fragment.py:268`, `_fragments_read.py`, `sdist.py:284`,
  `pyproject.py:342`. The roughly 200 broad excepts in `extract/ai_model`
  readers are not ruled on. One rule: re-raise `InternalError` first.
- **Inventory:** `_module_bindings` does not look inside other functions, so
  `global RELAY_EXTRA` rebinding slips (the maskers share the gap).
- **Argparse wording** (amendment 6): a line whose `usage_code()` is `None`
  stays `uncoded` and fails unless marked; check on 3.11-3.14 legs.
- **Summary regex** has two `.+` fields without DOTALL: about 0.4 s at the
  65,536-character cap on a raw-newline line (test harness only).
- **Manual checks outside `universal()`/`expect_tagged()`**:
  `_checks_loom.py:179` and any `_checks_wheel.py` line still test
  `startswith(TAGS)` themselves.
- **A loom SDK fragment write**, `os.path.abspath(script_path)` with the cwd
  gone, the floor-docs test reading only the first `licenseid>=` (sweep A
  leftovers).
- **Hub `log.debug` of `exc.request_id`** (optional, off stderr), from the
  #537 review.
- **`existing_model_path()`** (`cli/commands/utils.py`, used by `enrich`) uses
  `Path.exists()`: a long `ftp://...` target raises an uncoded
  `OSError(ENAMETOOLONG)` on macOS/Linux up to Python 3.13 and reads as missing
  on 3.14 and Windows, so the line differs by OS and Python. Minimal fix: probe
  through `input_exists(given, shown=target)` and treat `ENAMETOOLONG` as
  missing ("a name that cannot exist is absent"), with a regression test.
  Unchanged from main, so not a B2 regression.
- **`src/pitloom/logging_config.py` is 503 lines** after #537 and #542, over
  the soft limit: split it (the one-line and failure-text helpers are one
  cohesive piece).
- **The strict check misses records of a module-, class- or session-scoped
  fixture** (documented): a `pytest_fixture_setup` hookwrapper for those
  scopes would close it.
- **`line_kind` reads `(a log message that could not be shown) [real-code]` as
  `uncoded`**, which is why one test needs an allowance: teach it "fixed text
  plus a catalogued code = coded".

## For sweep C: the PR 17 onward range review (2026-11-25)

A combined review of d6cb054e..ed4dc84c (#524 to #542) in four areas. None
blocks #542; the maintainer ruled "fix the rest in sweep C". Read from the
reviewers' probes, not yet re-run here.

Authors, loom SDK, environment (#524, #527):

- **`input_datasets` given as a string** is iterated per character
  (`_loom_active_run.py`, `_resolve_input_ids_for_output`): `"a.txt"` links
  dataset `a` and warns for `.`, `t`, `x`, `t`; an unhashable entry raises an
  uncoded `TypeError` at the run's exit, no fragment written. Refuse anything
  but `None` or a list/tuple of `str` at the call (`loom_sdk_invalid_value`).
- **A credential in a namespace has two codes**: CLI `--namespace` says
  `option-invalid`, the library `IdRegistry(namespace=)` says
  `credentials-unsafe/registry` (the CLI case is the one in shell history).
- **Wrong-typed loom SDK arguments raise uncoded** `TypeError`/`AttributeError`
  (`set_model(None)`, `path=5`, `add_dataset(5)`, `croissant=5`,
  `set_model_hyperparameters(["a"])`, `data_preprocessing="tok"`,
  `declared_license` on purpose): use `LOOM_SDK_VALUE_LINE`; revisit the
  pr17b-build "internal" ruling.
- **An unknown `dataset_type` is recorded as `text`** silently
  (`_loom_dataset.py`, `getattr(..., text)`); `"__module__"` raises from the
  bindings. Look up the enum's terms only; refuse or warn.
- **One script named two ways** in a fragment: `_get_caller_script_path`
  resolves a symlink, the provenance label does not.
- **A code-built `PitloomConfig(sbom_basename=)`** warns as a
  `[tool.pitloom]` key, and `embed_wheel_sbom` refuses it as `sbom_filename`
  after generating: check it in `PitloomConfig.__post_init__`.
- **A dependency's over-cap author field** does not name the package.
- **`author-invalid` says "not an email address"** for text after a valid
  address; the docs example in `metadata-provenance-authors.md` cannot be
  printed.
- **`loom.run()` with the cwd gone** fails earlier than the carried
  `abspath` item: `Path.cwd()` in `resolve_registry` raises an uncoded
  `FileNotFoundError` at `__enter__`.
- Nits: a repeated `input_datasets` name warns once per repeat; a non-string
  value is quoted like a name; `generate_env_sbom`'s `Raises:` omits
  `CodedRuntimeError`; `iri.namespace_problem`'s docstring order;
  `namespace_invalid`'s plain `ValueError` should be `InternalError`;
  `_counted_entries` duplicates `_fields_authors._entries_text`.

Datasets, text, SBOM output (#533, #534, #540): determinism and SPDX validity
held on every route; the only SBOM change in the range is #540's.

- **`dataset-conflict` is said twice** for one dataset and field (reader and
  assembler each keep a `warned` set; the assembler folds by name, "option
  B"): make the summary true or share one memo per model.
- **The conflict lines name no model**: two lines in a multi-model wheel
  cannot be told apart; add a model subject or narrow the #534 CHANGELOG.
- **The metadata-budget `over-cap` line reads as if the model file is over
  the cap**, and the dropped-key count left the line.
- **A NUL byte in `croissant=`** raises an uncoded `ValueError` from `os.stat`
  (`_extract_utils.py`, `fetch_json` catches only `OSError`/`HTTPException`).

Masking and Hub text (#526, #537): no credential-leak regression (about 480
texts through 20 paths, base vs head).

- **High, for the `TOKEN_RE`/masking PR before 0.25.0: quadratic masker cost
  on `Bearer%20...`** (#526, on main). `%20` is both a separator after a
  scheme and a `%XX` element of `_RUN` (`core/url_masking/_auth_schemes.py`),
  so runs overlap. Re-measured here: `"Bearer%20x." * n` takes 0.07 s at
  8 KiB, 0.28 s at 16 KiB, 1.3 s at 32 KiB (plain `"Bearer x."`: 0.014 s at
  32 KiB); the reviewer saw 204 s for a 200 KB `license` string. Smallest fix
  `%(?!20)[0-9A-Fa-f]{2}` in `_RUN` (a credential holding `%20` is then
  masked up to it), or resume the search after a masked run; add the shapes
  (`Bearer%20x.`, `Basic%20QQ==.`, `Authorization=x%20a.`, `a.Bearer%20`) to
  `_ADVERSARIAL` and correct the "Linear" docstring.
- **Dropping a request id can glue a token to the word before it** (#537):
  `abc(Request ID: a)ghp_...` prints the whole token; the mirror of the
  userinfo hazard the docstring guards. Mask, drop, mask again.
- **`one_line` collapses white space before masking** (pre-existing):
  `https://user:S3cr\n3tPw99x@h` keeps `3tPw99x`, as `excerpt` no longer
  does; fix with the item above (mask, collapse, mask).
- Nits: a header credential after a line break is missed on multi-line paths;
  the `_auth_schemes.py` "Linear" paragraph and `loggable()`'s `kv_line`
  claim are stale.

Catalogue machinery and concurrency (#536-#542): ratchet and reference
checks pass; #538's guard and #539's fix do not interact (40 runs, 3.10,
coverage, no hang).

- **An empty path prints an uncoded `ERROR:`** (pre-existing): `loom wheel ""`
  (also `verify-wheel`, `validate-wheel`, `embed-wheel`) says `file='' is not
  a file`, re-measured here. `messages/_templates.py` `written()` raises a
  plain `ValueError` for a value outside its field's shape, and the ratchet
  leaves `messages/` out. Treat `""` as `input-not-found`; make `written()`,
  `Message.line_for()` and the field writers raise `InternalError`; test `""`
  on each wheel command. `report_wheel_failure`'s "every per-wheel ERROR line
  carries a code" holds only for `OSError`. Also `loom enrich ""` reports `.`.
- **A helper with one uncoded return branch counts as coded**:
  `extract/ai_model/reader.py` `refusal_error()` returns a plain `ValueError`
  when an LFS pointer's re-read fails (reached with a patched
  `read_lfs_pointer`; a race in practice). Raise `file_unreadable_error`; judge
  each return expression in the inventory.
- **Ratchet blind spots** (rescan): a logger outside the `LOGGER_NAME` regex,
  `warnings.warn`, `sys.stderr.write` outside `logging_config.py`,
  `raise <local var>`, `getattr(log, "warning")`, an aliased `print`; a
  positional upper-case constant from `pitloom.messages` counts as coded;
  `extra={"pitloom_code": None}` too. In `src` today only
  `_models_wheel_types.py:358` (benign) and the `refusal_error` branch. A lint
  test for the first four is cheap.
- Nit: `_coded.py` `STATIC_CALLS` omits `CodedOSError` (fails safe).

