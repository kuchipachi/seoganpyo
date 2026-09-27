#!/bin/bash
# $1 라벨. 고정 도착률(RATE)로 DUR 동안 강의 목록 요청 → 지연 분포 + api CPU 평균
cd "$(dirname "$0")"; L=$1; OUT=result-$L.txt
C=repro-api-1
( while true; do docker stats --no-stream --format '{{.CPUPerc}}' $C; sleep 2; done ) > cpu-$L.log 2>/dev/null &
S=$!
k6 run --no-usage-report -q --summary-trend-stats "med,p(90),p(95),p(99),max" overload.js > k6-$L.log 2>&1
kill $S
{
  echo "rate=${RATE}/s dur=${DUR} image=$(docker inspect $C --format '{{.Config.Image}}')"
  grep -E "http_req_duration|http_req_failed|http_reqs" k6-$L.log | sed 's/\x1b\[[0-9;]*m//g'
  awk '{gsub("%",""); s+=$1; n++; if($1>m)m=$1} END{printf "api CPU avg=%.0f%% max=%.0f%% (samples=%d)\n", s/n, m, n}' cpu-$L.log
} | tee $OUT
