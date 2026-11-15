<!--
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
Created: 2026-11-15
Last-Modified: 2026-11-15
-->

# Credential leak fixes (plan)

See also: [message-catalogue-and-skills.md](message-catalogue-and-skills.md),
`pitloom.core.url_masking` (the maskers), `pitloom.logging_config` (the sink).

Status: BUILT 2026-11-15 (uncommitted), awaiting review. One PR, before
catalogue PR 7. Plan approved by the user, strip form: drop the parameter.

## Root cause

Masking is per call site. The sinks (log formatter, `print_traceback`,
`print_kv`, `provenance_*`) only escape control characters, so any forgotten
site leaks. Probe on base (2026-11-15): `escape_controls("x
https://u:SECRET@h/p?token=SECRET")` returns the text unchanged;
`masked_given_path("alice:SECRET@host:o/r")` returns it unchanged;
`sanitize_url_credentials` leaves `?code=`, `?session=`, `?ticket=` and
`token%3D=` values; `_probe_url("https://u:SECRET" "host:99x/r")` raises
`Invalid URL: Port could not be cast ... 'SECREThost:99x'`.

## Decisions already made

- Separate PR, first. `since` 0.24.1 for new catalogue entries.
- User-written project data in the SBOM: STRIP userinfo and secret query
  values, `WARNING:` once per value.
- Registry namespaces and keys: REFUSE, not mask.

## Design

### A. Sink masking (items 4, 5, 6, 7, 11)

1. `escape_controls` (used by `_OneLineFormatter`, `print_traceback`)
   also runs `masked_given_path(text, line=True)`. Every log line,
   traceback line and `ERROR:` line is then masked whatever the site.
2. `kv_line` (so `print_kv`, stdout) masks each value the same way; stdout
   `KEY=VALUE` of paths (`OUTPUT_PATH`, `ID_REGISTRY_PATH`, fragment `PATH=`)
   is fixed by this one change. Check `-o -` SBOM stream is untouched (it
   is not `print_kv`).
3. Exception text re-raised to library callers (hook `plugins/hatch.py:369`,
   `_config_parse.py:311`, `fragments.py:511`): mask where the exception is
   built from a URL-bearing value, since a library caller never passes the
   sink. Poetry warnings (`_poetry_requirements.py:121`,
   `_models_wheel_types.py:82`) go through the sink fix; add direct masking
   where text is stored (not logged).
4. `failed_error` (`_http_errors.py`, `messages/_field_writers.py:100`) and
   `warn_instead` mask the free-text `failure`.
5. Cost: masking each log line is linear (patterns are bounded); keep the
   no-`://` fast path.

### B. Masker gaps (items 10, 11)

- Add secret names `code`, `session`, `ticket`, `sid`, `otp` (whole-name
  match only, as `key`/`auth` today); decode `token%3D=` names (name is a
  percent-encoded `token=`).
- scp-like `alice:SECRET@host:o/r`: treat `user:pass@host:path` with a
  colon in the user part as userinfo; mask in `masked_given_path` and
  reject nothing (a local path stays a local path elsewhere). Risk: a
  relative path `a:b@c:d` is masked; accepted like the existing
  `backup:/u@h/x` rule.
- Whitespace/newline in password: `sanitize_url` already handles a
  whole-URL text; add case for line mode documented as out of scope
  (RFC 3986 percent-encodes it). Raw `/` likewise stays out of scope,
  recorded.
- Plain `http://` with credentials: new `WARNING:` (credentials sent in
  clear), catalogued.

### C. Git (items 1, 2, 11)

1. `_SAFE_CONFIG` gains `credential.helper=` (empty value resets the helper
   list, so no keychain / `~/.git-credentials` store), `credential.interactive=false`,
   `core.askPass=`; env `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=` set to a
   no-op, `SSH_ASKPASS` likewise; scrub inherited `GIT_ASKPASS`.
