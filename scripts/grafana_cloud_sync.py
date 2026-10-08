"""Grafana Cloud 에 대시보드·알림 룰·Discord 연락처를 반영한다 (D10).

설정은 레포가 원본이다 — Grafana 화면에서 고친 것은 다음 실행 때 덮어써진다.
화면에서 고쳤다면 JSON 을 내보내 레포에 반영할 것.

    python3 scripts/grafana_cloud_sync.py            # 반영
    python3 scripts/grafana_cloud_sync.py --dry-run  # 무엇을 바꿀지만 출력
    python3 scripts/grafana_cloud_sync.py --test-notify  # 반영 후 Discord 로 테스트 알림 1건

비밀값은 SSM 에서 읽고 출력하지 않는다 (aws CLI 자격 증명 필요).
  /seoganpyo/ops/GRAFANA_SA_TOKEN       서비스 계정 토큰 (Editor)
  /seoganpyo/prod/DISCORD_ALERT_WEBHOOK  알림을 보낼 Discord 웹훅

반영 대상
  - 폴더 "서간표" (uid seoganpyo)
  - 대시보드  infra/observability/grafana-cloud/dashboards/*.json
  - 알림 룰    infra/observability/grafana-cloud/alert-rules.json
  - 연락처 seoganpyo-discord + 알림 정책: team=seoganpyo 라벨 → Discord (기존 기본 정책은 유지)
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

GRAFANA = "https://indigochickpea1864.grafana.net"
NAMESPACE = "stacks-1849564"   # /api/frontend/settings 의 namespace
REGION = "ap-northeast-2"
FOLDER_UID, FOLDER_TITLE = "seoganpyo", "서간표"
CONTACT_UID, CONTACT_NAME = "seoganpyo-discord", "seoganpyo-discord"
ROOT = Path(__file__).resolve().parent.parent
CLOUD = ROOT / "infra/observability/grafana-cloud"
DRY = "--dry-run" in sys.argv


def ssm(name: str) -> str:
    out = subprocess.run(
        ["aws", "ssm", "get-parameter", "--name", name, "--with-decryption", "--region", REGION,
         "--query", "Parameter.Value", "--output", "text"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


TOKEN = ssm("/seoganpyo/ops/GRAFANA_SA_TOKEN")


def api(method: str, path: str, body=None, ok404=False):
    req = urllib.request.Request(
        GRAFANA + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 # 화면에서도 고칠 수 있게 (provisioned 잠금 해제)
                 "X-Disable-Provenance": "true"})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if ok404 and e.code == 404:
            return None
        raise SystemExit(f"✗ {method} {path} → {e.code} {e.read().decode()[:300]}")


def step(msg):
    print(("[dry-run] " if DRY else "") + msg)


def ensure_folder():
    # 없는 폴더를 GET 하면 Grafana Cloud 는 404 대신 403 을 준다 — 목록에서 찾는다
    if any(f.get("uid") == FOLDER_UID for f in api("GET", "/api/folders")):
        step(f"폴더 '{FOLDER_TITLE}' 있음")
        return
    step(f"폴더 '{FOLDER_TITLE}' 생성")
    if not DRY:
        api("POST", "/api/folders", {"uid": FOLDER_UID, "title": FOLDER_TITLE})


def sync_dashboards():
    for f in sorted((CLOUD / "dashboards").glob("*.json")):
        d = json.loads(f.read_text())
        step(f"대시보드 {d['uid']} ({d['title']})")
        if not DRY:
            api("POST", "/api/dashboards/db", {"dashboard": d, "folderUid": FOLDER_UID, "overwrite": True,
                                                "message": "scripts/grafana_cloud_sync.py"})


def sync_contact_point():
    webhook = ssm("/seoganpyo/prod/DISCORD_ALERT_WEBHOOK")
    cp = {"uid": CONTACT_UID, "name": CONTACT_NAME, "type": "discord",
          "settings": {"url": webhook, "use_discord_username": False}, "disableResolveMessage": False}
    existing = [c for c in api("GET", "/api/v1/provisioning/contact-points") if c.get("uid") == CONTACT_UID]
    step(f"연락처 {CONTACT_NAME} {'갱신' if existing else '생성'} (Discord)")
    if not DRY:
        if existing:
            api("PUT", f"/api/v1/provisioning/contact-points/{CONTACT_UID}", cp)
        else:
            api("POST", "/api/v1/provisioning/contact-points", cp)


def sync_policy():
    tree = api("GET", "/api/v1/provisioning/policies")
    routes = [r for r in tree.get("routes") or [] if r.get("receiver") != CONTACT_NAME]
    routes.insert(0, {"receiver": CONTACT_NAME, "object_matchers": [["team", "=", "seoganpyo"]],
                      "group_by": ["alertname"], "group_wait": "30s", "group_interval": "5m",
                      "repeat_interval": "4h"})
    tree["routes"] = routes
    step(f"알림 정책: team=seoganpyo → {CONTACT_NAME} (기본 수신자 '{tree.get('receiver')}' 유지)")
    if not DRY:
        api("PUT", "/api/v1/provisioning/policies", tree)


def sync_rules():
    rules = json.loads((CLOUD / "alert-rules.json").read_text())
    for r in rules:
        r["folderUID"] = FOLDER_UID
        r.setdefault("orgID", 1)
        exists = api("GET", f"/api/v1/provisioning/alert-rules/{r['uid']}", ok404=True)
        step(f"알림 룰 {'갱신' if exists else '생성'}: {r['title']}")
        if not DRY:
            if exists:
                api("PUT", f"/api/v1/provisioning/alert-rules/{r['uid']}", r)
            else:
                api("POST", "/api/v1/provisioning/alert-rules", r)
    for group in sorted({r["ruleGroup"] for r in rules}):  # 평가 주기 1분
        if not DRY:
            g = api("GET", f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{group}")
            g["interval"] = 60
            api("PUT", f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{group}", g)


def test_notify():
    """새 알림 API(v1beta1)로 연락처에 테스트 알림을 보낸다 — 옛 receivers/test 는 410"""
    import base64
    name = base64.urlsafe_b64encode(CONTACT_NAME.encode()).decode().rstrip("=")
    webhook = ssm("/seoganpyo/prod/DISCORD_ALERT_WEBHOOK")
    r = api("POST", f"/apis/notifications.alerting.grafana.app/v1beta1/namespaces/{NAMESPACE}/receivers/{name}/test", {
        "integration": {"uid": CONTACT_UID, "type": "discord",
                        "settings": {"url": webhook, "use_discord_username": False}},
        "alert": {"labels": {"alertname": "서간표 알림 연결 테스트", "team": "seoganpyo"},
                  "annotations": {"summary": "[테스트] Grafana Cloud → Discord 알림 연결 확인",
                                  "description": "scripts/grafana_cloud_sync.py --test-notify. 실제 장애 아님."}}})
    step(f"테스트 알림: {r.get('status')} ({r.get('duration')})")


if __name__ == "__main__":
    ensure_folder()
    sync_dashboards()
    sync_contact_point()
    sync_policy()
    sync_rules()
    if "--test-notify" in sys.argv and not DRY:
        test_notify()
    print("완료" if not DRY else "dry-run 끝 — 아무것도 바꾸지 않음")
