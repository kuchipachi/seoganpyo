#!/usr/bin/env bash
# 배포 후 스모크 테스트 — 운영 도메인 기준
#
# 사용법 (EC2):
#   ./scripts/smoke-test.sh                       # 검사만
#   DISCORD_ALERT_WEBHOOK=... ./scripts/smoke-test.sh   # 실패 시 Discord 알림
#   BASE=https://54.180.181.46.nip.io ./scripts/smoke-test.sh
#
# 왜 필요한가 (docs/postmortems/2026-09-26-caddy-backend-routing.md):
#   1차 배포 때 홈 화면 200 과 컨테이너 health 만 보고 성공으로 판단했는데,
#   실제로는 /auth /history /upload 가 프론트로 새고 있어 아무도 로그인할 수 없었다.
#   홈은 프론트가 서빙하므로 200 이 나온다 — 그것만으로는 아무것도 보장되지 않는다.
#   → 프론트·백엔드 **양쪽**과 라우팅 분기를 모두 확인한다.

set -uo pipefail

BASE="${BASE:-https://54.180.181.46.nip.io}"
WEBHOOK="${DISCORD_ALERT_WEBHOOK:-}"
FAILED=()

check() {
    local name=$1 path=$2 want=$3
    local got
    got=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${BASE}${path}" 2>/dev/null)
    if [ "$got" = "$want" ]; then
        printf '  ✅ %-34s %s\n' "$name" "$got"
    else
        printf '  ❌ %-34s %s (기대 %s)\n' "$name" "$got" "$want"
        FAILED+=("$name: ${path} → ${got} (기대 ${want})")
    fi
}

echo "=== 스모크 테스트 — ${BASE} ==="
echo

echo "[프론트엔드]"
check "홈" "/" 200
check "로그인 페이지" "/login" 200

echo
echo "[백엔드 — /backend prefix 라우팅]"
# 포스트모템 1호의 핵심: 이 경로들이 프론트로 새면 인증이 전부 깨진다
check "OpenAPI 문서" "/backend/docs" 200
check "OpenAPI 스펙" "/backend/openapi.json" 200
check "과목 목록" "/backend/api/v1/courses?year=2026&semester=1&limit=1" 200
# 인증 필요 → 401 이 정상. 307 이면 프론트로 샌 것
check "수강이력 (인증 필요)" "/backend/history/me" 401

echo
echo "[슬래시 정규화 — root-path 확인]"
# 끝에 / 가 붙으면 FastAPI 가 리다이렉트하는데, --root-path 가 없으면
# Location 에서 /backend 가 빠지고 http 로 다운그레이드된다 → 프론트로 샘
loc=$(curl -sI --max-time 10 "${BASE}/backend/api/v1/courses/" | tr -d '\r' | awk '/^[Ll]ocation:/{print $2}')
if [ -z "$loc" ]; then
    printf '  ✅ %-34s (리다이렉트 없음)\n' "courses/ 정규화"
elif [[ "$loc" == https://*/backend/* ]]; then
    printf '  ✅ %-34s %s\n' "courses/ 정규화" "$loc"
else
    printf '  ❌ %-34s %s\n' "courses/ 정규화" "$loc"
    FAILED+=("슬래시 정규화: Location=${loc} — root-path/proxy-headers 확인")
fi

echo
echo "[보안]"
check "메트릭 외부 차단" "/backend/metrics" 404

echo
echo "[컨테이너]"
if command -v docker >/dev/null 2>&1; then
    DC="docker compose -f $HOME/seoganpyo/docker-compose.yml -f $HOME/seoganpyo/docker-compose.prod.yml"
    unhealthy=$($DC ps --format '{{.Name}} {{.Status}}' 2>/dev/null \
        | grep -v 'healthy\|Up' || true)
    if [ -z "$unhealthy" ]; then
        echo "  ✅ 전부 정상"
    else
        echo "  ❌ 비정상:"
        echo "$unhealthy" | sed 's/^/     /'
        FAILED+=("컨테이너 비정상: $(echo "$unhealthy" | tr '\n' ' ')")
    fi
else
    echo "  ⏭  docker 없음 — 건너뜀"
fi

echo
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "=== ✅ 전체 통과 ==="
    exit 0
fi

echo "=== ❌ ${#FAILED[@]}건 실패 ==="
printf '  - %s\n' "${FAILED[@]}"

# Discord 알림 — 웹훅이 설정된 경우만
if [ -n "$WEBHOOK" ]; then
    lines=$(printf '• %s\\n' "${FAILED[@]}")
    curl -s -X POST -H 'Content-Type: application/json' \
        -d "{\"username\":\"서간표 배포\",\"embeds\":[{\"title\":\"🚨 배포 검증 실패\",\"description\":\"${lines}\",\"color\":11543338,\"footer\":{\"text\":\"${BASE}\"}}]}" \
        "$WEBHOOK" >/dev/null && echo "  → Discord 알림 발송"
fi

exit 1
