# 서간표 운영 Runbook

> 장애 발생 시 이 문서를 먼저 확인하세요.
> Discord 알림 → 해당 섹션으로 이동 → 체크리스트 순서대로 실행.

---

## 1. 서비스 개요

| 컨테이너 | 포트 | 역할 |
|---|---|---|
| seoganpyo-frontend | 3000 | Next.js 프론트엔드 |
| seoganpyo-api | 8080 | FastAPI 백엔드 |
| seoganpyo-redis | 6379 | 인증 OTP 임시 저장 (3분 TTL) |
| seoganpyo-ocr | 8001 | Mistral Pixtral 시간표 OCR 호출 마이크로서비스 |
| PostgreSQL (외부) | 8000 | 163.239.77.77 / DB: seoganpyo |

**CI/CD 흐름:**
```
Push → Jenkins
  dev:  Lint + Test
  main: Pre-Deploy → Docker Compose → Post-Deploy
  → Discord 알림 (성공/실패)
```

---

## 2. Discord 알림 해석 방법

Jenkins 빌드 결과는 Discord에 **Embed 카드** 형태로 전송됩니다.

### ✅ 배포 성공 카드
```
✅ 빌드 #42 배포 성공
─────────────────────────────
🌿 브랜치        | 🐳 컨테이너
main             | api · frontend · redis · ocr 정상 기동
─────────────────────────────
배포 완료: 2026-04-11 09:32:01 KST
```
→ 별도 조치 불필요

### ❌ 빌드 실패 카드
```
❌ 빌드 #43 실패 — Deploy 단계
─────────────────────────────
🌿 브랜치        | 🚨 실패 단계
main             | Deploy
─────────────────────────────
📋 에러 로그 미리보기
  [seoganpyo-api] ERROR: Connection refused (port 8000)
  ...
─────────────────────────────
🤖 AI 장애 분석
  [핵심 원인] PostgreSQL 연결 실패 — DB_HOST 환경변수 오설정 또는 DB 서버 다운
  [영향 범위] 로그인, 강의 조회, 모든 인증 필요 API 불가
  [즉시 조치] 1. .env DB_HOST 확인  2. DB 서버 ping  3. docker compose restart backend
  [재발 방지] DB 헬스체크를 pre-deploy.sh에 추가
─────────────────────────────
빌드 시각: 2026-04-11 09:35:22 KST
```

**실패 단계별 의미:**

| 실패 단계 | 의미 | 담당 |
|----------|------|------|
| CI - Lint & Check | Python ruff 오류 또는 프론트 빌드 실패 | 코드 작성자 |
| Test & Coverage | pytest 테스트 실패 | 코드 작성자 |
| Pre-Deploy Check | .env 누락 또는 Docker 미실행 | DevOps |
| Deploy | 컨테이너 빌드/실행 실패 | DevOps |
| Post-Deploy Check | 배포 후 헬스체크 실패 | DevOps |

---

## 3. 초기 대응 체크리스트 (5분 이내)

장애 알림 수신 즉시 아래 순서로 확인합니다.

```bash
# 1. 컨테이너 상태 확인 (30초)
docker compose ps

# 2. 에러 로그 확인 (1분)
docker compose logs seoganpyo-api --tail=50
docker compose logs seoganpyo-frontend --tail=30

# 3. 헬스체크 (30초)
curl -s http://localhost:8080/ | python3 -m json.tool
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/

# 4. DB 연결 확인 (1분)
docker compose exec -T seoganpyo-api python -c \
  "from app.database import engine; engine.connect(); print('DB OK')"

# 5. Redis 확인 (30초)
docker compose exec -T seoganpyo-redis redis-cli ping
```

---

## 4. 컨테이너별 트러블슈팅

### 4-1. seoganpyo-api (백엔드) 장애

**증상:** `/api/v1/*` 응답 없음, 500 오류

```bash
# 로그 확인
docker compose logs seoganpyo-api --tail=100 -f

# 재시작
docker compose restart seoganpyo-api

# 환경변수 확인
docker compose exec -T seoganpyo-api env | grep -E "DB_|SECRET|GROQ|REDIS"

# 강제 재빌드
docker compose up --build -d seoganpyo-api
```

### 4-2. seoganpyo-frontend (프론트엔드) 장애

**증상:** 화면이 안 뜸, 빈 화면

```bash
docker compose logs seoganpyo-frontend --tail=50
docker compose build --no-cache seoganpyo-frontend
docker compose up -d seoganpyo-frontend
```

### 4-3. seoganpyo-redis (Redis) 장애

**증상:** 이메일 인증번호가 작동 안 함

```bash
docker compose restart seoganpyo-redis
docker compose restart seoganpyo-api   # 백엔드도 재시작 필요
docker compose exec -T seoganpyo-redis redis-cli ping  # PONG 응답 확인
```