2. Credentials out of argv (`git.py:341,392,440`): strip userinfo from the
   URL in argv; pass `PITLOOM_GIT_USER` / `PITLOOM_GIT_PASS` in the child
   environment and an inline helper
   `-c credential.helper=!f() { echo username=$PITLOOM_GIT_USER; echo password=$PITLOOM_GIT_PASS; }; f`
   after the empty reset. The helper is ephemeral: nothing stored. `ps`
   shows no secret (environment of the child is not world-readable on
   Linux/macOS). **Windows**: git runs the `!` helper with its bundled sh;
   needs a probe on Windows (cannot run here: dry-run + `platform` marker).
   Fallback if the helper proves unportable: document that argv carries the
   credential, keep it out of everything else. Decision for you below.
3. Clone dir: write the remote URL without userinfo from the start
   (`url_without_credentials`), so a killed run leaves no password in
   `pitloom-git-*/.git/config`.
4. `_probe_url`: build the error from the host only; never interpolate
   `exc`. Mask the URL given to the "Invalid URL" message too.

### D. Croissant / dataset (item 3)

- `_extract_utils.py:255-256`: error uses `masked_given_path`.
- `croissant.py:256-258,322-341`: provenance, `externalRef`,
  `downloadLocation` get the stripped URL (E below).

### E. SBOM strip (item 9)

One helper `pitloom.core.url_masking.strip_url_secrets(url) -> (clean,
changed)` (userinfo removed, secret-named values removed with the `name=`
kept as `name=` empty? -> dropped parameter, decision: drop the whole
parameter so no `***` forges a value). Applied at one shared point per
source rather than per call site:

- requirements/direct-URL dependencies: `core/requirements.py` parse result
  (`provenance_note` then sees the clean text);
- project URLs: `read_project` result and Hatchling `metadata_from_hatchling`
  before `build()`; so setup.cfg/setup.py/pyproject/hatch routes converge
  (CLAUDE.md "route through one shared mechanism");
- installed-dependency metadata (`deps_installed.py`, `deps.py`,
  `deps_originator.py`), model-card `base_model`/arXiv (`_ai_package.py`).

`WARNING:` catalogued, once per distinct value: `URL=<masked>: credentials
removed from the SBOM; ...`. Drift guard: a test walks a fixture SBOM built
from a planted-secret project on every route (CLI, library, hook) and asserts
the secret is absent from the serialised document.

### F. Registry (item 8)

- `namespace_problem` (`core/iri.py:137-150`) gains: userinfo, secret-named
  query value -> new `NAMESPACE_PROBLEMS` entry + catalogued message. Refused.
- `loom id generate -e URL` refuses a URL with credentials (error code
  `id-registry/key-credentials`), key never stored.
- Conflict: PR #486 touches `core/iri.py`, `id_registry/`,
  `messages/_registry_*.py`. Keep F small, last, rebase after #486 merges.

### G. Misc

- `.gitignore`: add `.git-credentials`, `.netrc`, `.pypirc`.
- Action (`action.yml:524-561`): confirm it benefits from A (annotates tagged
  stderr lines); no change expected. `skills/*/SKILL.md`: grep for quoted
  messages; update if a message text changes.
- Side observation (a): namespace `ids.example` beside
  `https://spdx.org/spdxdocs/demo-<uuid>`; (b) Person + GPL text for a
  project named `demo`: investigate with a scratch project; report, fix only
  if confirmed.

## Tests (compact, parametrized)

- Sink: parametrize secret shapes x sinks (formatter, traceback, `print_kv`,
  `print_error`, `failed_error`, `warn_instead`); test a newline in value.
- Masker gaps and scp form: parametrized table; adversarial linear-time test.
- Git: real subprocess against a fake `git` shim on `PATH` recording argv,
  env and `-c` args: assert no secret in argv, helper reset present, no
  `.git/config` password; `platform` marker; Windows dry-run via
  `PureWindowsPath` where paths matter.
- SBOM: planted-secret project, all routes, assert absent plus WARNING once.
- Registry: refuse cases; secret never written to the registry file.
- Each regression test is run on the base tree and must fail there.

## Final probe (Done criterion)

Plant `PLANTSECRET` in: git URL, `-e`, namespace, pyproject URLs and direct
dependencies, croissant URL, config paths; run CLI (default and `-v`), hook,
library; grep stdout, stderr, SBOM, registry, git shim log: zero hits.

## Out of scope (notes)

