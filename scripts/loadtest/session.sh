#!/usr/bin/env bash
# 측정 세션 — 한 설정(CONFIG_LABEL)에 대해 여러 프로필을 정해진 횟수만큼 연속 실행
#
# 사용법 (Mac):
#   caffeinate -i scripts/loadtest/session.sh <CONFIG_LABEL> "<PROFILE:횟수 ...>"
#   예) caffeinate -i scripts/loadtest/session.sh baseline "smoke:1 load:5 stress:3 breakpoint:3"
#
# 규칙 (docs/performance.md §2.6):
#   - 실행 사이 쿨다운 COOLDOWN 초 (기본 300)
#   - 다음 실행 전 서버 정상 확인 — 프론트·백엔드 모두 200 이 60초 연속일 때까지 대기 (breakpoint 뒤 회복 대기)
#   - 실행마다 데이터 전송량(k6 data_received) 누적 기록 — 월 100GB 무료 한도 관리
set -uo pipefail

LABEL=${1:?CONFIG_LABEL 필요}
PLAN=${2:?"실행 계획 필요 (예: \"load:5 stress:3\")"}
COOLDOWN=${COOLDOWN:-300}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
# 운영 주소 — 공개 레포라 IP 를 코드에 두지 않는다. BASE 가 없으면 레포 .env 의 DOMAIN 을 쓴다 (EC2 는 .env 에 있음)
if [ -z "${BASE:-}" ]; then
  DOMAIN=$(grep -s '^DOMAIN=' "$REPO/.env" | cut -d= -f2-)
  BASE=${DOMAIN:+https://$DOMAIN}
fi
: "${BASE:?BASE 필요 — 예) BASE=https://<EC2_IP>.nip.io  (또는 레포 .env 에 DOMAIN=<EC2_IP>.nip.io)}"
export BASE   # run.sh 에 넘김
LOG="$REPO/infra/loadtest/k6/results/$LABEL/session.log"
mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

healthy_for() {  # $1 초 연속 정상이면 0
  local need=$1 ok=0 waited=0
  while (( ok < need )); do
    if [[ $(curl -s -o /dev/null -m 5 -w '%{http_code}' "$BASE/") == 200 &&
          $(curl -s -o /dev/null -m 5 -w '%{http_code}' "$BASE/backend/api/v1/courses?limit=1") == 200 ]]; then
      ok=$((ok + 5))
    else
      ok=0
    fi
    sleep 5; waited=$((waited + 5))
    if (( waited > 900 )); then return 1; fi   # 15분 넘게 회복 안 되면 중단
  done
  return 0   # 명시 — 없으면 마지막 산술 비교(거짓)의 종료 코드 1이 반환돼 정상을 실패로 오판
}

TOTAL_MB=0
first=1
log "세션 시작 label=$LABEL plan=\"$PLAN\" cooldown=${COOLDOWN}s"
for item in $PLAN; do
  profile=${item%%:*}; count=${item##*:}
  for i in $(seq 1 "$count"); do
    if (( ! first )); then
      log "쿨다운 ${COOLDOWN}s"; sleep "$COOLDOWN"
    fi
    first=0
    log "서버 정상 확인 중..."
    if ! healthy_for 60; then log "✗ 서버가 15분 동안 회복되지 않음 — 세션 중단"; exit 1; fi
    log "▶ $profile ($i/$count)"
    "$REPO/scripts/loadtest/run.sh" "$profile" "$LABEL" > /dev/null 2>&1
    run_dir=$(ls -dt "$REPO/infra/loadtest/k6/results/$LABEL"/*-"$profile"-"$LABEL" | head -1)
    mb=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(round(d['metrics']['data_received']['values']['count']/1e6,1))" "$run_dir/summary.json" 2>/dev/null || echo 0)
    TOTAL_MB=$(python3 -c "print(round($TOTAL_MB + $mb, 1))")
    exit_code=$(grep -o 'k6_exit=[0-9]*' "$run_dir/conditions.txt" | cut -d= -f2)
    oom=$(wc -l < "$run_dir/server/oom.log" 2>/dev/null | tr -d ' ')
    log "  ✔ $(basename "$run_dir")  k6_exit=${exit_code:-?}  수신 ${mb}MB (누적 ${TOTAL_MB}MB)  OOM로그 ${oom:-?}줄"
  done
done
log "세션 종료 — 누적 데이터 수신 ${TOTAL_MB}MB"
