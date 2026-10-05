#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

# Installs Pitloom for action.yml's "Install Pitloom" step.
#
# Env: PL_EXTRAS  comma-separated pip extras (may be empty)
#      PL_VERSION pitloom-version input: a bare version ("0.20.0"), a
#                 specifier (">=0.20,<1.0"), or empty to install the version
#                 carried by this pinned action checkout.
#
# See also: python-resolve.sh, python_probe.py,
#           ../check_version_consistency.py (--print-version)

set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck source=python-resolve.sh source-path=SCRIPTDIR
. "${script_dir}/python-resolve.sh"
require_python

spec="pitloom"
if [ -n "${PL_EXTRAS:-}" ]; then
  spec="${spec}[${PL_EXTRAS}]"
fi

# Whitespace is never significant in a version or specifier.
requested_version=$(printf '%s' "${PL_VERSION:-}" | tr -d '[:space:]')

derived_version=""
if [ -n "${requested_version}" ]; then
  # A leading comparison operator means a full specifier; only a bare
  # version needs "==" inserted ("pitloom==>=0.20,<1.0" is invalid).
  case "${requested_version}" in
    [\<\>=!~]*) spec="${spec}${requested_version}" ;;
    *) spec="${spec}==${requested_version}" ;;
  esac
else
  # Hand the native (drive-letter) form to a native python.exe on Windows.
  version_script="${script_dir}/../check_version_consistency.py"
  if command -v cygpath >/dev/null 2>&1; then
    version_script=$(cygpath -m "${version_script}")
  fi
  if ! derived_version=$(python_text "${version_script}" --print-version) \
    || [ -z "${derived_version}" ]; then
    echo "::error::Cannot read the Pitloom version of this action checkout; set pitloom-version"
    exit 1
  fi
  spec="${spec}==${derived_version}"
  echo "::notice::Installing pitloom==${derived_version}, the version of this action's pinned ref (set pitloom-version to override)"
fi

if ! "${python_bin}" -m pip install "${spec}"; then
  if [ -n "${derived_version}" ]; then
    echo "::error::Cannot install pitloom==${derived_version} (see pip output above). If it is unreleased, pin a release tag or SHA, or set pitloom-version"
  fi
  exit 1
fi

if ! command -v loom >/dev/null 2>&1; then
  echo "::error::pitloom installed but loom is not on PATH"
  exit 1
fi
