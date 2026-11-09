#!/usr/bin/env bash
# Run the NuqtaPass module tests in a throwaway database.
#   scripts/test.sh                       → all three modules
#   scripts/test.sh nuqtapass_loyalty     → one module
set -euo pipefail
cd "$(dirname "$0")/../docker"
MODULES="${1:-nuqtapass_loyalty,nuqtapass_loyalty_pos,nuqtapass_loyalty_website_sale}"
TAGS="$(echo "$MODULES" | sed -E 's/(^|,)/\1\//g')"
DB="test_$(date +%s)"
LOG="$(mktemp)"
set +e
docker compose run --rm odoo odoo -c /etc/odoo/odoo.conf -d "$DB" -i "$MODULES" \
  --test-tags "$TAGS" --stop-after-init --log-level=test --http-port=8169 2>&1 | tee "$LOG"
STATUS=${PIPESTATUS[0]}
set -e
docker compose exec -T db dropdb -U odoo --if-exists "$DB" >/dev/null 2>&1 || true
if grep -qE "(FAIL|ERROR):|[1-9][0-9]* failed|[1-9][0-9]* error\(s\)" "$LOG"; then
  echo "TESTS FAILED"; exit 1
fi
# An import error or a broken registry stops Odoo before any test runs: it is logged at
# ERROR/CRITICAL level (not "ERROR:") and prints no result line, so catch it here.
if [ "$STATUS" -ne 0 ] || grep -qE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL) " "$LOG"; then
  echo "TESTS FAILED (Odoo exited $STATUS or logged an error)"; exit 1
fi
# A module Odoo can't find is only a warning, and then none of its tests run: that is not a pass.
if grep -q "invalid module names" "$LOG"; then
  echo "TESTS FAILED (module not found)"; exit 1
fi
# A manifest for another Odoo version is skipped with a warning ("incompatible version"), and then no test runs.
if grep -qE "incompatible version|not installable" "$LOG"; then
  echo "TESTS FAILED (module not installable on this Odoo version)"; exit 1
fi
if ! grep -qE "of [1-9][0-9]* tests" "$LOG"; then
  echo "TESTS FAILED (no test ran)"; exit 1
fi
# The till's money math is plain JS (no Odoo imports): run it with Node, on the host.
if [[ ",$MODULES," == *",nuqtapass_loyalty_pos,"* ]]; then
  if ! command -v node >/dev/null 2>&1; then
    echo "TESTS FAILED (node not found: the till's JS tests need Node 22+)"; exit 1
  fi
  if ! node --test ../nuqtapass_loyalty_pos/tests/js/*.test.mjs; then
    echo "TESTS FAILED (till JS)"; exit 1
  fi
fi
echo "TESTS PASSED"
