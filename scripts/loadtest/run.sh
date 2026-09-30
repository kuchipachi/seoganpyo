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
# 결과: infra/loadtest/k6/results/<CONFIG_LABEL>/<RUN_ID>/  (근거 데이터로 커밋 — results/README.md)
#
# 서버 접속: 22번 포트는 닫혀 있다 (SSM Run Command 배포, D14~D15). 서버 지표 수집은 Session Manager 경유 SSH.
#   1) Session Manager 플러그인 설치 (brew install --cask session-manager-plugin, 또는 AWS 배포 zip 을 ~/.local/bin 에)
#   2) ~/.ssh/config:
#        Host seoganpyo
#          HostName <인스턴스 ID>
#          User ec2-user
#          IdentityFile ~/.ssh/server-key.pem
#          ProxyCommand sh -c "PATH=$HOME/.local/bin:$PATH aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters portNumber=%p"
#   3) BASE=https://<EC2_IP>.nip.io EC2=ec2-user@seoganpyo scripts/loadtest/session.sh <LABEL> "load:3 breakpoint:1"
set -uo pipefail

PROFILE=${1:?PROFILE 필요 (smoke|load|stress|breakpoint)}
LABEL=${2:?CONFIG_LABEL 필요 (예: baseline)}
REPO=$(cd "$(dirname "$0")/../.." && pwd)
# 운영 주소 — 공개 레포라 IP 를 코드에 두지 않는다. BASE 가 없으면 레포 .env 의 DOMAIN 을 쓴다 (EC2 는 .env 에 있음)
if [ -z "${BASE:-}" ]; then
  DOMAIN=$(grep -s '^DOMAIN=' "$REPO/.env" | cut -d= -f2-)
  BASE=${DOMAIN:+https://$DOMAIN}
fi
: "${BASE:?BASE 필요 — 예) BASE=https://<EC2_IP>.nip.io  (또는 레포 .env 에 DOMAIN=<EC2_IP>.nip.io)}"
EC2=${EC2:-ec2-user@$(echo "$BASE" | sed -E 's#^https?://##; s#\.nip\.io.*$##')}   # nip.io 도메인에서 IP 추출
KEY=${KEY:-$HOME/.ssh/server-key.pem}
INSTANCE_ID=${INSTANCE_ID:-i-0cf5fbf562ec4017b}
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
# ssh -n + 원격 stdin/stdout/stderr 를 모두 끊어야 ssh 가 수집기 종료를 기다리지 않고 즉시 돌아온다
# (끊지 않으면 k6 가 수집 시간만큼 늦게 시작해 서버 지표가 부하 구간과 어긋남)
ssh -n -o BatchMode=yes -o LogLevel=ERROR -i "$KEY" "$EC2" \
  "chmod +x ~/collect-server-metrics.sh; nohup ~/collect-server-metrics.sh '$RUN_ID' $SECS < /dev/null > /dev/null 2>&1 &"
# ⚠️ 'chmod && nohup ... &' 로 쓰면 & 가 묶음 전체에 걸려 그 서브셸이 ssh 출력을 붙잡는다 → ';' 로 분리
# 수집기가 실제로 시작됐는지 확인 (before.txt 생성)
for _ in $(seq 1 10); do
  "${SSH[@]}" "test -f ~/loadtest-logs/$RUN_ID/before.txt" < /dev/null && break
  sleep 1
done
echo "collector_started=$(date -Iseconds)" >> "$OUT/conditions.txt"

# ── k6 실행 (raw 는 JSON 으로 보관 — percentile 은 여기서 다시 계산)
echo "▶ $RUN_ID"
echo "k6_started=$(date -Iseconds)" >> "$OUT/conditions.txt"
k6 run --no-usage-report \
  -e PROFILE="$PROFILE" -e BASE="$BASE" -e RUN_ID="$RUN_ID" -e OUT_DIR="$OUT" \
  --out json="$OUT/raw.json.gz" \
  "$REPO/infra/loadtest/k6/seoganpyo.js" 2>&1 | tee "$OUT/k6.log"
K6_EXIT=${PIPESTATUS[0]}
echo "k6_exit=$K6_EXIT" >> "$OUT/conditions.txt"
echo "--- Mac 부하 (종료 시)" >> "$OUT/conditions.txt"; uptime >> "$OUT/conditions.txt"

# ── 서버 지표 회수 (수집기가 끝날 때까지 대기)
echo "서버 지표 수집 종료 대기..."
# k6 가 일찍 끝나도(breakpoint 자동 중단) 수집기는 SECS 까지 돈다 — 회복 관찰 구간까지 받으려면 끝까지 기다린다
for _ in $(seq 1 $(( SECS / 5 + 24 ))); do
  "${SSH[@]}" "test -f ~/loadtest-logs/$RUN_ID/after.txt" && break
  sleep 5
done
scp -q -r -o LogLevel=ERROR -i "$KEY" "$EC2:~/loadtest-logs/$RUN_ID" "$OUT/server"
echo "✔ 결과: $OUT (k6 exit=$K6_EXIT — 99 는 threshold 미달)"
