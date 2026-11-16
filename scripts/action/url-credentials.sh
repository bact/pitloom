# shellcheck shell=bash

# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

# Sourced by action.yml's "Generate SBOM" step; not run directly. Builtins
# only (no external program, no python), for bash 3.2 and Git Bash.
#
# Defines:
#   mask_url_secrets VALUE...
#       Print one ::add-mask:: line for each credential-shaped piece of a
#       URL in each VALUE (a word holding "://"): its user information, its
#       password, and its query and fragment, each whole. A piece shorter
#       than 6 characters is not masked: masking it would hide every
#       occurrence of those characters in the log. Prints nothing else, so
#       it can run before any other output of the step.
#   add_url_credential_args MODE FINGERPRINTS
#       Append --refuse-url-credentials (MODE "refuse"; "warn" or empty
#       passes nothing) and one --accept-url-credential FP per entry of
#       FINGERPRINTS (separated by commas or line breaks) to the loom_args
#       array. Returns 1 after an ::error:: line for a MODE or an entry it
#       refuses; neither is printed, and a refused entry is masked (it may
#       be the credential, pasted by mistake).
#
# See also: python-resolve.sh, ../../action.yml

# Pieces shorter than this are not masked.
_url_mask_min=6

_url_mask_piece() {
  local piece="$1"
  if [ "${#piece}" -lt "${_url_mask_min}" ]; then
    return 0
  fi
  # The runner decodes %25, %0D and %0A in a workflow command's value.
  piece=${piece//'%'/%25}
  piece=${piece//$'\r'/%0D}
  printf '::add-mask::%s\n' "${piece}"
}

_url_mask_word() {
  local word="$1" rest authority userinfo
  case "${word}" in
    *://*) ;;
    *) return 0 ;;
  esac
  rest=${word#*://}
  # git reads the user information up to the last @ before the first /.
  authority=${rest%%/*}
  case "${authority}" in
    *@*)
      userinfo=${authority%@*}
      _url_mask_piece "${userinfo}"
      case "${userinfo}" in
        *:*) _url_mask_piece "${userinfo#*:}" ;;
      esac
      ;;
  esac
  case "${rest}" in
    *'?'*) _url_mask_piece "${rest#*\?}" ;;
  esac
  case "${rest}" in
    *'#'*) _url_mask_piece "${rest#*#}" ;;
  esac
}

mask_url_secrets() {
  local value line word
  local -a words
  for value in "$@"; do
    while IFS= read -r line || [ -n "${line}" ]; do
      line=${line%$'\r'}
      IFS=$' \t' read -r -a words <<< "${line}"
      for word in ${words[@]+"${words[@]}"}; do
        _url_mask_word "${word}"
      done
    done <<< "${value}"
  done
}

# Whether $1 is "sha256:" and 16 to 64 lowercase hex digits (the shape loom's
# --accept-url-credential takes).
_is_fingerprint() {
  local hex
  case "$1" in
    sha256:*) hex=${1#sha256:} ;;
    *) return 1 ;;
  esac
  case "${hex}" in
    '' | *[!0123456789abcdef]*) return 1 ;;
  esac
  [ "${#hex}" -ge 16 ] && [ "${#hex}" -le 64 ]
}

add_url_credential_args() {
  local mode="$1" list="$2" entry number=0 failed=0
  case "${mode}" in
    '' | warn) ;;
    refuse) loom_args+=("--refuse-url-credentials") ;;
    *)
      echo "::error::url-credentials: must be warn or refuse"
      return 1
      ;;
  esac
  list=${list//,/$'\n'}
  while IFS= read -r entry || [ -n "${entry}" ]; do
    # Leading and trailing white space (a CR included) is no part of it.
    entry=${entry#"${entry%%[![:space:]]*}"}
    entry=${entry%"${entry##*[![:space:]]}"}
    if [ -z "${entry}" ]; then
      continue
    fi
    number=$((number + 1))
    if _is_fingerprint "${entry}"; then
      loom_args+=("--accept-url-credential" "${entry}")
    else
      _url_mask_piece "${entry}"
      echo "::error::accept-url-credentials entry ${number}: not a fingerprint (sha256: and 16 to 64 lowercase hex digits; the value is not shown)"
      failed=1
    fi
  done <<< "${list}"
  return "${failed}"
}
