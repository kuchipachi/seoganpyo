# 과부하 교착 로컬 재현

[포스트모템 2026-09-27](../../../docs/postmortems/2026-09-27-db-pool-deadlock.md)의 장애를 운영 서버를 건드리지 않고 재현합니다.
운영(EC2)과 같게 api 컨테이너를 **CPU 1코어·메모리 512MB·단일 uvicorn**으로 제한합니다.

```bash
# 레포 루트에서
docker build -t seoganpyo-api:repro -f Dockerfile .
cd scripts/loadtest/repro
docker compose -p repro up -d
# 운영과 같은 데이터 (강의계획서 PDF 37개 필요 — data/syllabi/)
(cd ../../.. && DB_HOST=localhost DB_PORT=55432 DB_USER=postgres DB_PASSWORD=repro DB_NAME=seoganpyo \
  PYTHONPATH=. python scripts/seed_courses_from_syllabi.py --apply)

# 실험 1: 현재 운영 설정 (풀 5+10, 동시 처리 한도 없음) → 교착, 약 16분 뒤 회복
RATE=60 DUR=60s ./run-overload.sh pool15

# 실험 2: 풀을 스레드풀(40)보다 크게 → 여전히 교착 (가설 반증)
DB_POOL_SIZE=45 DB_MAX_OVERFLOW=0 docker compose -p repro up -d --force-recreate api
RATE=60 DUR=60s ./run-overload.sh pool45

# 실험 3: 동시 처리 한도 15 → 교착 없음, 즉시 회복
docker compose -p repro -f compose.yml -f compose.limit.yml up -d --force-recreate api
RATE=60 DUR=60s ./run-overload.sh limit15

docker compose -p repro down
```

`run-overload.sh` 는 강의 목록 API 에 60초 과부하를 건 뒤, 10초마다 API 응답과 `pg_stat_activity` 를 기록하며
회복까지 걸린 시간과 분당 `QueuePool` 타임아웃 수를 `result-<라벨>.txt` 에 남깁니다.
