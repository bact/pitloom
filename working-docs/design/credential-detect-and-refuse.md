<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-16
-->

# Credentials: detect and refuse, never rewrite

See also: [credential-leak-fixes.md](../implementation/credential-leak-fixes.md)
(what PR 487 built and its tracked gaps),
[message-catalogue-and-skills.md](message-catalogue-and-skills.md) (the
message contract the new codes join).

Status: proposed 2026-11-15, follow-up to PR 487 (merged). PR 1 (PR 489)
built the detector and keeps the strip; the refusal at the persisted sinks
and the override (PR 2) are not built. See "Built in PR 1" below.

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
  use the detector; `load()` still drops the entry, as in PR 487.
- The SBOM strip stays; a value it leaves that the detector refuses gets a
  `credentials-unsafe` line, said once and masked ("which the SBOM states
  as written").
- The masker (`core/url_masking/_mask.py`) hides every finding, tokens
  included, in a value and in a line.
- A timing test per view on adversarial inputs (`test_each_view_is_linear`)
  and 1 MiB runs of the two shapes that were once quadratic.

Not built: any refusal of the SBOM output, merged fragments, the dataset
PURL or a Git URL's secret query value; the change of `load()` to refuse;
the override (fingerprint, flags, `pyproject.toml`, library option); the
Action's `::add-mask::`; `credentials-unsafe/refused`; the JSON path and
fingerprint of a finding.

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
  data). Add one refusal: a Git URL with a secret query value.
- Rejected: warn and accept by default (opt-in security). A published SBOM
  cannot be recalled, a warning scrolls past in CI, and the unsafe outcome
  would be the silent one.

## Sink table

| Sink | Today (PR 487) | Proposed |
|------|----------------|----------|
| SBOM output (`Spdx3JsonExporter.to_json`, after merge and enrichment) | strip + `credentials-unsafe` warning | refuse; every offender in one error |
| Merged fragment ids and references | strip together, `id-collision` error | refuse; with an override pass through unchanged |
| Registry namespace and key | refuse | unchanged |
| `IdRegistry.load()` | drops the entry, next save rewrites the file | refuse and name the entry; the user edits the file |
| Dataset PURL | built from the stripped URL | refuse (nothing safe to build from) |
| Logs, tracebacks, `KEY=VALUE`, `print_error` | mask | unchanged |
| Git URL userinfo | helper, never argv or `.git/config` | unchanged |
| Git URL secret query value | reaches argv and `.git/config` (tracked gap) | refuse |
| Weak names (`code`, `session`, `ticket`, `sid`, `otp`) | kept, truthful warning | `WARNING:` only, never a refusal (OAuth examples in a README must not block a build) |

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
- Global: `--allow-url-credentials`, CLI only, one `WARNING:` per URL. No
  `pyproject.toml` equivalent: a global boolean set once for an example URL
  later lets a real token through silently (precedent: `--allow-build`).
- The library API carries it in the shared options object, not a new
  keyword per entry point. The Action passes both through and starts
  `::add-mask::` for its source inputs.
- Skills explain the fingerprint override and never suggest the global flag
  first.

## Release plan

1. Merge PR 487 (logging, git, registry refusal, catalogue; independent of
   this change). Done.
2. Do not cut 0.25.0 until the detect-and-refuse PR lands. Strip in 0.25.0
   and refuse in 0.26.0 would turn builds that succeeded into failures and
   need two advisory stories.
3. Catalogue codes with `since` 0.25.0 that never shipped (`credentials-unsafe`
   stripped and kept lines, `credentials-unsafe/id-collision`) are retired
   or renamed freely. Add `credentials-unsafe/refused`. Regenerate the
   reference and update every `SKILL.md` that quotes the warning.

## Deleted and added (rough, not measured)

- Deleted: most of `core/url_masking/_strip.py`, `export/_spdx3_strip.py`
  cut from about 180 to about 70 lines, `strip_purl_secrets`, the kept and
  id-collision messages, the registry load-drop, the id and reference
  consistency rewrite. About 500-600 source lines plus tests.
- Added: detector about 150 lines, override plumbing about 120 (CLI,
  pyproject, hook, library, `_matrix_plan.py`), messages about 40, tests
  about 400.

## Traps

- Refusing in the Hatchling hook fails `python -m build` in CI on a README
  example such as `https://user:pass@example.com`. Expect it; the error
  must name the field and the override.
- Detection runs after merge and enrichment (`sbom-enrich` adds README
  prose), at the single writer.
- Fingerprint on the exact serialised string, so it is stable across
  platforms.
- Refusal text must not itself leak; test the raw traceback path.
- `docs/dependency-sources.md` "Known gaps" says "not detected" instead of
  "not stripped".

## Open questions

- Fingerprint length and hash input (whole value or only the credential
  part).
- Whether the token-shape list is a refusal or a warning by default in the
  SBOM. In the ID registry a token is refused since PR 1.
- Whether `loom id import` of a document with a credentialed id refuses or
  skips with the override.
