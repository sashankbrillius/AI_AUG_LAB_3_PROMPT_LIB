#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:7000}"
PASS=0
FAIL=0

check() {
  local desc="$1"
  local result="$2"
  if [ "$result" = "true" ]; then
    echo "  PASS  $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Lab 3: DevOps Prompt Library — Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

echo "--- Waiting for service readiness ---"
for i in $(seq 1 30); do
  if curl -sf "$BASE_URL/health" > /dev/null 2>&1; then
    echo "  Service ready after ${i}s"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "  FAIL: Service not ready after 30s"
    exit 1
  fi
  sleep 1
done
echo ""

echo "--- Health & Config ---"
HEALTH=$(curl -sf "$BASE_URL/health" 2>/dev/null || echo '{}')
check "Health endpoint returns ok" \
  "$(echo "$HEALTH" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('ok',False)).lower())" 2>/dev/null || echo false)"
check "Service mode is mock" \
  "$(echo "$HEALTH" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('mode','')=='mock').lower())" 2>/dev/null || echo false)"
check "Library has 20 prompts" \
  "$(echo "$HEALTH" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('prompts_in_library',0)==20).lower())" 2>/dev/null || echo false)"
check "5 scenarios available" \
  "$(echo "$HEALTH" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('scenarios_available',0)==5).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Prompt Listing ---"
PROMPTS=$(curl -sf "$BASE_URL/prompts" 2>/dev/null || echo '{}')
check "GET /prompts returns 20 prompts" \
  "$(echo "$PROMPTS" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('total',0)==20).lower())" 2>/dev/null || echo false)"
check "Has 5 categories" \
  "$(echo "$PROMPTS" | python3 -c "import sys,json; print(str(len(json.load(sys.stdin).get('category_breakdown',{}))==5).lower())" 2>/dev/null || echo false)"

DBUG=$(curl -sf "$BASE_URL/prompts?category=debugging" 2>/dev/null || echo '{}')
check "Debugging category has 4 prompts" \
  "$(echo "$DBUG" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('total',0)==4).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Prompt Detail ---"
DETAIL=$(curl -sf "$BASE_URL/prompts/debug-log-analysis" 2>/dev/null || echo '{}')
check "GET /prompts/debug-log-analysis returns prompt" \
  "$(echo "$DETAIL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str('prompt' in d).lower())" 2>/dev/null || echo false)"
check "Quality analysis included" \
  "$(echo "$DETAIL" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str('quality_analysis' in d).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Scenarios ---"
SCENARIOS=$(curl -sf "$BASE_URL/scenarios" 2>/dev/null || echo '{}')
check "GET /scenarios returns 5 scenarios" \
  "$(echo "$SCENARIOS" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('total',0)==5).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Prompt Testing ---"
TEST_RESULT=$(curl -sf -X POST "$BASE_URL/prompts/test" \
  -H "Content-Type: application/json" \
  -d '{"prompt_id":"debug-log-analysis","scenario_id":"scenario-debugging"}' 2>/dev/null || echo '{}')
check "POST /prompts/test returns ok" \
  "$(echo "$TEST_RESULT" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('ok',False)).lower())" 2>/dev/null || echo false)"
check "Test includes quality_score" \
  "$(echo "$TEST_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str('quality_score' in d).lower())" 2>/dev/null || echo false)"
check "Test includes mock_response" \
  "$(echo "$TEST_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str('mock_response' in d).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Quality Scoring ---"
SCORE=$(curl -sf -X POST "$BASE_URL/prompts/score" \
  -H "Content-Type: application/json" \
  -d '{"prompt_text":"Analyze this log"}' 2>/dev/null || echo '{}')
check "POST /prompts/score returns ok" \
  "$(echo "$SCORE" | python3 -c "import sys,json; print(str(json.load(sys.stdin).get('ok',False)).lower())" 2>/dev/null || echo false)"
check "Score includes suggestions" \
  "$(echo "$SCORE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(len(d.get('suggestions',[]))>0).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Export ---"
YAML_EXPORT=$(curl -sf "$BASE_URL/export" 2>/dev/null || echo '')
check "GET /export returns YAML content" \
  "$(echo "$YAML_EXPORT" | python3 -c "import sys; content=sys.stdin.read(); print(str('metadata' in content and 'prompts' in content).lower())" 2>/dev/null || echo false)"

MD_EXPORT=$(curl -sf "$BASE_URL/export?format=markdown" 2>/dev/null || echo '')
check "GET /export?format=markdown returns markdown" \
  "$(echo "$MD_EXPORT" | python3 -c "import sys; content=sys.stdin.read(); print(str('# SmartDine' in content).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Stats ---"
STATS=$(curl -sf "$BASE_URL/stats" 2>/dev/null || echo '{}')
check "GET /stats returns library stats" \
  "$(echo "$STATS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(str(d.get('total_prompts',0)==20).lower())" 2>/dev/null || echo false)"

echo ""
echo "--- Metrics ---"
METRICS=$(curl -sf "$BASE_URL/metrics" 2>/dev/null || echo '')
check "GET /metrics returns Prometheus metrics" \
  "$(echo "$METRICS" | python3 -c "import sys; content=sys.stdin.read(); print(str('prompts_library_total' in content).lower())" 2>/dev/null || echo false)"

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed ($(( PASS + FAIL )) total)"
echo "================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "All smoke tests passed!"