Percent-encoding `/` or whitespace in line mode; secrets in file contents
the user points us at (README text); `ps` exposure on Windows if the helper
fallback is used.

## Review plan

Opus agent reviews this plan; then Opus review rounds on the diff; haiku for
grep sweeps of call sites. Mutation testing on the maskers and git run.

## As built, and deferred

Built as planned except:

- Message family `credentials-unsafe` (`since` 0.24.1), not `url-credentials`:
  the catalogue names a family `<subject>-<condition>`. Exported from
  `pitloom.messages.network`; helpers in `pitloom.messages.url_credentials`.
- The SBOM strip is one pass over the decoded `@graph` in
  `Spdx3JsonExporter.to_json` (every surface passes it), not per source.
  `spdxId`/`@id` values are skipped.
- Namespace refusal is in `require_namespace_iri` (this base has no
  `namespace_problem`/`NAMESPACE_PROBLEMS`); an argparse `--namespace`
  error prints `[option-invalid]`, not the new code. Conflicts with PR #486
  (`core/iri.py`, `_registry.py`) to resolve on rebase.
- Git: one `GitRunner.run` mechanism; the runner keeps the credentials for
  later calls (`fetch origin`). `.git/config` now never holds the password.
- Side observations: (a) not reproduced without a registry; (b) a scratch
  project `demo` gets no Person or licence text (probed 2026-11-15, no
  installed `demo`).

Deferred (not fixed here):

- Plain `http://` URL with credentials: no warning yet.
- Hatchling hook re-raises the original exception, so Hatchling's own
  traceback prints its text; producers mask where they build a URL-bearing
  message, the log sink masks the rest.
- A secret query value in a Git URL stays in git's argv (userinfo does not).
- Windows: the `!` helper needs git's bundled sh; not run on Windows.
- A password with a raw `/` or (in a line) white space is not masked
  (RFC 3986 percent-encodes both).
- pyrefly could not run in this worktree (its path is ignored by
  `.gitignore`); run it from the repository root before merge.

## Review round 2 (Opus review of PR head 5846c2a, Fable review)

Decided with the user:

- An element id that holds credentials (a third-party fragment's) and every
  reference to it are stripped to the same new id in one pass
  (`_strip_url_credentials`); ids minted by Pitloom never hold credentials
  (a namespace with credentials is refused), so registry ids and emitted ids
  agree. Test: `test_the_stripped_url_warning_is_said_once_per_url`.
- Weak names (`code`, `session`, `ticket`, `sid`, `otp`) are kept as written
  in the SBOM, the namespace and an `-e` key; the warning, the catalogue and
  `docs/dependency-sources.md` say they are kept. They are masked in logs.
- `sort_key`, `primary-key` and the like are not secrets: the SBOM strip
  matches whole names, `*_token`/`*_secret`/... endings and named `*_key`
  forms (`api_key`), not every `_key`.
- The scp form (`alice:pw@host:o/r`, also `host:/abs`) is refused as a
  namespace or an `-e` key (`holds_url_credentials`), skipped on import
  (`_unrecordable` in `_harvest.py`), not stripped from SBOM text (it has no
  `://`, and `python:3.11@sha256:...` would be hit).
- The git password is in the environment of `clone`, `fetch` and `ls-remote`
  calls only.

Recorded, not fixed here:

- Masker gaps: `/` in a password, `@[::1]` hosts, `state=`, `Policy=`
  (CloudFront), `oauth_verifier` only by its `verifier` ending.
- A user name alone on an ssh URL is kept in the SBOM (`git@`), while a
  token used as that user name is masked in logs and kept in the SBOM.
- `IdRegistry.register()` raises for a credential key, also inside a user's
  program that uses `pitloom.loom`.
- Windows: the real-git helper test is POSIX only; the `!f()` helper needs
  git's bundled sh (Git for Windows ships it) and is unverified there.
- Namespace mixing (reproduced by the review): one element on
  `ids.example/ns` and eight on `spdx.org/spdxdocs/demo-<uuid>` in one SBOM.
  Not related to credentials; needs its own investigation.
- Mutation testing of the new rules and pyrefly (it ignores this worktree
  path; run from the repository root with `--use-ignore-files=false`).
