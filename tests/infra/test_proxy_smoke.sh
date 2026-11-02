#!/usr/bin/env bash
# Smoke-test a running LiteLLM proxy:  tests/infra/test_proxy_smoke.sh <base_url> <master_key> [model]
set -euo pipefail
BASE="${1%/}"; MASTER="$2"; MODEL="${3:-gpt-5-mini}"
pass() { echo "  ✓ $1"; } ; fail() { echo "  ✗ $1"; exit 1; }

KEY=$(curl -fsS "$BASE/key/generate" -H "Authorization: Bearer $MASTER" -H 'Content-Type: application/json' \
  -d '{"key_alias":"smoke-'$RANDOM'@test","max_budget":0.000001}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["key"])')
[[ "$KEY" == sk-* ]] && pass "virtual key minted" || fail "no key"

code=$(curl -s -o /tmp/smoke1.json -w '%{http_code}' "$BASE/v1/chat/completions" -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"model":"'$MODEL'","messages":[{"role":"user","content":"Say ok"}]}')
[[ "$code" == 200 ]] && pass "first call 200" || fail "first call returned $code: $(head -c 300 /tmp/smoke1.json)"

sleep 3  # spend is written asynchronously
code=$(curl -s -o /tmp/smoke2.json -w '%{http_code}' "$BASE/v1/chat/completions" -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"model":"'$MODEL'","messages":[{"role":"user","content":"Say ok"}]}')
if [[ "$code" =~ ^4 ]] && grep -qi budget /tmp/smoke2.json; then pass "over-budget call blocked ($code)"; else fail "over-budget call returned $code: $(head -c 300 /tmp/smoke2.json)"; fi
curl -fsS "$BASE/key/delete" -H "Authorization: Bearer $MASTER" -H 'Content-Type: application/json' -d '{"keys":["'$KEY'"]}' >/dev/null && pass "key deleted"
rm -f /tmp/smoke1.json /tmp/smoke2.json
