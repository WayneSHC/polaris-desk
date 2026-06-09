#!/usr/bin/env bash
# Sync the fetch-tw-earnings-call skill CODE from polaris-desk (canonical source
# of truth) to the standalone plugin repo, so the two never drift.
#
# Syncs only the files where logic lives — scripts + skill tests + fixtures.
# Deliberately NOT synced (legitimately per-repo):
#   - SKILL.md      : invocation path differs (repo path vs portable $SKILL_DIR)
#   - conftest.py   : test sys.path wiring differs between the repos
#   - plugin.json / marketplace.json : plugin packaging, polaris-desk has none
#
# Usage:
#   scripts/sync-plugin.sh [PLUGIN_REPO]
#   PLUGIN_REPO=/path/to/fetch-tw-earnings-call scripts/sync-plugin.sh
# Default PLUGIN_REPO: ../fetch-tw-earnings-call (sibling checkout).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_SKILL="$REPO_ROOT/.claude/skills/fetch-tw-earnings-call"
SRC_TESTS="$REPO_ROOT/tests"
PLUGIN_REPO="${1:-${PLUGIN_REPO:-$REPO_ROOT/../fetch-tw-earnings-call}}"

DST_SKILL="$PLUGIN_REPO/skills/fetch-tw-earnings-call"
DST_TESTS="$PLUGIN_REPO/tests"

TEST_FILES=(test_ec_model.py test_ec_mops.py test_ec_todayir.py test_fetch_earnings_call.py)
FIXTURES=(ctbc_financial_analyst_2026.html mops_t100sb02_2891.html)

[ -d "$DST_SKILL/scripts" ] || { echo "✗ plugin scripts dir not found: $DST_SKILL/scripts" >&2; exit 1; }

echo "→ syncing scripts/*.py"
for f in "$SRC_SKILL/scripts"/*.py; do
  cp "$f" "$DST_SKILL/scripts/$(basename "$f")"
done

echo "→ syncing skill test files"
for f in "${TEST_FILES[@]}"; do
  cp "$SRC_TESTS/$f" "$DST_TESTS/$f"
done

echo "→ syncing fixtures"
for f in "${FIXTURES[@]}"; do
  cp "$SRC_TESTS/fixtures/$f" "$DST_TESTS/fixtures/$f"
done

echo "→ verifying scripts are byte-identical"
diff -r --exclude=__pycache__ "$SRC_SKILL/scripts" "$DST_SKILL/scripts" \
  && echo "  ✓ scripts identical"

echo "→ running plugin test suite"
( cd "$PLUGIN_REPO" && python3 -m pytest -q )

echo "✓ sync complete. Reminder: if SKILL.md's naming spec changed, reconcile"
echo "  $DST_SKILL/SKILL.md by hand (keep its portable \$SKILL_DIR invocation)."
