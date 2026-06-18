#!/usr/bin/env bash
# Recompute every published table and figure from the released archive.
#
# Exits non-zero if any reproduce_*.py script's snapshot check fails.
# Pass --update-snapshot to forward the flag to every step.

set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

PASS_ARGS="$*"

declare -a STEPS=(
    "scripts.reproduce.reproduce_table_2"
    "scripts.reproduce.reproduce_table_3"
    "scripts.reproduce.reproduce_fig_3"
    "scripts.reproduce.reproduce_fig_4"
    "scripts.reproduce.reproduce_app_2"
)

FAILED=0
for module in "${STEPS[@]}"; do
    echo
    echo "===== ${module} ====="
    if ! python -m "${module}" ${PASS_ARGS}; then
        echo "[FAIL] ${module}"
        FAILED=1
    fi
done

echo
if [ "${FAILED}" -eq 0 ]; then
    echo "ALL RECOMPUTE STEPS PASSED."
else
    echo "ONE OR MORE RECOMPUTE STEPS FAILED. See output above."
fi
exit "${FAILED}"
