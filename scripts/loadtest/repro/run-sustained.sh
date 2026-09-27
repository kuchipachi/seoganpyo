#!/bin/bash
# $1 라벨, RATE/DUR 환경변수. 과부하 동안·이후 헬스 상태와 autoheal 재시작을 5초 간격으로 기록
cd "$(dirname "$0")"; L=$1; OUT=result-$L.txt; : > $OUT
C=repro-api-1
echo "rate=${RATE:-60}/s dur=${DUR:-60s} limit=${LIMIT:-?} image=$(docker inspect $C --format '{{.Config.Image}}') cmd=$(docker inspect $C --format '{{join .Config.Cmd " "}}')" | tee -a $OUT
R0=$(docker inspect $C --format '{{.RestartCount}}'); S0=$(docker inspect $C --format '{{.State.StartedAt}}')
T0=$(date +%s)
k6 run --no-usage-report -q overload.js > k6-$L.log 2>&1 &
K=$!
prev=""
while :; do
  el=$(( $(date +%s)-T0 ))
  h=$(docker inspect $C --format '{{if .State.Health}}{{.State.Health.Status}} streak={{.State.Health.FailingStreak}}{{end}} started={{.State.StartedAt}}' 2>/dev/null | sed -E 's/started=([0-9T:-]+)\..*/started=\1/')
  hz=$(curl -s -m 6 -o /dev/null -w '%{http_code}' http://localhost:18000/healthz)
  api=$(curl -s -m 6 -o /dev/null -w '%{http_code}' 'http://localhost:18000/api/v1/courses?limit=1')
  running=$(kill -0 $K 2>/dev/null && echo LOAD || echo idle)
  line="$running docker=$h healthz=$hz api=$api"
  [ "$line" != "$prev" ] && echo "+${el}s $line" | tee -a $OUT
  prev=$line
  if [ "$running" = idle ] && [ -z "${ENDT:-}" ]; then ENDT=$el; fi
  if [ -n "${ENDT:-}" ] && [ $((el-ENDT)) -ge ${AFTER:-120} ]; then break; fi
  sleep 5
done
echo "--- k6" | tee -a $OUT
grep -E "http_req_failed|http_reqs|http_req_duration|dropped" k6-$L.log | sed 's/\x1b\[[0-9;]*m//g' | tee -a $OUT
echo "--- autoheal 재시작 (이 실험 구간)" | tee -a $OUT
docker logs --since "$(( $(date +%s)-T0+5 ))s" repro-autoheal-1 2>&1 | grep -i "restarting" | tee -a $OUT
echo "restarts_logged=$(docker logs --since "$(( $(date +%s)-T0+5 ))s" repro-autoheal-1 2>&1 | grep -ci restarting)" | tee -a $OUT
echo "--- api 응답 코드 분포" | tee -a $OUT
docker logs --since "$(( $(date +%s)-T0+5 ))s" $C 2>&1 | grep -oE '" (200|500|503)' | sort | uniq -c | tee -a $OUT
