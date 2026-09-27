"""CloudWatch 알람(SNS) → Discord 웹훅 변환.

CloudWatch 는 Discord 형식을 모르고, SNS 도 마찬가지다.
그 사이를 메우는 얇은 변환기.

    CloudWatch 알람 → SNS 토픽 → 이 함수 → Discord 웹훅

외부 패키지를 쓰지 않는다(urllib 만) — 의존성 없이 .zip 하나로 배포하기 위해.
requests 를 쓰면 레이어를 만들거나 패키징이 필요해진다.

환경변수
    DISCORD_WEBHOOK_URL  필수. Discord 채널 웹훅 URL
    DASHBOARD_URL        선택. embed 하단에 링크로 붙임
"""
import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "").strip()

# Discord embed color (10진수)
_COLOR = {
    "ALARM": 0xE74C3C,              # 빨강 — 임계 초과
    "OK": 0x2ECC71,                 # 초록 — 정상 복귀
    "INSUFFICIENT_DATA": 0xF1C40F,  # 노랑 — 데이터 부족
}
_EMOJI = {"ALARM": "🔴", "OK": "🟢", "INSUFFICIENT_DATA": "🟡"}
_LABEL = {"ALARM": "알람 발생", "OK": "정상 복귀", "INSUFFICIENT_DATA": "데이터 부족"}


def _build_embed(alarm: dict) -> dict:
    """CloudWatch 알람 JSON → Discord embed."""
    state = alarm.get("NewStateValue", "UNKNOWN")
    name = alarm.get("AlarmName", "(이름 없음)")
    reason = alarm.get("NewStateReason", "")
    trigger = alarm.get("Trigger", {}) or {}

    fields = [
        {"name": "알람", "value": f"`{name}`", "inline": False},
    ]

    # 지표 정보 — 어떤 값이 임계를 넘었는지
    metric = trigger.get("MetricName")
    if metric:
        threshold = trigger.get("Threshold")
        operator = trigger.get("ComparisonOperator", "")
        fields.append({
            "name": "지표",
            "value": f"{trigger.get('Namespace', '')} / {metric}",
            "inline": True,
        })
        if threshold is not None:
            fields.append({
                "name": "임계",
                "value": f"{operator} {threshold}",
                "inline": True,
            })

    # 어느 리소스인지 — 인스턴스가 여러 개일 때 구분에 필요
    dims = trigger.get("Dimensions") or []
    if dims:
        fields.append({
            "name": "대상",
            "value": "\n".join(f"{d.get('name')}: `{d.get('value')}`" for d in dims),
            "inline": False,
        })

    if reason:
        # Discord field 값 상한 1024자
        fields.append({"name": "사유", "value": reason[:1000], "inline": False})

    embed = {
        "title": f"{_EMOJI.get(state, '⚪')} {_LABEL.get(state, state)}",
        "color": _COLOR.get(state, 0x95A5A6),
        "fields": fields,
        "footer": {"text": alarm.get("Region", "")},
    }
    if alarm.get("StateChangeTime"):
        embed["timestamp"] = alarm["StateChangeTime"]
    if DASHBOARD_URL:
        embed["url"] = DASHBOARD_URL
    return embed


def _post(payload: dict) -> int:
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            # User-Agent 필수 — 없으면 urllib 기본값(Python-urllib/3.x)이 나가고
            # Discord 앞단 Cloudflare 가 봇으로 보고 403(error code 1010)으로 막는다.
            "User-Agent": "seoganpyo-alarm/1.0 (+https://github.com/kuchipachi/seoganpyo)",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.status


def lambda_handler(event, context):
    if not WEBHOOK:
        logger.error("DISCORD_WEBHOOK_URL 미설정 — 알림을 보낼 수 없음")
        return {"statusCode": 500, "body": "webhook not configured"}

    sent = 0
    for record in event.get("Records", []):
        raw = record.get("Sns", {}).get("Message", "")
        try:
            alarm = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # CloudWatch 알람이 아닌 SNS 메시지(테스트 발행 등)는 원문 그대로 전달
            alarm = None

        if isinstance(alarm, dict) and "NewStateValue" in alarm:
            payload = {"username": "서간표 알람", "embeds": [_build_embed(alarm)]}
        else:
            payload = {"username": "서간표 알람", "content": f"```\n{str(raw)[:1800]}\n```"}

        try:
            _post(payload)
            sent += 1
        except urllib.error.HTTPError as e:
            # 실패해도 다음 레코드는 처리 — SNS 재시도로 중복 발송되는 것보다 낫다
            logger.error("Discord 발송 실패 %s: %s", e.code, e.read()[:300])
        except Exception as e:
            logger.error("Discord 발송 실패: %s", e)

    logger.info("발송 %d건", sent)
    return {"statusCode": 200, "body": f"sent {sent}"}
