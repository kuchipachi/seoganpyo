#!/bin/bash
# T2 비교 — 이미지·도착률 조합을 3라운드 번갈아 측정 (순서 효과·열 상태 편향 제거)
# 사용: ./run-t2-compare.sh dev24:20 t2:20 t1app:60 t1t2:60
#   <이미지 태그>:<요청/초>. 모든 이미지를 같은 설정(compose.t1.yml + compose.t1app.yml, 한도 14)으로 띄운다.
#   한도 미들웨어가 없는 이미지는 MAX_CONCURRENT_REQUESTS 를 무시하므로 같은 명령으로 비교 가능.
cd "$(dirname "$0")"
use() {
  API_IMAGE=seoganpyo-api:$1 docker compose -p repro -f compose.yml -f compose.t1.yml -f compose.t1app.yml \
    up -d --force-recreate --no-deps api >/dev/null 2>&1 || { echo "UP FAILED $1"; return 1; }
  for _ in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/ | grep -q 200 && break; sleep 2; done
  got=$(docker inspect repro-api-1 --format '{{.Config.Image}}')
  [ "$got" = "seoganpyo-api:$1" ] || { echo "IMAGE MISMATCH $got"; return 1; }   # 이미지 교체 실패로 무효 측정이 된 적 있음
  bytes=$(curl -s "http://localhost:18000/api/v1/courses?year=2026&semester=1" | wc -c)
  echo "using $got bytes=$bytes"                                                    # 운영 크기(약 130KB)인지 확인
  for _ in $(seq 1 20); do curl -s -o /dev/null "http://localhost:18000/api/v1/courses?year=2026&semester=1"; done
  sleep 5
}
for r in 1 2 3; do
  for spec in "$@"; do
    img=${spec%:*}; rate=${spec#*:}
    use "$img" || exit 1
    RATE=$rate DUR=60s ./run-latency.sh "t2full-$img-r$rate-$r"
    sleep 20
  done
done
