#!/bin/bash
# $1 = 라벨. 과부하 60초 → 멈춘 뒤 회복까지 10초 간격 관찰 (최대 15분)
cd "$(dirname "$0")"; L=$1; OUT=result-$L.txt; : > $OUT
T0=$(date +%s)
k6 run --no-usage-report -q overload.js > k6-$L.log 2>&1 &
K=$!
while kill -0 $K 2>/dev/null; do sleep 1; done
T1=$(date +%s); echo "k6 종료 +$((T1-T0))s" | tee -a $OUT
grep -E "http_req_failed|http_req_duration|http_reqs|dropped" k6-$L.log | sed 's/\x1b\[[0-9;]*m//g' | tee -a $OUT
for i in $(seq 1 90); do
  c=$(curl -s -o /dev/null -m 5 -w '%{http_code}' 'http://localhost:18000/api/v1/courses?limit=1')
  st=$(docker exec repro-db-1 psql -U postgres -d seoganpyo -Atc "select coalesce(string_agg(state||'='||n, ' '),'-') from (select state, count(*) n from pg_stat_activity where datname='seoganpyo' and pid<>pg_backend_pid() group by state) x")
  echo "+$(( $(date +%s)-T1 ))s api=$c db[$st]" | tee -a $OUT
  if [ "$c" = "200" ]; then echo "회복: 부하 종료 후 $(( $(date +%s)-T1 ))s" | tee -a $OUT; break; fi
  sleep 10
done
echo "--- QueuePool 타임아웃 분당:" | tee -a $OUT
docker logs -t repro-api-1 --since "$(( $(date +%s)-T0+30 ))s" 2>&1 | grep "QueuePool limit" | cut -c12-16 | sort | uniq -c | tee -a $OUT
