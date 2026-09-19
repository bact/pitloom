---
Created: 2026-09-19
Last-Modified: 2026-09-19
SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
SPDX-FileType: DOCUMENTATION
SPDX-License-Identifier: CC0-1.0
---

# Choosing a `--build-timeout` value

Companion to `../SKILL.md`'s "Choosing `--build-timeout`" section. This
only ever applies **after** the user has already explicitly asked for
`--allow-build` in this conversation -- picking a `--build-timeout`
value is not itself a security decision, but adding `--allow-build` is,
and that hard rule (`../SKILL.md`, "Known limitations") never changes
because of anything below.

## 1. Duration format

Bare number = seconds; or `h`/`m`/`s` units, largest-first, each at
most once:

```text
900        # 900 seconds
900s       # same, explicit unit
15m        # 15 minutes
1h30m      # 1 hour 30 minutes
1h30m45s   # 1 hour 30 minutes 45 seconds
```

Rejected: decimals (`1.5h`), `ms`/`us`/`d` units, uppercase (`1H`),
whitespace (`1h 30m`, ` 90m`), out-of-order/repeated units (`30m1h`,
`1h1h`). Range: 1 second .. 7 days (604800 s). Default when the flag is
omitted: 20 minutes (1200 s). Prefer the unit form when talking to the
user (`--build-timeout 8m`, not `--build-timeout 480`) -- it's what a
human actually reads.

## 2. Estimate the build time -- read-only, never run the build to measure it

Never run the project's build (or any of its own code) just to see how
long it takes -- that is the exact unbounded-build risk `--build-timeout`
exists to bound. Estimate instead, from signals you can read without
executing anything:

- **Build backend + native code.** Pure-Python backends (hatchling,
  flit, pdm, poetry, uv_build, setuptools with no `ext_modules`) are
  typically well under 2 minutes, dominated by installing
  `build-system.requires`. Native-code backends run minutes to tens of
  minutes: setuptools with `ext_modules`/Cython (`.pyx` files),
  `maturin` (Rust -- check `Cargo.toml`/`Cargo.lock` crate count),
  `scikit-build-core`/`meson-python` (C/C++ -- count `.c`/`.cc`/`.cpp`
  files).
- **Project size.** Count source files by extension (`git ls-files`, or
  a bounded `find`) -- not bytes read.
- **Build dependencies.** Count `[build-system] requires` entries (plus
  any lock file). An isolated build (the default) downloads them from
  the network on every run -- slower, network-bound.
  `--no-build-isolation` uses the already-installed backend instead --
  no download.
- **Machine.** CPU count (`nproc` / `sysctl -n hw.ncpu` /
  `$env:NUMBER_OF_PROCESSORS`), memory, and warm caches (pip cache dir,
  `~/.cargo/registry`, an existing `target/`/`build/` directory) all
  shorten a real run.
- **Toolchain presence.** Missing `cargo`/`cmake`/`cc`/`cl` makes the
  build fail fast rather than time out -- say so instead of picking a
  long timeout for a build that can't succeed anyway.
- **Load.** Other builds or jobs running right now on the same machine
  slow this one down (CPU contention).

Give the user a **range**, not a false-precision single number --
"likely 1-3 minutes, could reach ~10 on a cold cache" -- and say
explicitly that it's an estimate, not a measurement.

## 3. Know your own limits (agent/harness), before choosing a value

- **Per-command timeout of whatever runs `loom`.** For example, Claude
  Code's Bash tool defaults to a 2-minute timeout per call (up to a
  10-minute max if requested), unless the command is run in the
  background; a CI job may carry its own `timeout-minutes`; a scheduler
  may carry an overall job/session budget.
- **Why it matters.** If the harness stops `loom` before
  `--build-timeout` fires on its own, no SBOM is written at all. On
  SIGTERM/SIGHUP/Ctrl-C during the build, or while its files are still in
  use, Pitloom still kills the build and removes its temp dirs before exiting (a few seconds at most), but
  a harness may SIGKILL (outright, or as an escalation a few seconds
  after SIGTERM), and then the build process tree is orphaned. Pitloom's own default (20m) already
  exceeds many harness call limits, so **in an agent session, always
  pass an explicit `--build-timeout`** rather than relying on the
  default.
- **Rule of thumb:** `--build-timeout` value `<= command_limit - margin`, where
  `margin = max(60s, 25% of the limit)`, leaving room for killing the
  build once the timeout fires (up to ~8 s on Linux/macOS, up to
  ~90 s on Windows -- use a margin of at least 2 min there) and the
  rest of the run (metadata extraction, hashing, writing the SBOM)
  after the build finishes. If the estimated build time doesn't fit
  inside a foreground call's limit, run `loom` as a background task
  instead (if the harness supports it) and size the timeout against
  the session budget rather than the single-call limit.
- **Parallel work.** Budget against what's actually left of the
  session after other tasks already running or planned alongside this
  one (other `loom` runs, subagents, test suites) -- don't launch
  several `--allow-build` builds in parallel on one machine unless the
  CPU count comfortably allows it; they slow each other down, so
  stretch the estimate accordingly when they do run concurrently.

## 4. Talk to the user (interactive session)

State the estimate, your own limit, and a proposed value, then ask one
question with a short set of choices: the proposed value (recommended),
Pitloom's own default of 20m (only offer this if it actually fits your
limit), a custom value the user names, or skipping `--allow-build`
entirely in favour of static discovery. If the estimate already exceeds
what fits inside your own limit, say so plainly and suggest the exact
command to run in the user's own terminal instead (verbatim, so they
can paste it).

## 5. Non-interactive fallback (CI/batch, no human to answer)

Don't block waiting for input. Pick
`min(upper_estimate * 1.5, fitted_limit)`, rounded up to a whole
minute, and state the chosen value and the reasoning in your output
(not just silently proceeding) -- e.g. "estimated 3-5 min build,
harness limit fits ~9 min after margin, using `--build-timeout 8m`".

## 6. On timeout

Report the `WARNING:` line verbatim (see `../SKILL.md`'s "Check stderr"
section for its exact wording). The SBOM was still written -- the
command exits 0 -- but its file list came from the static Hatchling
heuristic fallback, not the real build, so it may be incomplete or
mis-pathed for this backend. Offer a re-run with a larger
`--build-timeout` in an interactive session; in a non-interactive run,
just report what happened. **Never silently retry with `--allow-build`
again on your own initiative** -- a repeat pass needs the same
explicit ask this whole document is scoped under.

## See also

- `../SKILL.md` -- "Choosing `--build-timeout`" (the short version this
  file expands on) and "Known limitations" (the `--allow-build`
  consent rule).
- `references/examples.md` -- a copy-paste recipe using
  `--build-timeout`.
