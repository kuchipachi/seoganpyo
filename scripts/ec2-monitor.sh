#!/usr/bin/env bash
# EC2 메모리·컨테이너 상태 점검 — D7~D8 RAM 튜닝용
#
# 사용법 (EC2 에서):
#   ./scripts/ec2-monitor.sh          한 번 출력
#   ./scripts/ec2-monitor.sh -w       5초 간격 반복 (Ctrl+C 로 종료)
#   ./scripts/ec2-monitor.sh -l       튜닝 로그에 append (docs/performance.md 용)
#
# 부하 테스트(§2.8)를 민지 PC 에서 돌리는 동안 이 스크립트를 EC2 에서 띄워두면
# OOM 임계점과 컨테이너별 메모리 사용량을 동시에 관찰할 수 있습니다.

set -uo pipefail

COMPOSE="docker compose -f $HOME/seoganpyo/docker-compose.yml -f $HOME/seoganpyo/docker-compose.prod.yml"
LOGFILE="$HOME/seoganpyo/tuning-$(date +%Y%m%d).log"

snapshot() {
    echo "════════════════════════════════════════════  $(date '+%F %T')"

    echo "── 메모리 ───────────────────────────────────"
    free -h

    echo
    echo "── swap 사용 상위 5 프로세스 ────────────────"
    # /proc 에서 프로세스별 swap 사용량 — free 만으로는 누가 쓰는지 모름
    for f in /proc/*/status; do
        awk '/^Name:/{n=$2} /^VmSwap:/{if ($2+0 > 0) printf "%8d kB  %s\n", $2, n}' "$f" 2>/dev/null
    done | sort -rn | head -5 || echo "  (swap 사용 없음)"

    echo
    echo "── 컨테이너 ─────────────────────────────────"
    docker stats --no-stream \
        --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}' 2>/dev/null \
        || echo "  docker stats 실패"

    echo
    echo "── 상태 / 재시작 횟수 ───────────────────────"
    # 재시작 횟수가 늘면 OOM Killer 에 당했을 가능성
    docker ps -a --format '{{.Names}}' --filter 'name=seoganpyo' | while read -r c; do
        printf '%-22s %-12s restarts=%s\n' \
            "$c" \
            "$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null)" \
            "$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null)"
    done

    echo
    echo "── OOM Killer 로그 (최근 5건) ───────────────"
    if sudo dmesg 2>/dev/null | grep -i 'killed process\|out of memory' | tail -5 | grep -q .; then
        sudo dmesg | grep -i 'killed process\|out of memory' | tail -5
        echo "  ⚠️  OOM 발생 — 포스트모템 대상 (§8.4)"
    else
        echo "  없음"
    fi

    echo
}

case "${1:-}" in
    -w|--watch)
        trap 'echo; echo "중단됨"; exit 0' INT
        while true; do
            clear
            snapshot
            echo "5초 후 갱신… (Ctrl+C 종료)"
            sleep 5
        done
        ;;
    -l|--log)
        snapshot | tee -a "$LOGFILE"
        echo "→ $LOGFILE 에 기록"
        ;;
    -h|--help)
        sed -n '2,12p' "$0"
        ;;
    *)
        snapshot
        ;;
esac
