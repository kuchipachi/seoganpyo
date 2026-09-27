# 부하 테스트 결과 (근거 데이터)

[docs/performance.md](../../../../docs/performance.md) 의 수치는 모두 이 폴더의 raw 데이터에서 `scripts/loadtest/analyze.py` 로 다시 계산한 것입니다.

| 폴더 | 내용 |
| --- | --- |
| `baseline/` | 튜닝 전 베이스라인 (2026-09-27) — smoke 1 · load 5 · stress 3 · breakpoint 1, `session.log` |
| `baseline/incident-20260927/` | breakpoint 후 교착 장애 증거 (재시작 직전 `pg_stat_activity`·스레드 수·분당 풀 타임아웃) |
| `repro-local-20260927/` | 로컬 재현 실험 3개 — 풀 15 / 풀 45 / 동시 처리 한도 15 ([재현 방법](../../../../scripts/loadtest/repro/)) |
| `invalid-ssh-block-20260927/` | **무효** — 측정 스크립트 버그로 서버 지표가 부하 구간과 어긋난 실행. 보고서 수치에 쓰지 않음 (performance.md §3.6) |
| `smoke-check/` | 파이프라인 첫 검증 |

## 실행 폴더 구조 (`<날짜-시각>-<프로필>-<설정>/`)

| 파일 | 내용 |
| --- | --- |
| `conditions.txt` | git 커밋, RTT, CPU 크레딧, Mac 부하, 수집기·k6 시작 시각 (정렬 검증) |
| `raw.json.gz` | k6 raw 샘플 — percentile 재계산용 |
| `summary.json`, `k6.log` | k6 요약·실행 로그 |
| `server/` | EC2 지표: `vmstat.log` `io.log` `net.log` `docker_stats.csv` `docker_events.log` `pg_activity.log` `oom.log` `before.txt` `after.txt` |

커널 부팅 로그 전체(`dmesg_raw.log`)는 커밋하지 않습니다 — OOM 관련 줄만 `oom.log` 에 추려 둡니다.

```bash
python3 scripts/loadtest/analyze.py run baseline/<실행 폴더>
python3 scripts/loadtest/analyze.py label baseline load     # 5회 집계
```
