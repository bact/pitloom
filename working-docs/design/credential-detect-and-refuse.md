<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-16
-->

# Credentials: detect, warn or refuse, never rewrite

See also: [credential-leak-fixes.md](../implementation/credential-leak-fixes.md)
(what PR 487 built and the gaps still tracked),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the
message contract the new codes join).

Status: proposed 2026-11-15, follow-up to PR 487 (merged). PR 1 (PR 489,
merged) built the detector; PR 2 (#490, merged 2026-11-16, unreleased) built
the check at the persisted sinks, the two modes and the per-value override,
and deleted the strip. PR 3 (#491, merged 2026-11-16, unreleased): the Action
inputs and masks, the Git hardening, detector and masker extras ("Built in
PR 3" below).

## Decision record: warn by default (2026-11-16)

User decision, reversing "Decision" below for the default: **Pitloom runs in
CI and build hooks and must not break them by default.** Credential handling
is a policy with two modes:

- `warn` (default): detect, say one loud `WARNING: ...
  [credentials-unsafe/written]` per value (masked value, element, pointer,
  fingerprint, and how the surface turns `refuse` on), write the SBOM as it
  is, exit 0. The hook does not fail the build.
- `refuse` (opt in): what PR 2 first built: one `ERROR:` per value, a count
  line, no SBOM, registry unchanged, exit 1.
- Setting: `[tool.pitloom] url-credentials = "warn" | "refuse"` (`setup.cfg`
  too; another value is `option-invalid`), `--refuse-url-credentials` (parent
  parser, `merge`, `loom id generate`/`import`), library
  `CredentialPolicy(refuse=True)` and `PitloomConfig.url_credentials`, through
  the existing cascade (`ConfigOverrides.credentials`; the flag turns
  `refuse` on, never off). `to_json()`'s default policy warns: a forgotten
  call site warns rather than fails.
- Fingerprint accept stays: in `refuse` it lets a value through; in either
  mode an accepted value gets the quieter `credentials-unsafe/accepted` line
  instead of the `written` one.
- Removed: the global `--allow-url-credentials`, `CredentialPolicy.allow_all`,
  `PitloomConfig.allow_url_credentials`, the `allow-url-credentials` key
  (now an ordinary unknown key) and `config-unsafe/cli-only`. With `warn` the
  default, an allow-all switch has nothing left to do.
- Registry: a key given (`register()`, `id generate -e`) and a registry
  file's entries follow the mode (`warn`: stored or loaded with a `WARNING:`;
  `refuse`: refused as before; `IdRegistry(refuse_credentials=...)`). A
  credentialed namespace is refused in both modes (it ends up in every id).
  Harvest and `id import` skip a credentialed element in both modes (it never
  breaks a run). `loom id` reads the project's `url-credentials` only without
  `-o`, as for the registry location. A registry passed in to a run that
  refuses is turned to `refuse` (`IdRegistry.refuse_mode()`, entries
  checked).
- The `credentials-unsafe` family moved to its own reference page (URL
  credentials), as the network page passed the size limit.
- Release: 0.25.0 is no longer blocked by this change (item 2 of "Release
  plan" is moot: the default no longer turns a passing build into a failure).

The text below describes PR 2 as first built (refuse by default); where it
says "refused", read "refused in the `refuse` mode, warned of in `warn`".

## Built in PR 2

- **SBOM refused, never rewritten** (`export/_spdx3_credentials.py`,
  `check_graph_credentials`), last in `Spdx3JsonExporter.to_json`, so on
  every surface (CLI, library, Hatchling hook, `loom.run` fragments,
  `merge`, `enrich`), and on the file `embed-wheel --sbom` embeds. One
  `ERROR: URL=<masked>: holds a credential (<element> <pointer>,
  sha256:<16 hex>); remove it from the source, or accept this value ...` per
  distinct value, in graph order, the end naming how the surface accepts it
  (CLI `with --accept-url-credential <fp>`, Hatchling hook `by listing it in
  [tool.pitloom] accept-url-credentials`, library `with
  credentials=CredentialPolicy(accepted=["<fp>"])`; a `credential_advice`
  context the entry point sets), then a closing count naming no URL (`<n>
  URL value(s) in the SBOM hold credentials; the SBOM is refused`, the same
  on every surface); exit 1, no SBOM written. The hook's lines start
  `Pitloom build hook: `. The raised error's text and `args` name no URL
  and it has no context.
- **What is read**: the fields of `URL_FIELDS` (every `anyURI` field of the
  SPDX 3.0.1 model, ids and namespaces with the `embedded` reading, an
  `identifier` of any type, and the 40 reference fields (`createdBy`,
  `suppliedBy`, `creationInfo`, `from`, `to`, `subject`, `rootElement`,
  `element`, ...) read as ids when they hold one; a drift test keeps the
  list complete), each as a whole value; an id is also read percent-decoded.
  Pitloom's own provenance is read too, as whole values: every string of a
  JSON statement whose `schema` starts `https://pitloom.dev/` (a field
  provenance note split into its notes) and each segment (`Note`, `Value`)
  of each entry of a `Metadata provenance:` comment line (the same value, so
  the same fingerprint). Any other comment, a name, a description or other
  prose is not.
- **Weak** values (`code`, `session`, `ticket`, `sid`, `otp`, a `_key`
  name that is no kind of secret key, an `ssh` account name) warn
  (`credentials-unsafe`, "the SBOM states it as written"), never refuse.
  Token shapes refuse in the SBOM, as in the registry.
- **Fingerprint** (`core/credential_policy.py`): `sha256:` and the first 16
  lowercase hex digits of the SHA-256 of the whole field value as it stands
  in the output (UTF-8, `surrogatepass`); an accepted entry may be 16 to 64
  digits (a prefix of the full digest); uppercase is refused, and a bad
  entry is never quoted (it may be a pasted credential). The **pointer** is
  RFC 6901 within the element; for a provenance note it goes on into the
  statement's JSON (`/statement/fields/<field>/note`) or the comment entry
  (`/comment/<field>/note`).
- **Override**: `--accept-url-credential FP` (repeatable, every generating
  command and `merge`), `[tool.pitloom] accept-url-credentials = [...]`,
  library `PitloomConfig(accept_url_credentials=...)` or a `credentials=`
  `CredentialPolicy`; the CLI list adds to the config's, never replaces it.
  `setup.cfg` holds the list as `[tool:pitloom] accept-url-credentials` (one
  per line, or comma or whitespace separated; a bad entry is named by its
  position). `PitloomConfig` rejects a bad fingerprint when built. An
  accepted value is stated with `WARNING: ...
  [credentials-unsafe/accepted]`; an accepted fingerprint matching no value
  warns once per fingerprint and SBOM (`option-no-effect`, `FINGERPRINT=`,
  naming the SBOM's `SpdxDocument` id, else its first element); a fingerprint
  an enrichment fragment inherits from the project's list
  (`CredentialPolicy.inherited`) is never said stale. (A global
  `--allow-url-credentials` with a `config-unsafe/cli-only` warning for the
  file key was built first, then removed by the 2026-11-16 decision record.)
  The Hatchling hook reads the `pyproject.toml` settings only; `embed-wheel --sbom` and `merge` (`generate_merged_sbom()`
  takes only `credentials=`) read the run's flags only (no project
  configuration applies to a given SBOM). The Action's model mode reads no
  project file, only the `config` input's.
- **Duplicate keys**: `read_given_sbom` (`embed-wheel --sbom`, `loom id
  import`) refuses a JSON object that names a key twice (`sbom-invalid`):
  readers disagree on which value counts, so what is checked could differ
  from what is embedded. `merge` fragments are not read this way.
- **Registry**: `IdRegistry.load()` and `rebase()` refuse a file with a
  credentialed entry or namespace and leave it as it is (`ERROR: ... ID
  registry file '<path>' is not loaded; remove the entry`); `loom id import`
  still skips such an element with a `WARNING:` and takes no override.
- **Deleted**: `core/url_masking/_strip.py` (its URL scanner moved to
  `_urls.py`), `export/_spdx3_strip.py`, `strip_purl_secrets` and the
  stripped PURL of `build_generic_purl` (the dataset PURL is built from the
  URL as given and refused with it), the stripped, kept and unremoved
  lines, `credentials-unsafe/id-collision` and the id and reference
  rewrite, the registry load-drop.
- Tests: `tests/test_credential_surfaces_accept.py` (the override on each
  surface), `tests/test_credential_deep_query_surfaces.py` (a 1000-`?` URL
  refused, then accepted by its fingerprint),
  `tests/export/test_spdx3_credentials*.py`,
  `tests/core/test_credential_policy.py`,
  `tests/cli/test_cli_credential_flags.py`.

## Built in PR 3

Built 2026-11-16 (branch `credential-hardening`). Detail and evidence:
[credential-leak-fixes.md](../implementation/credential-leak-fixes.md)
("Git argv spy (PR 3)") and
[credential-leak-fixes-pr3-detector.md](../implementation/credential-leak-fixes-pr3-detector.md).

- **The Action**: inputs `url-credentials` (`warn` default; `refuse` adds
  `--refuse-url-credentials`) and `accept-url-credentials` (commas or line
  breaks; each entry becomes `--accept-url-credential FP`, a malformed entry
  fails the step and is not printed). `scripts/action/url-credentials.sh`
  prints `::add-mask::` first for the URL-capable inputs (`project-path`,
  `model`, `args`, `accept-url-credentials`: user information, password,
  query, fragment, whole; a piece under 6 characters is not masked). GitHub
  echoes a step's inputs before it runs, so only `${{ secrets.X }}` is hidden
  from that echo.
- **Git**: a Git URL's `?token=` was never a gap: the query and fragment are
  dropped before the clone URL is built, so git never receives them
  (`tests/extract/remote/test_git_credentials_argv.py` spies on every git
  argv and environment and reads the clone's files). Fixed: the scheme
  refusal printed an scp-style password; a NUL in the user information
  and a host no host name spells are refused before git runs; the git
  environment scrub drops more variables.
- **Detector and masker**: decoded query and fragment values, a password
  starting with `?` or `#`, third-party log masking (`urllib3`, `requests`),
  wheel-pattern handling (`glob` recursion, bracket names).

## Built in PR 1 (PR 489)

- The detector: `find_url_credentials` and `holds_url_credentials`
  (`core/url_masking/_detect.py`, reading the hits of `_hits.py` and the
  token shapes of `_tokens.py`). It reads a URL-typed value as a whole
  (a URL, a PEP 508 requirement with a direct reference, a whole scp-style
  address, a PURL with its qualifiers and subpath) and never prose (user
  ruling 2026-11-15); an identifier Pitloom stores is read for a URL or a
  token anywhere in it. Detail: "Detector sweep (PR 1)" in
  [credential-leak-fixes.md](../implementation/credential-leak-fixes.md).
- A `Finding` holds its kind, its view (left out of `repr`) and the masked
  text; a weak name or an accepted `ssh` account name is a weak finding,
  never refused.
- The registry refusals (namespace, key, element id) and `IdRegistry.load()`
  use the detector; `load()` still dropped the entry, as in PR 487 (PR 2
  refuses).
- The SBOM strip stayed; a value it left that the detector refuses got a
  `credentials-unsafe` line (PR 2 deleted both).
- The masker (`core/url_masking/_mask.py`) hides every finding, tokens
  included, in a value and in a line.
- A timing test per view on adversarial inputs (`test_each_view_is_linear`)
  and 1 MiB runs of the two shapes that were once quadratic.

Not built in PR 1: everything under "Built in PR 2" above.

## Corrections after PR 1

Where this plan and the built detector disagree, the code holds:

- Token shapes are read inside a URL-typed value (a path segment, a query
  value, the user information, a PURL qualifier or subpath) and in a stored
  identifier, not "anywhere in the graph": prose is out of scope by the
  ruling. The masker hides tokens anywhere in displayed text.
- The detector does not share every reading, and so every gap, of the
  strip: it reads white space and quotes inside a URL field, any scheme
  after one `/` or after backslashes (`s3:/u:p@h`), a dotless scp-style
  address as a whole value (`alice:pw@host:repo`, `build:42@ci:linux`),
  a PURL subpath, and no longer refuses a weak name nested in a weak name.
  It keeps others (`state=`, `Policy=`, a `/` in a password, a user-less
  scp address): "Tracked, not fixed here" in credential-leak-fixes.md.
- A PURL qualifier is decoded at most 5 times (`PURL_DECODE_ROUNDS`), not
  to a fixed point; a value a sixth decode would still change is a
  `nesting` finding.
- Size: `_hits.py`, `_detect.py`, `_mask.py` and `_tokens.py` add about
  740 source lines, against the estimate of 150 below.

## Why

PR 487 strips credentials from user-written data (SBOM, ids, references)
and masks logs. Seven review rounds each found a new fault in the previous
round's fix. Most faults were in the rewriting, not the detecting: prose
corruption, scp-shaped strings rewritten (`build:42@ci:linux`), a trailing
comma swallowed, an `a=1` moved inside another value, a PURL qualifier
decoded one level too far, a weak name nested in a weak name refused. The
rest were hangs (recursion, quadratic scans) in the shared parser.

A rewriter has to find the exact span and leave everything else intact.
A detector only has to answer "could this be a credential", and may
over-trigger: a false positive costs one flag, a false negative is the only
real danger.

## Decision

Never rewrite persisted data automatically.

- **Persisted sinks** (SBOM output, registry namespaces and keys, merged
  third-party fragments, `load()` of a registry file): detect, `ERROR:` and
  refuse by default. A per-value override accepts a reviewed false positive
  (opt-out security).
- **Displayed sinks** (logs, tracebacks, `KEY=VALUE` lines, error text):
  keep best-effort masking. Corruption there is harmless.
- **Git**: keep the ephemeral per-origin helper (transport, not rewritten
  data). (A refusal of a secret query value was planned; PR 3 found the query
  never reaches git, so none was added.)
- Rejected: warn and accept by default (opt-in security). A published SBOM
  cannot be recalled, a warning scrolls past in CI, and the unsafe outcome
  would be the silent one.

## Sink table

| Sink | PR 487 | Proposed | PR 2 |
|------|--------|----------|------|
| SBOM output (`Spdx3JsonExporter.to_json`, after merge and enrichment) | strip + `credentials-unsafe` warning | refuse; every offender in one error | built (one line per value, then a count) |
| Merged fragment ids and references | strip together, `id-collision` error | refuse; with an override pass through unchanged | built |
| Registry namespace and key | refuse | unchanged | unchanged |
| `IdRegistry.load()` | drops the entry, next save rewrites the file | refuse and name the entry; the user edits the file | built (`rebase()` too) |
| Dataset PURL | built from the stripped URL | refuse (nothing safe to build from) | built (refused at the SBOM check) |
| Logs, tracebacks, `KEY=VALUE`, `print_error` | mask | unchanged | unchanged |
| Git URL userinfo | helper, never argv or `.git/config` | unchanged | unchanged |
| Git URL secret query value | reaches argv and `.git/config` (tracked gap) | refuse | not needed (PR 3): the query is dropped before git is given the URL |
| Weak names (`code`, `session`, `ticket`, `sid`, `otp`) | kept, truthful warning | `WARNING:` only, never a refusal (OAuth examples in a README must not block a build) | built |

## Detector

- Same parsing as today: where user information ends (`_userinfo.py`),
  secret versus weak names (`_params.py`), URL-field versus free-text mode,
  PURL qualifiers decoded to a fixed point. Its false negatives are
  therefore today's tracked gaps; it does not fix them.
- Gains: fail closed on the masker's widest reading; flag known token shapes
  anywhere in the graph (`ghp_`, `glpat-`, `hf_`, `AKIA`, `xox`), which a
  rewriter could not do without corrupting prose.
- Keeps the bounds: nesting cap (`MAX_QUERY_MARKS`), linear scans, no
  recursion. Add a 1 MiB timing test per scan.
- The detector reports a JSON path, the masked value and a fingerprint of
  the exact serialised string. It never puts the raw URL in an exception
  text, `args` or `__cause__` (Hatchling prints a raw traceback).

## Override

- Per value: `[tool.pitloom] accept-url-credentials = ["sha256:<prefix>"]`
  and `--accept-url-credential <fingerprint>` (repeatable). The error prints
  the fingerprint. Fits CLI > pyproject > defaults and stays deterministic.
- Global: `--allow-url-credentials`, CLI only, one `WARNING:` per URL.
  Built in PR 2, then removed (decision record 2026-11-16: the `warn`
  default makes it moot).
- The library API carries it in the shared options object, not a new
  keyword per entry point. The Action passes both through and starts
  `::add-mask::` for its source inputs (built in PR 3).
- Skills explain the fingerprint override and never suggest the global flag
  first.

## Release plan

1. Merge PR 487 (logging, git, registry refusal, catalogue; independent of
   this change). Done.
2. Do not cut 0.25.0 until the detect-and-refuse PR lands. Strip in 0.25.0
   and refuse in 0.26.0 would turn builds that succeeded into failures and
   need two advisory stories. Lifted once PR 2 merges.
3. Catalogue codes with `since` 0.25.0 that never shipped (`credentials-unsafe`
   stripped and kept lines, `credentials-unsafe/id-collision`) are retired
   or renamed freely. Add `credentials-unsafe/refused`. Regenerate the
   reference and update every `SKILL.md` that quotes the warning. Done in
   PR 2 (`credentials-unsafe/accepted` added too, then
   `credentials-unsafe/written` for the `warn` mode; `config-unsafe/cli-only`
   was added and removed again; `sbom-generate`'s
   `references/url-credentials.md` holds the skill flow).

## Deleted and added (rough, not measured)

- Deleted: most of `core/url_masking/_strip.py`, `export/_spdx3_strip.py`
  cut from about 180 to about 70 lines, `strip_purl_secrets`, the kept and
  id-collision messages, the registry load-drop, the id and reference
  consistency rewrite. About 500-600 source lines plus tests.
- Added: detector about 150 lines, override plumbing about 120 (CLI,
  pyproject, hook, library, `_matrix_plan.py`), messages about 40, tests
  about 400.
- Measured in PR 2 (source lines): deleted `_strip.py` (386) and
  `_spdx3_strip.py` (208); added `_spdx3_credentials.py` (339),
  `credential_policy.py` (196), `_parser_credentials.py` (90) and `_urls.py`
  (220, the scanner kept from `_strip.py`).

## Traps

- Refusing in the Hatchling hook fails `python -m build` in CI on a URL field
  value such as `https://user:pass@example.com`: why `refuse` is opt in
  (2026-11-16). The error must name the field and the override.
- Detection runs after merge and enrichment (`sbom-enrich` adds README
  prose), at the single writer.
- Fingerprint on the exact serialised string, so it is stable across
  platforms.
- Refusal text must not itself leak; test the raw traceback path.
- The user-facing gaps say "not detected", not "not stripped" (PR 2: "Not
  detected" in `docs/url-credentials.md`).

## Open questions (settled in PR 2)

- Fingerprint length and hash input: 16 hex digits printed (16 to 64
  accepted) of the SHA-256 of the whole field value, not of the credential
  part (a credential part would need the detector's span, and a value
  changed anywhere must be reviewed again).
- Token shapes refuse in the SBOM, as in the ID registry.
- `loom id import` of a document with a credentialed id skips the element
  with a `WARNING:`; it takes no override.
