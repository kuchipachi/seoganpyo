#!/usr/bin/env bash
# autoheal 재시작 루프 감시 — cron 으로 5분마다 실행
#
#   */5 * * * * /home/ec2-user/seoganpyo/scripts/autoheal-guard.sh >> /home/ec2-user/seoganpyo/guard.log 2>&1
#
# 왜 필요한가:
#   autoheal 은 unhealthy 컨테이너를 재시작하지만 **근본 원인은 고치지 못한다.**
#   2026-09-27 장애 주입 검증에서 DB 가 막혀 있는 동안 컨테이너가 starting 에
#   머무는 것을 확인했다(약 2분 27초). DB 가 계속 죽어 있었다면 재시작 →
#   unhealthy → 재시작을 무한 반복했을 것이다.
#
#   willfarrell/autoheal 에는 재시작 횟수 제한 옵션이 없다. 그래서 밖에서 센다.
#
# 무엇을 하는가:
#   최근 WINDOW 분 동안 재시작이 THRESHOLD 회를 넘으면
#     1) Discord 로 알린다 (SNS → Lambda 경유, 알람 파이프라인 재사용)
#     2) autoheal 을 멈춘다 — 무한 재시작보다 "멈춘 채로 사람을 기다리는" 편이 낫다
#
#   멈추는 이유: 재시작이 반복되면 그 사이 요청은 전부 실패하고, 로그도 계속
#   갈려나가 원인 분석이 어려워진다. 차라리 마지막 상태로 두는 게 조사에 유리하다.

set -uo pipefail

WINDOW=${WINDOW:-30}              # 분
THRESHOLD=${THRESHOLD:-5}         # 이 횟수를 초과하면 루프로 판단
TOPIC_ARN=${TOPIC_ARN:-arn:aws:sns:ap-northeast-2:833823555621:seoganpyo-alarms}
REGION=${REGION:-ap-northeast-2}
STATE_FILE=${STATE_FILE:-$HOME/seoganpyo/.autoheal-guard.state}

DC="docker compose -f $HOME/seoganpyo/docker-compose.yml -f $HOME/seoganpyo/docker-compose.prod.yml"

notify() {
    local title=$1 msg=$2
    # CloudWatch 알람과 같은 형식으로 보내 Lambda 가 그대로 렌더링하게 한다
    aws sns publish --topic-arn "$TOPIC_ARN" --region "$REGION" \
        --message "{\"AlarmName\":\"${title}\",\"NewStateValue\":\"ALARM\",\"NewStateReason\":\"${msg}\",\"Region\":\"ap-northeast-2\"}" \
        >/dev/null 2>&1 \
        && echo "  → Discord 알림 발송" \
        || echo "  → 알림 발송 실패 (SNS 권한·네트워크 확인)"
}

# autoheal 이 떠 있지 않으면 할 일 없음
if ! docker ps --format '{{.Names}}' | grep -q '^seoganpyo-autoheal$'; then
    echo "$(date +%F' '%T)  autoheal 미실행 — 건너뜀"
    exit 0
fi

# 최근 WINDOW 분간 autoheal 이 재시작시킨 횟수
# 로그 예: "Container /seoganpyo-api (abc123) found to be unhealthy - Restarting container now"
COUNT=$(docker logs --since "${WINDOW}m" seoganpyo-autoheal 2>&1 \
        | grep -ci 'restarting container' || true)

echo "$(date +%F' '%T)  최근 ${WINDOW}분 재시작 ${COUNT}회 (임계 ${THRESHOLD})"

if [ "$COUNT" -le "$THRESHOLD" ]; then
    # 정상으로 돌아왔으면 상태 파일 정리 — 다음 루프 때 다시 알림이 가도록
    [ -f "$STATE_FILE" ] && { rm -f "$STATE_FILE"; echo "  루프 해소 — 상태 초기화"; }
    exit 0
fi

echo "  ⚠️ 재시작 루프 감지"

# 이미 대응했으면 중복 알림·중복 정지 방지
if [ -f "$STATE_FILE" ]; then
    echo "  이미 대응함 ($(cat "$STATE_FILE")) — 건너뜀"
    exit 0
fi

date +%F' '%T > "$STATE_FILE"

# 조사에 쓸 근거를 먼저 남긴다 — autoheal 을 멈추면 로그가 더 안 쌓인다
SNAP="$HOME/seoganpyo/loop-$(date +%Y%m%d-%H%M%S).log"
{
    echo "=== autoheal 재시작 루프 ==="
    echo "최근 ${WINDOW}분 ${COUNT}회"
    echo
    echo "--- 컨테이너 상태"; $DC ps
    echo; echo "--- backend 로그 (최근 100줄)"; docker logs --tail 100 seoganpyo-api 2>&1
    echo; echo "--- autoheal 로그"; docker logs --since "${WINDOW}m" seoganpyo-autoheal 2>&1
    echo; echo "--- 메모리"; free -h
} > "$SNAP" 2>&1
echo "  스냅샷: $SNAP"

# 무한 재시작보다 멈춘 채로 사람을 기다리는 편이 낫다
docker stop seoganpyo-autoheal >/dev/null 2>&1 \
    && echo "  autoheal 중지" \
    || echo "  autoheal 중지 실패"

notify "autoheal 재시작 루프" \
    "최근 ${WINDOW}분 동안 ${COUNT}회 재시작. 근본 원인이 해결되지 않은 상태. autoheal 을 중지했으니 수동 조사 필요. 스냅샷: $(basename "$SNAP")"

echo "  복구: 원인 해결 후  docker start seoganpyo-autoheal && rm $STATE_FILE"
exit 1
