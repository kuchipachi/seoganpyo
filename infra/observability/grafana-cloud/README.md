# Grafana Cloud 설정 (D10)

레포가 원본입니다. Grafana 화면에서 고친 것은 다음 반영 때 덮어써지므로, 화면에서 고쳤다면 JSON 을 내보내 여기에 반영하세요.

| 파일 | 내용 |
| --- | --- |
| `dashboards/seoganpyo-metrics.json` | 서간표 API 메트릭 — RPS, p50/p95/p99, 4xx/5xx, 엔드포인트별 p95 |
| `dashboards/seoganpyo-overview.json` | 서간표 통합 모니터링 — 컨테이너별 로그 양, ERROR 로그, OCR 실패 |
| `alert-rules.json` | 알림 룰 4개 → Discord (`team=seoganpyo` 라벨로 라우팅) |

로컬 관측 스택의 대시보드(`../grafana/provisioning/dashboards/json/`)와 같고 데이터 소스 uid 만 다릅니다 (`loki` → `grafanacloud-logs`, `prometheus` → `grafanacloud-prom`).
수집기 Alloy 가 로컬 설정과 같은 라벨(`container`, `compose_project`, `job="seoganpyo-api"`)을 붙이므로 쿼리는 그대로입니다.

## 반영

```bash
python3 scripts/grafana_cloud_sync.py --dry-run      # 무엇이 바뀌는지만
python3 scripts/grafana_cloud_sync.py                # 반영
python3 scripts/grafana_cloud_sync.py --test-notify  # 반영 + Discord 테스트 알림
```

필요: aws CLI 자격 증명 — SSM `/seoganpyo/ops/GRAFANA_SA_TOKEN`(서비스 계정, Editor), `/seoganpyo/prod/DISCORD_ALERT_WEBHOOK`

## 알림 룰

| 알림 | 조건 | 등급 | 데이터 없을 때 |
| --- | --- | --- | --- |
| API 5xx 비율 5% 초과 | 5분 비율 > 5%, 5분 지속 | critical | 정상 |
| API 응답 p95 1초 초과 | p95 > 1초, 10분 지속 (평상시 약 0.13초) | warning | 정상 |
| API 메트릭 수집 실패 | `up` < 1, 3분 지속 | critical | **알림** — Alloy·EC2 가 멈춰도 잡힘 |
| 컨테이너 자동 재시작 | autoheal 로그 `Restarting` 5분 내 1건 이상 | critical | 정상 |

5xx 비율·p95 는 **사용자 요청만** 본다 — `/metrics`(Alloy 수집)·`/healthz`·`/`(헬스체크)는 뺀다. 사용자가 없을 때 내부 요청만으로 p95 가 계산돼 오탐이 날 수 있어서다 (10/08 기준 24시간 백엔드 요청이 전부 내부 요청이었음).

⚠️ T1 동시 처리 한도의 503 거절도 5xx 로 잡힙니다 — **부하 테스트 중에는 5xx 알림이 오는 게 정상**입니다.
인프라 알림(EC2 상태 검사·CPU 크레딧 등)은 CloudWatch → Discord (🟦 하연) 가 따로 담당합니다.
