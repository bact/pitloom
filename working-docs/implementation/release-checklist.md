---
Created: 2026-08-11
Last-Modified: 2026-09-30
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Release checklist

Steps for cutting a Pitloom release, maintainer-facing. Distinct from
[CONTRIBUTING.md](../../CONTRIBUTING.md)'s per-PR checklist -- this is
the release-cutting process itself, run once per version bump.

## 1. Pre-tag verification (local)

CI already covers most of this list on the release PR -- check the green
run before repeating it locally. Job-name map (`gh pr checks` shows job
names, not workflow names): pytest = `Test on Python ...`; mypy/pyright/
pyrefly = `Type checking`; ruff, **pylint and flake8** = one job, `Ruff
(Lint & Format)`; plugin validation = `claude plugin validate`; version
fields = `Check version fields agree`; `python -m build --wheel` + PEP 770
embed + `verify-wheel`/`validate-wheel` on Pitloom's own wheel =
`Python X on <os>` (`build.yml`, ubuntu/windows/macos); the hook against
the Hatchling floor and latest = `Hook on Python X / Hatchling Y`
(`hatch-integration.yml`). Docs-only commits skip most workflows via
`paths-ignore`.

- [ ] `pytest tests/ -q` -- 0 failed.
- [ ] `mypy examples/ src/ tests/` -- clean.
- [ ] `ruff check examples/ src/ tests/` and `ruff format --check
      examples/ src/ tests/` -- clean.
- [ ] `pylint src/ tests/ examples/` -- 10.00/10 (`--ignore-paths` any
      stray local `.venv` under `examples/` -- see
      [summary.md](summary.md) for why one can exist untracked).
- [ ] `scripts/` is not linted by CI: run ruff, mypy, pylint, flake8,
      `shellcheck -x scripts/action/*.sh` and `actionlint` on it by hand
      when it changed since the last tag.
- [ ] `claude plugin validate .claude-plugin/plugin.json` and
      `.../marketplace.json` -- both pass.
- [ ] Version string consistent across every file that carries one:
      `pyproject.toml`, `src/pitloom/__about__.py`,
      `.claude-plugin/plugin.json`, `CITATION.cff`, `codemeta.json`,
      `README.md`, `action.yml`, `docs/index.md`, `docs/github-action.md`
      (also `pip install pitloom==<version>` in its registry recipe),
      `working-docs/implementation/github-action.md`. Check with
      `grep -rn "<old-version>"` across those files -- anything left
      over is a missed bump. Dependency floors (e.g. `hatchling>=`) are
      *not* covered by `scripts/check_version_consistency.py`: grep them by
      hand across `pyproject.toml`, README, `docs/`, examples, CI matrix,
      comments and test literals (see [recurring-bug-patterns.md](recurring-bug-patterns.md)).
- [ ] Skills' minimum Pitloom version (`pitloom>=X.Y.Z` in each
      `skills/*/SKILL.md` `compatibility`, their install recipes and
      `docs/agent-skills.md`): not above the version being released, and
      raised whenever this release breaks a CLI flag or subcommand the
      skills use. 0.20.0 is the first release the current floor
      (`>=0.20.0`, set in PR #235) is satisfiable by; until it ships,
      the pinned `uvx`/`pipx` examples fail by design.
      `scripts/check_version_consistency.py` does not check this yet.
- [ ] `CHANGELOG.md`: every merged PR since the last tag either has an
      entry, or is a routine dependabot/CI-only/docs-only/test-only
      change that doesn't need one (cross-check `git log --oneline
      <last-tag>..HEAD | grep "Merge pull request"` against the
      `[#NNN]:` link refs at the bottom of the file). Include the
      version-bump PR itself when it carries more than version strings
      (0.18.1's bump PR also lowered a dependency floor and changed the
      skills, and had no entry until this check caught it).
- [ ] `python -m build --wheel` succeeds locally; the built wheel embeds
      `<name>-<version>.dist-info/sboms/<name>-<version>.spdx3.json` (PEP 770).
- [ ] Run the `Fuzz` workflow (`workflow_dispatch`, both targets) for a
      major release; skim the run for crash artifacts before proceeding.
      See [fuzzing.md](fuzzing.md) for why this is manual/pre-release
      rather than continuous or RC-tag-triggered.

## 2. Tag and publish

- [ ] `spdx3-validate` is a hard gate on Pitloom's own SBOM: the
      publish workflow validates the release wheel and its standalone SBOM
      and runs the `network`-marked tests with `PITLOOM_REQUIRE_NETWORK=1`
      before `publish`, so an unreachable spdx.org/PyPI blocks publishing
      (re-run the workflow); it is never skipped.
- [ ] The same workflow's `scripts/check_sbom_license.py` step fails
      unless the release SBOM, embedded and standalone, declares *and*
      concludes `Apache-2.0` on the `pitloom` package. The `build` job has
      no licenseid database, so the concluded licence comes from
      `CITATION.cff`'s `license`, else `codemeta.json`'s: keep it there.
      `build.yml` runs the same check on every push and PR, on the
      hook-embedded and `loom project` SBOMs, so a change there fails
      before release.
      The release SBOM comes from `embed-wheel`, which dropped the
      concluded licence before #243 (the build hook's SBOM, which it
      overwrites, still had it).

- [ ] Tag the release, push the tag, publish to PyPI (however this
      project's release automation does it -- not scripted here). The
      GitHub Action installs the version its pinned ref carries, so
      `uses: bact/pitloom@<new-tag>` fails until PyPI serves that
      version; don't announce the tag before the publish completes.

## 3. Post-publish verification (the actual published artifact)

Local build success in step 1 checks Pitloom's own build; it does not
prove what PyPI actually serves. Verify the **real, externally-hosted**
wheel directly:

- [ ] Resolve the wheel URL via `https://pypi.org/pypi/pitloom/<version>/json`
      and download it; verify its SHA-256 against the digest PyPI's own
      API publishes for that file.
- [ ] Unzip it and inspect `pitloom-<version>.dist-info/sboms/pitloom-<version>.spdx3.json`
      directly -- the actual bytes a consumer gets, not a regenerated copy.
- [ ] Confirm PEP 770 location and recommended extension
      (`loom verify-wheel <downloaded.whl> --sbom-filename
      pitloom-<version>.spdx3.json`), run schema + SHACL validation
      (`loom validate-wheel <downloaded.whl>`), recompute every
      `software_File`'s SHA-256 from the extracted bytes and cross-check
      against the wheel's own `RECORD`, and confirm the main package's
      PURL/license relationships/creator identity are as expected.
- [ ] Record the result as a new dated entry in
      [wheel-sbom-verification.md](wheel-sbom-verification.md), following
      its existing entries' format -- this is what makes each release's
      verification durable evidence instead of a one-off chat answer
      that disappears with the session that produced it.

- [ ] Run a throwaway workflow with `uses: bact/pitloom@<new-tag>`
      (and, for the SHA-pin path, `@<tag's commit SHA>`) against a small
      project: it must install exactly `<version>` and emit no
      warning annotation beyond the expected Python-selection one. See
      [github-action.md](github-action.md).

## 4. GitHub Release

- [ ] If a draft release already exists for this tag, regenerate its
      notes before publishing -- a draft created early in the release
      window (e.g. right after the first RC) will be missing every PR
      merged since. Don't publish a draft without checking its PR list
      against `git log --oneline <last-tag>..HEAD` first.
