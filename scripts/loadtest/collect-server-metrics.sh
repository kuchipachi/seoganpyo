#!/usr/bin/env bash
# 부하 테스트 중 EC2 서버 지표 수집 (USE method: 사용률·포화·에러) — docs/performance.md §2.5
#
# EC2 에서 실행 (scripts/loadtest/run.sh 가 ssh 로 호출):
#   ./collect-server-metrics.sh <RUN_ID> <초>
# 결과: ~/loadtest-logs/<RUN_ID>/
#
# 가벼운 도구만 쓴다 (수 MB) — 측정 대상과 같은 1 GiB 를 나눠 쓰므로 관측 스택(Prometheus 등)은 띄우지 않는다.
set -uo pipefail

RUN_ID=${1:?RUN_ID 필요}
SECS=${2:?수집 시간(초) 필요}
ENV_FILE=${ENV_FILE:-$HOME/seoganpyo/.env}
OUT=$HOME/loadtest-logs/$RUN_ID
mkdir -p "$OUT"

# ── 테스트 전 상태 (설정이 실제로 적용됐는지 증명)
{
  date -Is; uptime; free -m; cat /proc/sys/vm/swappiness
  for c in $(docker ps --format '{{.Names}}'); do
    docker inspect "$c" --format '{{.Name}} image={{.Config.Image}} id={{.Image}} mem={{.HostConfig.Memory}} swap={{.HostConfig.MemorySwap}} reserve={{.HostConfig.MemoryReservation}} restarts={{.RestartCount}}'
  done
} > "$OUT/before.txt" 2>&1

# ── DB 접속 정보 (.env 에서 읽기만, 출력하지 않음)
get_env() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed -E 's/^["'"'"']|["'"'"']$//g'; }
export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGCONNECT_TIMEOUT=5
PGHOST=$(get_env DB_HOST); PGPORT=$(get_env DB_PORT); PGDATABASE=$(get_env DB_NAME)
PGUSER=$(get_env DB_USER); PGPASSWORD=$(get_env DB_PASSWORD)

T="timeout $SECS"
# CPU(us/sy/st)·run queue(r)·메모리·swap in/out(si/so)
$T vmstat -t 1 > "$OUT/vmstat.log" 2>&1 &
# 네트워크 처리량
$T sar -n DEV 1 > "$OUT/net.log" 2>&1 &
# 디스크(swap 장치) 사용률·대기열
$T iostat -xz 1 > "$OUT/io.log" 2>&1 &
# 컨테이너별 CPU·메모리 (5초 간격 — docker stats 자체 비용 때문에 1초는 피함)
$T bash -c 'while true; do docker stats --no-stream --format "$(date +%T),{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}"; sleep 5; done' > "$OUT/docker_stats.csv" 2>&1 &
# 컨테이너 OOM·종료·재시작 이벤트
$T docker events --filter event=oom --filter event=die --filter event=restart \
  --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' > "$OUT/docker_events.log" 2>&1 &
# 커널 OOM killer
$T sudo dmesg -wT > "$OUT/dmesg_raw.log" 2>&1 &
# DB 연결 수 (state 별)
$T bash -c 'while true; do psql -Atc "select to_char(now(),'"'"'HH24:MI:SS'"'"'), coalesce(state,'"'"'null'"'"'), count(*) from pg_stat_activity where datname = current_database() group by 2" 2>&1 | tr "\n" " "; echo; sleep 5; done' > "$OUT/pg_activity.log" 2>&1 &

wait

# ── 테스트 후 상태
{
  date -Is; free -m
  for c in $(docker ps -a --format '{{.Names}}'); do
    docker inspect "$c" --format '{{.Name}} status={{.State.Status}} oomkilled={{.State.OOMKilled}} restarts={{.RestartCount}}'
  done
} > "$OUT/after.txt" 2>&1
grep -iE 'oom|killed process' "$OUT/dmesg_raw.log" > "$OUT/oom.log" || true
echo "collected: $OUT"
