#!/usr/bin/env bash
# 부하 테스트 1회 실행 — 전후 조건 기록 + EC2 서버 지표 수집 + k6 + 결과 회수
#
# 사용법 (Mac):
#   scripts/loadtest/run.sh <PROFILE> <CONFIG_LABEL>
#   예) scripts/loadtest/run.sh load baseline
#       scripts/loadtest/run.sh stress v1-memlimit
#   PROFILE: smoke | load | stress | breakpoint
#   CONFIG_LABEL: 튜닝 설정 이름 (before/after 비교 단위)
#
# 결과: infra/loadtest/k6/results/<CONFIG_LABEL>/<RUN_ID>/  (raw 는 커밋하지 않음)
set -uo pipefail

PROFILE=${1:?PROFILE 필요 (smoke|load|stress|breakpoint)}
LABEL=${2:?CONFIG_LABEL 필요 (예: baseline)}
BASE=${BASE:-https://54.180.181.46.nip.io}
EC2=${EC2:-ec2-user@54.180.181.46}
KEY=${KEY:-$HOME/.ssh/server-key.pem}
INSTANCE_ID=${INSTANCE_ID:-i-0cf5fbf562ec4017b}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
SSH=(ssh -o BatchMode=yes -o LogLevel=ERROR -i "$KEY" "$EC2")

case $PROFILE in   # k6 시나리오 길이 + 여유 (서버 지표 수집 시간)
  smoke) SECS=90 ;; load) SECS=720 ;; stress) SECS=930 ;; breakpoint) SECS=1560 ;;  # 20분 + 회복 관찰 5분
  *) echo "알 수 없는 PROFILE: $PROFILE"; exit 1 ;;
esac

RUN_ID="$(date +%Y%m%d-%H%M%S)-$PROFILE-$LABEL"
OUT="$REPO/infra/loadtest/k6/results/$LABEL/$RUN_ID"
mkdir -p "$OUT"

# ── 실행 전 조건 기록 (노이즈 통제 근거)
{
  echo "run_id=$RUN_ID profile=$PROFILE label=$LABEL base=$BASE"
  echo "local_time=$(date -Iseconds)"
  echo "git=$(git -C "$REPO" rev-parse --short HEAD)"
  echo "k6=$(k6 version | head -1)"
  # ICMP(ping)는 보안그룹에서 막혀 있어 TCP 연결 시간(= 왕복 1회)으로 잰다
  echo "--- RTT (Mac → EC2, TCP connect 10회, ms)"
  for _ in $(seq 1 10); do curl -s -o /dev/null -m 5 -w '%{time_connect}\n' "$BASE/"; done \
    | awk '{v=$1*1000; s+=v; if(NR==1||v<mn)mn=v; if(v>mx)mx=v} END{printf "min=%.1f avg=%.1f max=%.1f\n", mn, s/NR, mx}'
  echo "--- CPU 크레딧 (최근 10분)"
  aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUCreditBalance \
    --dimensions Name=InstanceId,Value="$INSTANCE_ID" --statistics Average --period 300 \
    --start-time "$(date -u -v-10M +%Y-%m-%dT%H:%M:%SZ)" --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --query 'Datapoints[].Average' --output text 2>&1
  echo "--- Mac 부하 (생성기가 병목이 아닌지)"; uptime
} > "$OUT/conditions.txt"

# ── EC2 수집기 배포 후 백그라운드 실행
scp -q -o LogLevel=ERROR -i "$KEY" "$REPO/scripts/loadtest/collect-server-metrics.sh" "$EC2:~/collect-server-metrics.sh"
"${SSH[@]}" "chmod +x ~/collect-server-metrics.sh && nohup ~/collect-server-metrics.sh '$RUN_ID' $SECS > /dev/null 2>&1 &"
sleep 3

# ── k6 실행 (raw 는 JSON 으로 보관 — percentile 은 여기서 다시 계산)
echo "▶ $RUN_ID"
k6 run --no-usage-report \
  -e PROFILE="$PROFILE" -e BASE="$BASE" -e RUN_ID="$RUN_ID" -e OUT_DIR="$OUT" \
  --out json="$OUT/raw.json.gz" \
  "$REPO/infra/loadtest/k6/seoganpyo.js" 2>&1 | tee "$OUT/k6.log"
K6_EXIT=${PIPESTATUS[0]}
echo "k6_exit=$K6_EXIT" >> "$OUT/conditions.txt"
echo "--- Mac 부하 (종료 시)" >> "$OUT/conditions.txt"; uptime >> "$OUT/conditions.txt"

# ── 서버 지표 회수 (수집기가 끝날 때까지 대기)
echo "서버 지표 수집 종료 대기..."
for _ in $(seq 1 60); do
  "${SSH[@]}" "test -f ~/loadtest-logs/$RUN_ID/after.txt" && break
  sleep 5
done
scp -q -r -o LogLevel=ERROR -i "$KEY" "$EC2:~/loadtest-logs/$RUN_ID" "$OUT/server"
echo "✔ 결과: $OUT (k6 exit=$K6_EXIT — 99 는 threshold 미달)"