### 4-4. seoganpyo-ocr (OCR 서비스) 장애

**증상:** 시간표 이미지 업로드 실패

```bash
docker compose logs seoganpyo-ocr --tail=50
docker compose restart seoganpyo-ocr
# OCR 서비스는 Mistral API 호출 래퍼라 시작 즉시 준비됨 (모델 로딩 없음)
curl -s http://localhost:8001/health
```

---

## 5. 자주 발생하는 장애 사례

### CASE 1. 로그인/회원가입이 안 될 때
**원인 A:** `users` 테이블 컬럼 누락 (interests, target_careers)
```bash
docker compose exec -T seoganpyo-api python -c "
from app.database import engine
import sqlalchemy as sa
with engine.connect() as conn:
    conn.execute(sa.text(\"ALTER TABLE users ADD COLUMN IF NOT EXISTS interests TEXT DEFAULT ''\"))
    conn.execute(sa.text(\"ALTER TABLE users ADD COLUMN IF NOT EXISTS target_careers TEXT DEFAULT ''\"))
    conn.commit()
    print('done')
"
```

**원인 B:** `users.is_approved` 컬럼 누락 — 기존 DB에 컬럼이 없으면 `if not user.is_approved` 체크 시 AttributeError/컬럼 오류 발생, 기존 사용자 전원 로그인 불가
```bash
docker compose exec -T seoganpyo-api python -c "
from app.database import engine
import sqlalchemy as sa
with engine.connect() as conn:
    conn.execute(sa.text(\"ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN NOT NULL DEFAULT TRUE\"))
    conn.commit()
    print('done')
"
```
> ⚠️ `DEFAULT TRUE` 로 설정해야 기존 사용자의 로그인이 유지됩니다. 신규 가입자는 `DEFAULT FALSE`(이메일 인증 후 승인)이지만, 이미 가입된 계정은 즉시 로그인 가능 상태여야 합니다.

### CASE 2. 게시글 등록이 안 될 때
**원인:** `posts` 테이블 컬럼 누락
```bash
docker compose exec -T seoganpyo-api python -c "
from app.database import engine
import sqlalchemy as sa
with engine.connect() as conn:
    conn.execute(sa.text(\"ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_path VARCHAR(500)\"))
    conn.execute(sa.text(\"ALTER TABLE posts ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)\"))
    conn.execute(sa.text(\"ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_anonymous BOOLEAN DEFAULT FALSE\"))
    conn.commit()
    print('done')
"
```

### CASE 3. 강의계획서 버튼이 안 뜰 때
**원인:** `data/syllabi/`에 PDF가 있지만 DB에 hash 미등록
```bash
docker compose exec -T seoganpyo-api python -c "
import hashlib, re
from pathlib import Path
from app.database import engine
import sqlalchemy as sa

with engine.connect() as conn:
    for f in sorted(Path('data/syllabi').glob('*.pdf')):
        m = re.search(r'(CSE\d{4})', f.name)
        if not m: continue
        row = conn.execute(sa.text(\"SELECT course_id FROM courses WHERE course_code=:c AND year=2026 AND semester=1\"), {'c': m.group(1)}).first()
        if not row: continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        exists = conn.execute(sa.text('SELECT 1 FROM course_details WHERE course_id=:id'), {'id': row[0]}).first()
        if exists:
            conn.execute(sa.text('UPDATE course_details SET pdf_hash=:h WHERE course_id=:id'), {'h': h, 'id': row[0]})
        else:
            conn.execute(sa.text('INSERT INTO course_details (course_id, pdf_hash) VALUES (:id, :h)'), {'id': row[0], 'h': h})
        conn.commit()
        print(f'OK: {m.group(1)}')
"
```

### CASE 4. OTP 인증번호가 안 올 때
1. `.env`의 `SENDER_EMAIL`, `SENDER_PASSWORD` 확인
2. Redis 컨테이너 상태 확인: `docker compose ps seoganpyo-redis`
3. Redis 재시작: `docker compose restart seoganpyo-redis && docker compose restart seoganpyo-api`

### CASE 5. DB 연결 실패 (ConnectionRefused / OperationalError)
```bash
# DB 서버 도달 가능 여부 확인
ping 163.239.77.77
nc -zv 163.239.77.77 8000

# .env DB 설정 재확인
cat .env | grep DB_

# 백엔드 재시작
docker compose restart seoganpyo-api
```

### CASE 6. Groq API 오류 (강의계획서 요약 실패)
```bash
# API 키 유효 여부 확인
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY" | python3 -m json.tool | head -5

# 키 만료 시 → console.groq.com에서 새 키 발급 후 .env 업데이트
```

---

## 6. 로그 확인 명령어 모음

