# 성능 측정 기록

> 🟩 민지 — [cloud-migration-plan.md](./cloud-migration-plan.md) §2.8
> 개선을 수치로 남기는 문서입니다. 런북·포스트모템과는 별도로 둡니다.

## 1. Docker 이미지 최적화 (D3, 2026-09-24)

### 측정 환경

| 항목 | 값 |
| --- | --- |
| 빌드 머신 | MacBook Pro (Apple M1 Pro) — Docker Desktop 29.7.2, buildx v0.36.1 |
| 타깃 플랫폼 | `linux/amd64` (EC2 t3.micro 기준 — Apple Silicon 에서 에뮬레이션 빌드) |
| 빌드 옵션 | `docker buildx build --no-cache --platform linux/amd64 --load` |
| 공정성 조건 | 베이스 이미지는 미리 받아 둔 상태(pull 시간 제외), 매 빌드 전 BuildKit 컨텍스트 캐시 삭제(`buildx prune --filter type=source.local`) |
| 크기 기준 | `docker image inspect` 의 로컬(비압축) 크기. ECR 에 올라가는 압축 크기는 이보다 작음 |

### 결과

| 이미지 | 크기 before | 크기 after | 변화 | 빌드 시간 before → after |
| --- | --- | --- | --- | --- |
| **api** (backend) | 121.5 MB | **102.3 MB** | **−19.2 MB (−15.8%)** | 52s → **36s (−31%)** |
| ocr | 67.4 MB | 67.4 MB | 변경 없음 | 20s |
| frontend | 64.5 MB | 64.5 MB | 변경 없음 | 67s |
| **합계** | **253.4 MB** | **234.2 MB** | **−19.2 MB (−7.6%)** | |

### 무엇을 바꿨나

| 변경 | 효과 |
| --- | --- |
| backend `Dockerfile` 의 docker-cli 스테이지 삭제 | 이미지 −19.2 MB, 빌드 −16s. prod 는 docker.sock 을 마운트하지 않아 원래 쓸 수 없던 바이너리 (챗 도구는 #10 에서 자동 제외) |
| `frontend/.dockerignore` 커밋 (`.gitignore` 가 `.dockerignore` 를 무시하고 있어 레포에 없었음) | **빌드 실패 방지** — 아래 참고 |
| 루트 `.dockerignore` 신규 (허용 목록 방식) | `.env`·`*.pem` 등 비밀값이 빌드 컨텍스트에 섞이는 것 차단 |

### frontend — `.dockerignore` 가 없을 때 (재현)

`frontend/Dockerfile` 은 `COPY . .` 를 씁니다. `.dockerignore` 가 없는 개발 PC(예: 레포를 새로 받아 `pnpm install` 한 팀원)에서 빌드하면:

| | `.dockerignore` 없음 | 있음 |
| --- | --- | --- |
| 전송 컨텍스트 | **498.67 MB** (호스트 `node_modules` 포함) | 2.61 MB |
| 결과 | ❌ **빌드 실패** — `cannot copy to non-directory: .../node_modules/@radix-ui/react-accordion` | ✅ 성공 |

호스트(macOS)의 `node_modules` 가 deps 단계에서 설치한 Linux `node_modules` 위로 복사되며 충돌합니다. 기존에는 민지 로컬에만 `.dockerignore` 가 있어 드러나지 않았습니다.

### 측정하면서 알게 된 것

- **첫 측정은 불공정했다** — 처음 잰 before 값에는 베이스 이미지 pull 시간이 섞여 있었다(변경이 없는 ocr 이 44s → 19s 로 "빨라짐"). 베이스를 캐시한 뒤 다시 쟀다.
- **컨텍스트 전송량은 캐시 영향을 받는다** — BuildKit 은 같은 빌더에서 이전 컨텍스트와의 차이만 보낸다. 캐시를 지우지 않으면 6 kB 처럼 비현실적으로 작게 찍힌다.
- **루트 `.dockerignore` 의 크기 효과는 작다** (api 컨텍스트 14.57 MB → 13.47 MB) — BuildKit 이 `COPY` 대상 경로만 골라 전송하기 때문. 이 파일의 가치는 크기보다 **비밀값 차단**이다.
