#!/bin/bash

# Runs the steps of .github/workflows/compiler-discovery.yml by hand.
#
# The admin node's GitHub Actions runner takes one job at a time, and the nightly compiler
# install can hold it for hours, so a dispatched discovery sits queued behind it. This does
# the same sequence directly.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CE="${DIR}/bin/ce"

ENVIRONMENT=staging
BRANCH=main
SKIP_REMOTE_CHECKS=""
KEEP_RUNNING=""
FORCE=""
DRY_RUN=""
BUILDNUMBER=""

usage() {
    cat <<USAGE
Usage: $(basename "$0") [options] BUILDNUMBER

Run compiler discovery on the runner instance and upload the result.

Options:
  -e, --environment ENV     Environment to upload discovery for (default: ${ENVIRONMENT})
  -b, --branch BRANCH       Branch the build came from (default: ${BRANCH})
  -s, --skip-remote-checks  Comma separated remote checks to skip, e.g. gpu,winprod
      --keep-running        Leave the runner instance up afterwards
      --force               Proceed even if the runner instance is already running
      --dry-run             Print the commands without running them
  -h, --help                Show this message

Example:
  $(basename "$0") --environment staging gh-19252
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -e|--environment) ENVIRONMENT="$2"; shift 2 ;;
        -b|--branch) BRANCH="$2"; shift 2 ;;
        -s|--skip-remote-checks) SKIP_REMOTE_CHECKS="$2"; shift 2 ;;
        --keep-running) KEEP_RUNNING=1; shift ;;
        --force) FORCE=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
        *)
            if [[ -n "${BUILDNUMBER}" ]]; then
                echo "Unexpected argument: $1" >&2
                usage >&2
                exit 2
            fi
            BUILDNUMBER="$1"
            shift
            ;;
    esac
done

if [[ -z "${BUILDNUMBER}" ]]; then
    echo "No build number given" >&2
    usage >&2
    exit 2
fi

case "${ENVIRONMENT}" in
    staging|beta|prod) ;;
    *) echo "Unknown environment: ${ENVIRONMENT} (expected staging, beta or prod)" >&2; exit 2 ;;
esac

run() {
    echo "+ $*"
    if [[ -z "${DRY_RUN}" ]]; then
        "$@"
    fi
}

# The runner is normally stopped, so finding it up means something else is using it -- most
# likely the very GitHub Actions job this script exists to work around.
if [[ -z "${FORCE}" && -z "${DRY_RUN}" ]]; then
    STATUS=$("${CE}" runner status)
    if [[ "${STATUS}" != *stopped* ]]; then
        echo "${STATUS}" >&2
        echo "The runner is not stopped, so something else may be using it." >&2
        echo "Check for a running discovery job before continuing, then pass --force." >&2
        exit 1
    fi
fi

stop_runner() {
    # shellcheck disable=SC2317
    if [[ -n "${KEEP_RUNNING}" ]]; then
        echo "Leaving the runner instance running (--keep-running)"
        return
    fi
    # shellcheck disable=SC2317
    echo "Stopping the runner instance"
    # shellcheck disable=SC2317
    run "${CE}" runner stop
}
trap stop_runner EXIT

echo "Discovery for ${ENVIRONMENT}, branch ${BRANCH}, build ${BUILDNUMBER}"

run "${CE}" --env runner builds set_current "${BUILDNUMBER}" --branch "${BRANCH}" --confirm
run "${CE}" runner start
run "${CE}" runner pull
run "${CE}" runner discovery
run "${CE}" runner uploaddiscovery "${ENVIRONMENT}" --skip-remote-checks="${SKIP_REMOTE_CHECKS}" "${BUILDNUMBER}"

echo "Discovery uploaded for ${ENVIRONMENT} build ${BUILDNUMBER}"