```bash
# 전체 로그 실시간
docker compose logs -f

# 특정 컨테이너 최근 N줄
docker compose logs seoganpyo-api --tail=100
docker compose logs seoganpyo-frontend --tail=50
docker compose logs seoganpyo-ocr --tail=50

# 에러만 필터
docker compose logs seoganpyo-api 2>&1 | grep -iE "error|exception|traceback|critical"

# AI 로그 분석 (로컬 실행)
python3 scripts/analyze_logs.py \
  --build-number manual \
  --branch $(git branch --show-current) \
  --failed-stage "Manual Check" \
  --webhook "$DISCORD_WEBHOOK" \
  --containers seoganpyo-api seoganpyo-frontend seoganpyo-ocr
```

### 6.1 EC2 운영 환경 (AWS)

EC2 는 override 파일을 함께 지정해야 합니다. 별칭을 등록해 두면 편합니다.

```bash
# ~/.bashrc 에 등록 (1회)
alias dcp='docker compose -f ~/seoganpyo/docker-compose.yml -f ~/seoganpyo/docker-compose.prod.yml'

dcp ps                  # 컨테이너 상태
dcp logs -f             # 전체 로그
dcp logs caddy --tail 50    # HTTPS·인증서 문제
dcp restart backend     # 개별 재시작
```

### 6.2 메모리 점검 — `scripts/ec2-monitor.sh`

t3.micro(913MiB + swap 1.5GiB)에서 OOM 을 추적하는 스크립트입니다.

```bash
./scripts/ec2-monitor.sh        # 한 번 출력
./scripts/ec2-monitor.sh -w     # 5초 간격 반복
./scripts/ec2-monitor.sh -l     # 로그 파일에 append
```

출력 항목:

| 항목 | 보는 이유 |
| --- | --- |
| `free -h` | 전체 여유 메모리·swap 사용량 |
| swap 상위 5 프로세스 | **누가** swap 을 쓰는지 (`free` 로는 알 수 없음) |
| `docker stats` | 컨테이너별 사용량·제한 대비 비율 |
| **재시작 횟수** | 늘어나면 OOM Killer 에 당했을 가능성 |
| `dmesg` OOM 로그 | 확정 증거 — 나오면 포스트모템 대상 |

> 💡 부하 테스트(§2.8)를 민지 PC 에서 돌리는 동안 EC2 에서 `-w` 로 띄워 두면
> OOM 임계점을 실시간으로 관찰할 수 있습니다.

**수동 확인:**
```bash
free -h
docker stats --no-stream
sudo dmesg | grep -i 'killed process\|out of memory' | tail
docker inspect -f '{{.RestartCount}}' seoganpyo-api
```

---

## 7. 배포 체크리스트

### 배포 전
- [ ] `.env` 파일 존재 및 필수값 (`DB_*`, `SECRET_KEY`, `ADMIN_SECRET_KEY`, `SENDER_*`, `GROQ_API_KEY`) 확인
- [ ] `data/syllabi/`, `static/uploads/posts/` 디렉토리 존재 확인
- [ ] DB 스키마 변경 시 `ALTER TABLE` 먼저 실행
- [ ] Docker 데몬 실행 중인지 확인: `docker ps`

### 배포 후
- [ ] `http://localhost:8080/` → `{"message": "서간표 통합 서버가 준비되었습니다"}` 확인
- [ ] `http://localhost:3000/` 프론트엔드 로딩 확인
- [ ] 로그인 → 과목 검색 → 게시판 글 작성 동작 확인
- [ ] `docker compose ps` 전체 컨테이너 `Up` 상태 확인

---

## 8. 모니터링

### 8-1. 관리자 페이지 모니터링

`http://<VDI_IP>:3000/admin` 에서 실시간 상태 확인 가능.

| 메뉴 | 경로 | 내용 |
|---|---|---|
| 대시보드 | `/admin` | 서버 상태, 유저 수, 게시글 수, 미처리 신고 수 |
| 모니터링 | `/admin/monitoring` | API 서버 및 DB 연결 상태 확인 |
| 사용자 관리 | `/admin/users` | 유저 목록, 게시 권한 토글, 탈퇴 처리 |
| 신고 관리 | `/admin/reports` | 신고 내역 확인, 처리/기각 |
| 교수 데이터 | `/admin/professors` | 크롤링 실행, 연구분야 요약 생성 |

관리자 계정 로그인: `noey@sogang.ac.kr` (또는 role=admin 계정)

---

### 8-2. 헬스체크 API

```bash
# 서버 상태 + 통계 (관리자 토큰 필요)
TOKEN="<admin_token>"
curl -s http://localhost:8080/admin/health \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 응답 예시
# {
#   "status": "ok",
#   "admin": "심하연",
#   "stats": { "users": 31, "posts": 42, "pending_reports": 2 }
# }
```

---

