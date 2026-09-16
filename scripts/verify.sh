#!/usr/bin/env bash
# DATAEKO capstone scorecard.
#   ./scripts/verify.sh            everything it can check offline
#   ./scripts/verify.sh --live     also checks the API, GHCR and Pages
# Writes evidence/RECEIPT.json. Commit that file.
set -u

if [ -f .venv/bin/activate ] && [ -z "${VIRTUAL_ENV:-}" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export PATH="$HOME/.local/bin:$PWD/.venv/bin:${PATH}"
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"

LIVE=0; [ "${1:-}" = "--live" ] && LIVE=1
PASS=0; FAIL=0; SKIP=0
RESULTS=""
GH_USER="$(git config --get remote.origin.url 2>/dev/null | sed -E 's#.*[:/]([^/]+)/[^/]+(\.git)?$#\1#' | tr 'A-Z' 'a-z')"
API="${API:-http://localhost:8000}"
KEY="${API_KEY:-}"

ok(){   PASS=$((PASS+1)); printf "  \033[32mPASS\033[0m  %s\n" "$1"; RESULTS="$RESULTS{\"id\":\"$2\",\"result\":\"pass\"},"; }
no(){   FAIL=$((FAIL+1)); printf "  \033[31mFAIL\033[0m  %s\n     -> %s\n" "$1" "$2"; RESULTS="$RESULTS{\"id\":\"$3\",\"result\":\"fail\"},"; }
skip(){ SKIP=$((SKIP+1)); printf "  \033[33mSKIP\033[0m  %s (%s)\n" "$1" "$2"; RESULTS="$RESULTS{\"id\":\"$3\",\"result\":\"skip\"},"; }
banner(){ printf "\n\033[1m%s\033[0m\n" "$1"; }

banner "PHASE 0 — triage"
[ -x scripts/ingest.sh ] && ok "ingest.sh is executable" p0.exec \
  || no "ingest.sh is executable" "chmod +x, then git update-index --chmod=+x" p0.exec
grep -qE '\[ ! -f "\$1" \]|\[\[ ! -f "?\$1"? \]\]' scripts/ingest.sh \
  && ok "\$1 is quoted in ingest.sh" p0.quote \
  || no "\$1 is quoted in ingest.sh" "unquoted \$1 breaks on paths with spaces" p0.quote
awk '/^COPY|^RUN pip/{print NR": "$0}' Dockerfile | command head -3 >/dev/null
if grep -n "requirements" Dockerfile | command head -1 | grep -q COPY && \
   [ "$(grep -n 'COPY.*requirements' Dockerfile | cut -d: -f1 | command head -1)" -lt \
     "$(grep -n 'RUN pip install' Dockerfile | cut -d: -f1 | command head -1)" ] && \
   [ "$(grep -n 'RUN pip install' Dockerfile | cut -d: -f1 | command head -1)" -lt \
     "$(grep -n '^COPY \. \.' Dockerfile | cut -d: -f1 | command head -1)" ]; then
  ok "Dockerfile installs dependencies before copying source" p0.layers
else
  no "Dockerfile installs dependencies before copying source" "COPY . . must come after RUN pip install" p0.layers
fi
[ -f .dockerignore ] && grep -q "\.git" .dockerignore \
  && ok ".dockerignore exists and excludes .git" p0.dockerignore \
  || no ".dockerignore exists and excludes .git" "create it; .git must not enter the image" p0.dockerignore
if grep -rqE 'dataeko-capstone-2026-secret' --include="*.py" --include="*.yml" . 2>/dev/null; then
  no "no hardcoded API key in the repo" "still present — and still in git history" p0.secret
else
  ok "no hardcoded API key in the repo" p0.secret
fi
grep -qE 'requests\.(get|post)\([^)]*timeout' ingest/loader.py \
  && ok "requests call has a timeout" p0.timeout \
  || no "requests call has a timeout" "a request with no timeout waits forever" p0.timeout
ls sql/migrations/*.sql >/dev/null 2>&1 && grep -rqi "create index" sql/migrations/ \
  && ok "an index migration exists" p0.index \
  || no "an index migration exists" "add sql/migrations/001_*.sql with the CREATE INDEX" p0.index
if grep -A3 'from_port   = 22' infra/main.tf 2>/dev/null | grep -q '0\.0\.0\.0/0'; then
  no "SSH is not open to the world" "port 22 still has cidr_blocks 0.0.0.0/0" p0.sg
else
  ok "SSH is not open to the world" p0.sg
fi
grep -q "for_each" infra/main.tf && ! grep -q "count  *= length" infra/main.tf \
  && ok "buckets use for_each, not count" p0.foreach \
  || no "buckets use for_each, not count" "count churns resources when the list changes" p0.foreach
if [ -f TRIAGE.md ] && [ "$(grep -c '^## ' TRIAGE.md)" -ge 9 ] && ! grep -q "TODO" TRIAGE.md; then
  ok "TRIAGE.md documents all 9 defects" p0.triage
else
  no "TRIAGE.md documents all 9 defects" "nine '## ' sections, and no TODO left in the file" p0.triage
fi

banner "PHASE 1 — ingest"
python3 -c "from ingest.loader import read_rows, validate" 2>/dev/null \
  && ok "loader functions import" p1.import \
  || no "loader functions import" "activate your venv first; then implement read_rows and validate" p1.import
if command -v pytest >/dev/null 2>&1; then
  if pytest -q >/dev/null 2>&1; then ok "pytest passes" p1.tests
  else no "pytest passes" "run: pytest -v" p1.tests; fi
else skip "pytest passes" "pytest not installed" p1.tests; fi
[ -f evidence/rejected.csv ] && [ "$(tail -n +2 evidence/rejected.csv 2>/dev/null | wc -l | tr -d ' ')" -eq 9 ] \
  && ok "evidence/rejected.csv has exactly 9 rejected rows" p1.rejects \
  || no "evidence/rejected.csv has exactly 9 rejected rows" "the CSV has 9 malformed rows" p1.rejects

banner "PHASE 3 — queries"
for f in explain-before.txt explain-after.txt; do
  [ -s "evidence/$f" ] && ok "evidence/$f exists" "p3.$f" || no "evidence/$f exists" "commit the EXPLAIN ANALYZE output" "p3.$f"
done
grep -qi "seq scan" evidence/explain-before.txt 2>/dev/null \
  && ok "before-plan shows a sequential scan" p3.seq || no "before-plan shows a sequential scan" "capture it BEFORE creating the index" p3.seq
grep -qi "index scan" evidence/explain-after.txt 2>/dev/null \
  && ok "after-plan shows an index scan" p3.idx || no "after-plan shows an index scan" "capture it AFTER creating the index" p3.idx
[ "$(ls sql/queries/*.sql 2>/dev/null | wc -l | tr -d ' ')" -ge 4 ] \
  && ok "four query files in sql/queries/" p3.queries || no "four query files in sql/queries/" "one .sql per business question" p3.queries

banner "PHASE 4 — observability"
[ -s evidence/dashboard.json ] && ok "evidence/dashboard.json exists" p4.dash || no "evidence/dashboard.json exists" "export your Grafana dashboard" p4.dash
[ -s evidence/promql.txt ] && ok "evidence/promql.txt exists" p4.promql || no "evidence/promql.txt exists" "commit your rate() query and its output" p4.promql
grep -qE "^[A-Z_]+ *= *Gauge\\(" api/app.py && grep -q "capstone_orders_in_flight" api/app.py && ok "a Gauge is defined" p4.gauge || no "a Gauge is defined" "add capstone_orders_in_flight" p4.gauge

banner "PHASE 5 — ship"
grep -q "upload-artifact" .github/workflows/ci.yml && ok "CI uploads an artifact" p5.artifact || no "CI uploads an artifact" "actions/upload-artifact@v4" p5.artifact
grep -q "matrix" .github/workflows/ci.yml && ok "CI uses a matrix" p5.matrix || no "CI uses a matrix" "test on more than one Python version" p5.matrix
grep -rq "secrets\." .github/workflows/ && ok "workflow reads from secrets" p5.secrets || no "workflow reads from secrets" "the key must come from secrets, not the file" p5.secrets
[ -f .github/workflows/pages.yml ] && ok "a Pages workflow exists" p5.pages || no "a Pages workflow exists" "add .github/workflows/pages.yml" p5.pages

banner "PHASE 6 — provision"
for f in plan.txt drift-plan.txt; do
  [ -s "evidence/$f" ] && ok "evidence/$f exists" "p6.$f" || no "evidence/$f exists" "commit the terraform plan output" "p6.$f"
done
grep -qE "1 to change|must be replaced|~ " evidence/drift-plan.txt 2>/dev/null \
  && ok "drift plan shows a detected change" p6.drift || no "drift plan shows a detected change" "change something by CLI, then plan" p6.drift

if [ "$LIVE" = "1" ]; then
  banner "LIVE CHECKS"
  code(){ curl -s -o /dev/null -w "%{http_code}" "$@"; }
  if [ "$(code $API/health)" = "200" ]; then ok "API /health is 200" l.health
    [ "$(code $API/orders)" = "401" ] && ok "/orders with no key is 401" l.401 || no "/orders with no key is 401" "got $(code $API/orders)" l.401
    [ "$(code -H 'Authorization: Bearer wrong' $API/orders)" = "403" ] && ok "/orders with a bad key is 403" l.403 || no "/orders with a bad key is 403" "401 means unknown, 403 means refused" l.403
    if [ -n "$KEY" ]; then
      body=$(curl -s -H "Authorization: Bearer $KEY" "$API/orders?page=1&per_page=5")
      echo "$body" | grep -q '"total"' && echo "$body" | grep -q '"count"' \
        && ok "/orders returns count and total" l.page || no "/orders returns count and total" "they are different numbers" l.page
    else skip "/orders returns count and total" "set API_KEY" l.page; fi
    curl -s $API/metrics | grep -q "capstone_requests_total" && ok "/metrics exposes the counter" l.metrics || no "/metrics exposes the counter" "prometheus_client" l.metrics
  else
    for i in l.health l.401 l.403 l.page l.metrics; do skip "API check" "API not running at $API" $i; done
  fi
  if [ -n "$GH_USER" ]; then
    if docker manifest inspect "ghcr.io/$GH_USER/dataeko-capstone:latest" >/dev/null 2>&1; then
      ok "GHCR image is public and pullable" l.ghcr
    else no "GHCR image is public and pullable" "ghcr.io/$GH_USER/dataeko-capstone:latest — is the package public?" l.ghcr; fi
    P="https://$GH_USER.github.io/dataeko-capstone/"
    [ "$(code $P)" = "200" ] && ok "Pages site is live at $P" l.pages || no "Pages site is live" "$P returned $(code $P)" l.pages
  else skip "GHCR + Pages" "no git remote found" l.remote; fi
fi

TOTAL=$((PASS+FAIL+SKIP))
printf "\n\033[1mSCORE: %d/%d passed  (%d failed, %d skipped)\033[0m\n" "$PASS" "$((PASS+FAIL))" "$FAIL" "$SKIP"
mkdir -p evidence
printf '{"student":"%s","pass":%d,"fail":%d,"skip":%d,"total":%d,"checks":[%s]}\n' \
  "$GH_USER" "$PASS" "$FAIL" "$SKIP" "$TOTAL" "${RESULTS%,}" > evidence/RECEIPT.json
echo "wrote evidence/RECEIPT.json — commit it."
[ "$FAIL" -eq 0 ]