### 8-3. 관측 스택 (Loki + Promtail + Grafana)

> 평소에는 띄우지 않음. 로그 분석이 필요할 때만 옵트인.

```bash
# 관측 스택 시작
make up-obs

# Grafana 접속: http://localhost:3001
# 기본 계정: admin / admin (GF_SECURITY_ADMIN_* 환경변수로 변경 가능)

# 관측 스택 종료
make down-obs

# 관측 스택 로그 확인
make logs-obs
```

**Loki 로그 쿼리 예시 (Grafana Explore):**
```
{container="seoganpyo-api"} |= "ERROR"
{container="seoganpyo-api"} |= "502"
{container="seoganpyo-frontend"} |= "error"
```

---

### 8-4. Ollama (교수 연구분야 요약)

```bash
# Ollama 서버 상태 확인
curl http://localhost:11434

# 설치된 모델 확인
ollama list

# 서버 실행 (백그라운드)
ollama serve &

# 컨테이너 내부에서 Ollama 연결 테스트
docker compose exec seoganpyo-api python3 -c "
import httpx
r = httpx.get('http://host.docker.internal:11434', timeout=5)
print('연결:', r.status_code)
"
```

> Ollama가 실행 중이지 않으면 `/admin/professors/{id}/summarize` 호출 시 502 반환.

---

## 9. 서비스 명령어

```bash
# 로컬 개발 (--reload + HMR + 팀 DB 연결)
make dev

# VDI 배포 (pre-check → build → post-check)
make prod

# 중지
make down

# 로그 스트리밍
make logs

# 컨테이너 상태
make ps
```

직접 실행이 필요한 경우:

```bash
# 코드 변경 후 재빌드 (전체)
docker compose up --build -d

# 특정 서비스만 재빌드
docker compose up --build -d seoganpyo-api
docker compose up --build -d seoganpyo-frontend

# 완전 초기화 (볼륨 포함 삭제 — 주의)
docker compose down -v --remove-orphans
```

---

## 9. VDI 서버 환경 설정

### 최초 1회 설정

**1. 포트 포워딩 (외부 접근용)**
```bash
# VDI 방화벽에서 아래 포트 오픈 필요 (학교 네트워크 정책 확인)
# 3000 — Next.js 프론트엔드
# 8080 — FastAPI 백엔드
# 8001 — OCR 서비스 (내부용, 외부 오픈 불필요)
# 6379 — Redis (내부용, 외부 오픈 불필요)

# Ubuntu UFW 기준
sudo ufw allow 3000/tcp
sudo ufw allow 8080/tcp
sudo ufw reload
sudo ufw status
```

**2. Docker & Docker Compose 설치 확인**
```bash
docker --version        # 24.x 이상 권장
docker compose version  # v2.x 이상 권장
```

**3. 프로젝트 클론 및 환경변수 설정**
```bash
git clone https://github.com/gibunijjaejo/Opensource_Project.git
cd Opensource_Project
cp .env.example .env
# .env 편집: 실제 값으로 채우기
```

**4. 외부 PostgreSQL 연결 확인**
```bash
psql -h 163.239.77.77 -p 8000 -U <DB_USER> -d seoganpyo -c "SELECT 1"
```

**5. 최초 배포**
```bash
make prod
```

### 접속 주소

| 환경 | URL |
|------|-----|
| 프론트엔드 | `http://<VDI_IP>:3000` |
| 백엔드 API | `http://<VDI_IP>:8080` |
| API 문서 | `http://<VDI_IP>:8080/docs` |

> VDI IP는 `hostname -I` 또는 `ip addr show` 로 확인

---

## 10. 에스컬레이션 기준

| 상황 | 대응 |
|------|------|
| 컨테이너 재시작으로 해결됨 | 본인 처리 후 Discord에 조치 내용 공유 |
| DB 서버(외부) 다운 | 팀 전체 공지 + DB 관리자(학교 측) 연락 |
| 데이터 유실 의심 | 즉시 `docker compose stop` 후 팀 리더에게 에스컬레이션 |
| 보안 키/비밀번호 노출 의심 | `.env` 즉시 교체 + 팀 전체 공유 |
| 2회 이상 반복 장애 | GitHub Issue 생성 후 근본 원인 분석 |

---

## 11. Jenkins 수동 분석 (긴급 시)

Discord AI 분석 카드를 받지 못했거나 직접 분석하고 싶을 때:

```bash
# 로컬에서 수동으로 AI 분석 실행
DISCORD_WEBHOOK="your-webhook-url" \
python3 scripts/analyze_logs.py \
  --build-number 0 \
  --branch main \
  --failed-stage "Manual" \
  --containers seoganpyo-api seoganpyo-frontend seoganpyo-ocr
```

> ⚠️ `GROQ_API_KEY`가 `.env`에 있어야 실행됩니다.
