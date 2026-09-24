# 서간표 AWS 클라우드 마이그레이션 계획

> 학교 서버(163.239.77.x) → **AWS 단일 클라우드** 이전
> 목표: 클라우드에서 운영하고, 보이고(관측), 알림이 오는 서비스 — 크레딧 안에서 6개월 운영
> 작성 2026-09-20 · 개정 2026-09-23
>
> 📅 매일 보는 체크리스트: [migration-schedule.md](./migration-schedule.md)

> 🏗️ 실제 구축한 네트워크·보안그룹·EC2·RDS 구성과 근거: [aws-infra-design.md](./aws-infra-design.md)
> 📦 ECR·IAM 권한 설계: [aws-ecr-iam-design.md](./aws-ecr-iam-design.md)

## 담당자

| | 이름 | 맡는 레이어 | 배경 |
| --- | --- | --- | --- |
| 🟦 | **하연** | 클라우드 인프라 · 보안 · 운영 자동화 | 클라우드 설계 담당, AWS 계정 명의자 |
| 🟩 | **민지** | 앱 레이어 · 컨테이너 · 관측 | 백엔드 담당, 클라우드는 처음 |
| 🟪 | **페어** | 둘이 같이 | RAM 튜닝, 알람, 문서 마무리 |

문서 전체에서 담당은 🟦 하연 / 🟩 민지 / 🟪 페어로 표시합니다. 역할 상세는 [§12](#12-역할-분담).

---

## 0. 전제 조건 (확정)

| 항목 | 결정 | 관련 절 |
| --- | --- | --- |
| 클라우드 | **AWS 단일** (EC2 + RDS + ECR + S3) | — |
| AWS 계정 | **하연 명의** (2026-09 신규 생성) — 결제 책임 하연 | §2.1 |
| 예산 | **크레딧 소진형 무료 플랜** — 현재 $120, 활동 완료 시 최대 $200 / **6개월** | §2.1 |
| 리전 | **서울 `ap-northeast-2`** — Billing·크레딧 조회, CloudFront용 ACM만 `us-east-1` | §2.1 |
| 레포 | 원본 보존, **`kuchipachi/seoganpyo`** 로 이력째 복사 (✅ 완료) | §13 |
| 기존 데이터 | **복구 불가** — 스키마 재생성 + 재수집 | §3 |
| LLM | Ollama(`exaone3.5:7.8b`)는 **팀원 PC에 유지** (AWS 미배포) | §4 |
| 관측 | **1차에 Grafana Cloud** (자체 호스팅 폐기) | §8 |
| 부하 테스트 | **JMeter 포함** — RAM 튜닝 전후 측정 | §2.8 |
| 업로드 이미지 | 1차엔 EC2 로컬 저장 — **재생성 시 소실 감수**, 2차에 S3 | §5 |
| 범위 제외 | DefectDojo | §6 |
| 목표 직무 | Public Cloud 인프라 구축·운영 | §12 |

### 목표 아키텍처

```
 사용자 ──HTTPS──> Caddy(EC2) ──┬──> frontend  :3000  (Next.js)
                               └──> backend   :8000  (FastAPI) ──> ocr-service :8001
                                        │
                     ┌──────────────────┼──────────────────────────┐
                     ▼                  ▼                          ▼
              RDS PostgreSQL      Redis (EC2 동거)            외부 API
              db.t4g.micro        컨테이너                   Mistral / Gemini
                                                                   │
                                                     팀원 PC Ollama (배치 요약)
 ── 1차 ─────────────────────────────────────────────────────────────
              ECR ── (Mac에서 buildx amd64 push) ──> EC2 pull
              Grafana Cloud <── Alloy (로그·메트릭)  →  알람 → Discord
 ── 2차 ─────────────────────────────────────────────────────────────
              GitHub Actions (OIDC) → ECR ──SSM Run Command──> EC2
              S3 + CloudFront (이미지)
```

**1차**: EC2 1대(t3.micro, 1GB RAM)에서 Docker Compose로 `frontend + backend + ocr + redis + caddy + alloy`를 돌립니다. 이미지는 **로컬 Mac에서 `linux/amd64`로 빌드해 ECR에 push**하고, EC2는 pull만 합니다(EC2에서 빌드하면 OOM). 배포 자체는 수동입니다. 실질적인 제약은 RAM이고, §2.2에서 다룹니다.

> Route 53은 유료($0.5/월)라 쓰지 않습니다. 도메인 없이 **EC2 퍼블릭 IP + `nip.io`** 로 Caddy 자동 HTTPS를 씁니다.

---

## 1. 일정 — 2단계 분할

21일치 작업을 한 덩어리로 잡으면 중간에 막혔을 때 **남는 게 없습니다.** 1차만 끝나도 포트폴리오에 쓸 수 있게 둘로 나눴습니다.

### 1차 — "클라우드에서 돌아가고, 보이고, 알림이 온다"

| # | 내용 | 담당 | 소요 | 상태 |
| --- | --- | --- | --- | --- |
| 0 | AWS 계정 · 예산 알람 · IAM · VPC · 비용 Deny 정책 | 🟦 하연 | 1.5일 | ✅ |
| 1 | 레포 분리 (§13) | 🟩 민지 | 0.5일 | ✅ |
| 2 | 학교 서버 잔재 제거 · CLAUDE.md 정정 (§6) | 🟩 민지 | 0.5일 | |
| 3 | SG · 서브넷 그룹 · 태깅 → **RDS 생성** (§2.3, §2.5) | 🟦 하연 | 0.5일 | |
| 4 | Ollama 경로 환경변수화 + 503 처리 (§4.3 B) | 🟩 민지 | 0.5일 | |
| 5 | Grafana 부재 대응 — iframe·`query_prometheus` (§8.1) | 🟩 민지 | 0.5일 | |
| 6 | Docker 이미지 최적화 + before/after 측정 (§2.2, §6) | 🟩 민지 | 1일 | |
| 7 | EC2 + swap + Docker + Caddy (§2.2, §2.3) | 🟦 하연 | 1일 | |
| 8 | **ECR + EC2 인스턴스 역할(pull 권한)** (§7.2) | 🟦 하연 | 0.5일 | |
| 9 | JMeter/InfluxDB 별도 compose 분리 (§2.8) | 🟩 민지 | 0.25일 | |
| 10 | 데이터 재수집·적재 + RDS 연결 풀 (§3) | 🟩 민지 | 1.5일 ⚠️ | |
| 11 | 첫 배포 — amd64 빌드 → ECR push → EC2 pull | 🟪 페어 | (7·8·10에 포함) | |
| 12 | **베이스라인 측정** — JMeter 3회 반복 (§2.8) | 🟩 민지 | 0.5일 | |
| 13 | **RAM 튜닝** + 부하 재측정 + 포스트모템 (§2.2, §8.4) | 🟪 하연 1.25 / 민지 1.25 | 2.5일 | |
| 14 | 관측 — Alloy · 대시보드 임포트 (§8.2) | 🟩 민지 | 1.5일 | |
| 15 | 알람 룰 — Grafana Alerting (§8.3) | 🟩 민지 | 0.5일 | |
| 16 | 알람 룰 — CloudWatch + **Discord 연동** (§8.3) | 🟦 하연 | 0.5일 | |

**1차 소계**: 🟦 하연 **5.25일** / 🟩 민지 **8.0일** (계 13.25일)

### 2차 — 자동화 · 스토리지 · 운영 문서

| # | 내용 | 담당 | 소요 |
| --- | --- | --- | --- |
| 17 | SSM Parameter Store — `.env` 이관 (§2.4) | 🟦 하연 | 0.5일 |
| 18 | **GitHub OIDC + IAM 신뢰 정책** (§7.1) | 🟦 하연 | 2.5일 |
| 19 | SSM Run Command 배포 (§7.1) | 🟦 하연 | 1.5일 |
| 20 | S3 전환 + 최소 권한 IAM (§5) | 🟩 민지 | 1.5일 |
| 21 | **RDS 백업·복구 훈련** (§2.5) | 🟩 민지 | 0.5일 |
| 22 | 관측 고도화 — `query_prometheus` 토큰 인증 (§8.2-5) | 🟩 민지 | 0.5일 |
| 23 | **비용 분석** — Cost Explorer, 만료 후 예상액 (§2.6) | 🟦 하연 | 0.5일 |
| 24 | 런북 — 배포·**롤백** (§2.7) | 🟦 하연 | 0.25일 |
| 25 | 런북 — 장애 확인 순서·접속 정보 (§2.7) | 🟩 민지 | 0.25일 |
| 26 | README / 이 문서 갱신 | 🟪 페어 | 0.5일 |
| (선택) | RDS 자동 중지 — EventBridge + Lambda (§2.5) | 🟩 민지 | 0.5일 |

**2차 소계**: 🟦 하연 **5.5일** / 🟩 민지 **3.0일** (+선택 0.5) (계 8.5일)

### 총 비중

| | 🟦 하연 | 🟩 민지 | 계 |
| --- | --- | --- | --- |
| 1차 | 5.25 | 8.0 | 13.25 |
| 2차 | 5.5 | 3.0 (+0.5) | 8.5 |
| **총계** | **10.75일 (49%)** | **11.0일 (51%)** | **21.75일** |

> 1차는 민지, 2차는 하연 쪽이 무겁습니다. 총량은 비슷하지만 **시기가 어긋납니다.** 1차 후반(D6·D10)에 하연이 비면 §12 아키텍처 결정 기록을 쓰고, 2차에 민지가 비면 선택 과제(RDS 자동 중지)를 맡습니다.

### 시나리오별 추정 (달력 기준 실작업일, 2인 병렬)

| 시나리오 | 조건 | 1차 | 전체 |
| --- | --- | --- | --- |
| 최선 | 강의 엑셀 확보 + 막힘 없음 | 9일 | 14일 |
| **현실** | 엑셀 확보 + 첫 AWS 시행착오 | **10~11일** | **16~18일** |
| 최악 | 엑셀 없음 → 더미 시드 작성 | 13~14일 | 20일+ |

> ⚠️ **병렬화 한계**: RDS 엔드포인트(🟦) → 데이터 적재(🟩), EC2(🟦) → SSH 터널(🟩)이 직렬입니다. 레이어로 역할을 나눈 이유가 이것입니다 — 접점을 6개로 줄였습니다(§12).

---

## 2. AWS 리소스 설계

### 2.1 크레딧 모델 · 비용 — 🟦 하연

> 🔴 **예전 "12개월 무료 티어"가 아닙니다.** AWS는 2025-07-15부터 신규 계정을 **크레딧 소진형 무료 플랜**으로 바꿨고, 이 계정은 그 이후에 만들어졌습니다.

| | 구 모델 (~2025-07) | **현재 적용** |
| --- | --- | --- |
| 방식 | 12개월 사용량 한도 | **크레딧 차감** |
| EC2 / RDS | 750h/월 무료 | 크레딧에서 차감 |
| 기한 | 12개월 | **6개월 또는 크레딧 소진 — 먼저 오는 쪽** (≈ 2027-03) |
| 만료 후 | 종량 과금 전환 | **Paid 전환 안 하면 계정 폐쇄** |

**크레딧**: 가입 $100 + 온보딩 활동 1건당 $20, 최대 $200. 현재 **$120**(Budgets 완료). **EC2·RDS·Lambda·Bedrock 활동을 모두 채우면 $200**이 됩니다 — 비용 계획은 $200 확보를 전제로 합니다. Lambda는 §2.5 자동 중지로, Bedrock은 콘솔 플레이그라운드 1회 호출로 채웁니다.

#### 월 예상 비용 (서울, 상시 가동, 추정치 — Cost Explorer로 실측해 갱신)

| 리소스 | 월 비용 | 비고 |
| --- | --- | --- |
| EC2 t3.micro | ~$10 | 730h |
| RDS db.t4g.micro (Single-AZ) | ~$15 | **가동 시간 기준 — 데이터 양 무관** |
| **퍼블릭 IPv4 주소** | **~$3.6** | 2024-02부터 유료($0.005/h) — Elastic IP 포함 |
| EBS 30GB gp3 | ~$2.7 | |
| RDS 스토리지 20GB | ~$2.9 | |
| **합계** | **~$34/월 (≈ $1.13/일)** | |

| 크레딧 | 상시 가동 | RDS 월 20일 가동 (~$29/월) |
| --- | --- | --- |
| $120 (현재) | 약 3.5개월 | 약 4.1개월 |
| **$200 (목표)** | **약 5.9개월** | **6개월 기한까지 충분** |

> 💡 **"DB에 조금만 담으면 싸다"는 틀린 말입니다.** RDS 비용은 데이터 양이 아니라 인스턴스 가동 시간으로 매겨집니다. 줄이려면 가동 시간을 줄여야 합니다(§2.5 중지 전략).

#### 항상 무료 (크레딧 차감 없음, 월 한도 내)

| 서비스 | 한도 |
| --- | --- |
| CloudFront | 1TB 전송/월 |
| Lambda | 100만 요청/월 |
| CloudWatch | 지표 10개, 알람 10개, 로그 5GB |
| SNS / SQS | 100만 요청/월 |
| 데이터 전송(아웃바운드) | 100GB/월 |

#### 절대 만들지 말 것 — 크레딧 급소진

| 리소스 | 월 비용 | 대안 |
| --- | --- | --- |
| **ALB** | ~$16 | **Caddy on EC2** |
| **NAT Gateway** | ~$32 | 퍼블릭 서브넷만 |
| **RDS Multi-AZ** | 인스턴스 비용 2배 | Single-AZ |
| Secrets Manager | $0.4/시크릿 | **SSM Parameter Store** (무료) |
| Performance Insights 장기 보존 | 유료 | 끄기 |

> ⚠️ 위 표의 앞 세 개 중 하나만 실수로 만들어도 **한 달에 크레딧 절반이 날아갑니다.** IAM Deny 정책으로 막아 둡니다.

#### 비용 방어 IAM Deny 정책 `SeoganpyoDenyCostly` — 🟦 하연 (✅ 생성, 보강 필요)

D1에 만든 정책은 "RDS 클러스터"를 막고 있는데, **Multi-AZ는 클러스터가 아니라 `CreateDBInstance`의 옵션**이라 이 정책으로는 막히지 않습니다. 아래처럼 보강합니다:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Sid": "DenyALBandNAT", "Effect": "Deny",
      "Action": ["elasticloadbalancing:CreateLoadBalancer", "ec2:CreateNatGateway"],
      "Resource": "*" },
    { "Sid": "DenyRdsMultiAz", "Effect": "Deny",
      "Action": ["rds:CreateDBInstance", "rds:ModifyDBInstance", "rds:RestoreDBInstanceFromDBSnapshot"],
      "Resource": "*",
      "Condition": { "Bool": { "rds:MultiAz": "true" } } },
    { "Sid": "DenyBigRds", "Effect": "Deny",
      "Action": ["rds:CreateDBInstance", "rds:RestoreDBInstanceFromDBSnapshot"],
      "Resource": "*",
      "Condition": { "StringNotEquals": { "rds:DatabaseClass": "db.t4g.micro" } } },
    { "Sid": "DenyBigEc2", "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": { "StringNotEquals": { "ec2:InstanceType": "t3.micro" } } }
  ]
}
```

> 적용 후 콘솔에서 Multi-AZ RDS 생성을 시도해 **거부되는지 한 번 확인**하세요(권한 오류가 뜨면 성공). 이 확인 자체가 이력서의 "비용 가드레일" 근거가 됩니다.

#### 리전

**서울 `ap-northeast-2`** 로 통일합니다 — 팀과 크롤링 대상(`cs.sogang.ac.kr`)이 한국에 있고, 부하 테스트 수치가 네트워크 지연에 오염되지 않아야 합니다.

> ⚠️ 예외: Billing·크레딧 조회는 `us-east-1`, 2차 CloudFront용 ACM 인증서도 **반드시 `us-east-1`** 에서 발급합니다.
> ⚠️ 다른 리전에 리소스를 만들고 잊는 것이 과금 사고의 흔한 원인입니다. 콘솔 우상단 리전이 **서울**인지 매번 확인하세요.

### 2.2 1GB RAM — 핵심 제약 — 🟪 페어

현재 `docker-compose.yml`의 메모리 예약 합계는 **1GB**(backend 512M + frontend 256M + ocr 256M)이고, t3.micro 전체가 1GB입니다. 여기에 Caddy·Redis·Alloy가 더해집니다. **그대로 올리면 OOM으로 죽습니다.**

해결책 (순서대로):

1. **swap 2GB** (필수, 🟦 하연 — EC2 생성 당일)
   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```
2. **이미지는 EC2에서 빌드하지 않기** (🟩 민지) — 1차는 로컬 Mac에서, 2차는 GitHub Actions에서 빌드 → ECR push → EC2는 pull만. t3.micro에서 `pnpm build`는 거의 확실히 OOM입니다.
   ```bash
   # ⚠️ Apple Silicon Mac은 기본이 arm64 → t3.micro(x86)에서 exec format error
   docker buildx build --platform linux/amd64 -t <ecr>/seoganpyo-api:<tag> --push .
   ```
3. **메모리 예약 하향** (🟩 민지) — backend 256M / frontend 256M / ocr 192M, `NODE_OPTIONS=--max-old-space-size=256`
4. **프론트를 EC2에서 빼는 안** — S3 + CloudFront 정적 호스팅. 단 `next.config`가 standalone 서버 모드라 SSR 페이지가 있으면 불가 → 기본안은 EC2 유지 + 3번 제한.

> ⚠️ **첫 배포(D5)는 3번 적용 후에** 하세요. 기존 예약값 그대로 띄우면 바로 OOM입니다. 일부러 겪어 보고 기록하려면 그대로 띄우고 **포스트모템 1호**로 남기세요(§8.4).
>
> 💡 **대안 검토**: t3.small(2GB, ~$19/월)로 올리면 제약이 거의 사라지지만 크레딧 수명이 약 1개월 줄어듭니다. 1GB 제약 안에서 튜닝한 경험 자체가 포트폴리오 서사이므로 기본안은 t3.micro입니다.

### 2.3 네트워크 · 보안 그룹 — 🟦 하연

```
sg-web : 0.0.0.0/0 → 80, 443          (Caddy)
         <팀원 IP>/32 → 22            (SSH — 2차 SSM 도입 후 닫기)
sg-rds : sg-web 에서만 → 5432          (퍼블릭 액세스 OFF)
```

- **퍼블릭 서브넷만** 사용 (프라이빗 서브넷 = NAT Gateway 필요 = 유료). RDS 서브넷 그룹용으로 **AZ가 다른 서브넷 2개**가 필요합니다.
- RDS는 퍼블릭 액세스 비활성. 로컬(🟩 민지)에서는 EC2를 거친 SSH 터널로 접속합니다:
  ```bash
  ssh -L 5432:<rds-endpoint>:5432 ec2-user@<ec2-ip>
  ```

### 2.4 시크릿 관리 — 🟦 하연 (등록) / 🟩 민지 (키 목록)

- **1차**: EC2의 `~/seoganpyo/.env`에 직접 둡니다 — `chmod 600`, 절대 커밋 금지.
- **2차**: **SSM Parameter Store(SecureString, 무료)** 로 이관. 배포 시 `get-parameters-by-path`로 `.env`를 생성하고, EC2는 인스턴스 역할로 키 없이 접근합니다.
  ```bash
  aws ssm put-parameter --name /seoganpyo/prod/SECRET_KEY --type SecureString --value '...'
  ```

**이관 대상 키 (🟩 민지가 확정 → 🟦 하연 등록)**: ✅ 확정 — **[env-reference.md](./env-reference.md)** (필수 11개 · URL 3개 · 선택, SecureString/String 구분, EC2 `.env` 최소 구성 포함)

### 2.5 RDS 운영

#### 생성 체크리스트 — 🟦 하연 (D2)

- [ ] 템플릿 **개발/테스트** ← "프로덕션"을 고르면 Multi-AZ가 기본값
- [ ] 클래스 `db.t4g.micro` / **Multi-AZ 끄기**
- [ ] 스토리지 **20GB gp3** / **스토리지 자동 조정 끄기**
- [ ] **퍼블릭 액세스 끄기** / 보안그룹 `sg-rds`
- [ ] 백업 보존 7일
- [ ] **Performance Insights 끄기**
- [ ] 태그 `Project=seoganpyo` `Env=prod` `Owner=hayeon`

> 현재 데이터 규모는 `static/` 884KB + 강의·교수 테이블 수준입니다 — 20GB의 1%도 안 씁니다.

#### 중지 전략 — 🟦 하연

RDS는 **최대 7일까지 중지**할 수 있고, 중지 중엔 인스턴스 비용이 나가지 않습니다(스토리지만 과금).

```
작업하는 날 → RDS 시작    |    안 하는 날 → RDS 중지
```

> ⚠️ **7일이 지나면 자동으로 다시 켜집니다.** 계속 꺼 두려면 주 1회 다시 중지해야 합니다.
> 💡 **(선택, 🟩 민지 2차)** EventBridge 스케줄 + Lambda로 자동 중지하면 "운영 자동화" 항목이 하나 늘고, Lambda 온보딩 크레딧 $20도 받습니다. Lambda는 항상 무료 한도 내입니다.

#### 백업·복구 훈련 — 🟩 민지 (2차)

**자동 백업이 켜져 있는 것과 복원을 해 본 것은 다릅니다.**

| 항목 | 내용 |
| --- | --- |
| 수동 스냅샷 | 1회 생성 |
| **복원 훈련** | 스냅샷 → 새 인스턴스 복원 → **데이터 검증** → 원본 유지 확인 |
| 기록 | 소요 시간·절차를 런북(§2.7)에 |

> ⚠️ 복원은 **새 인스턴스를 만듭니다.** 검증 직후 삭제하세요 — 두 대가 동시에 떠 있으면 크레딧이 2배 속도로 줄어듭니다.
> 2차에 하는 이유: 1차엔 데이터가 재수집본이라 복원 훈련의 가치가 낮습니다.

### 2.6 비용 관리 — 🟦 하연 (2차)

"무료 한도 안에 머물렀다"보다 **"크레딧 $200 안에서 6개월을 설계했다"** 가 더 강한 서사입니다.

1. **태깅** (1차부터) — 모든 리소스에 `Project=seoganpyo` `Env=prod` `Owner=<이름>`
2. **Cost Explorer** 월별 추이(태그별 그룹화) + 크레딧 소진 속도
3. **크레딧 고갈 예상일** = 잔여 크레딧 ÷ 일 평균 차감액
4. **절감 실험 + 측정** — 실제로 바꿔 보고 수치를 남깁니다
   - RDS 중지 전략 적용 전후 일 차감액
   - EBS 30GB → 실사용 기준 축소
   - 야간 EC2 중지 시뮬레이션
5. **6개월 후 결정** — Paid 전환 / 서비스 종료 / 타 플랫폼 이전 중 택일 (만료 1개월 전까지)

→ 산출물: `docs/cost-analysis.md`

> 📊 **수치 3호 (측정 후 채움)**: "상시 가동 시 일 $X → RDS 중지 전략 후 일 $Y, 예상 수명 N개월 → M개월"

### 2.7 런북 — 🟦 하연 (배포·롤백) / 🟩 민지 (장애·접속) (2차)

운영 직무에서 문서는 산출물이 아니라 **업무 그 자체**입니다. 기존 `docs/runbook.md`를 갱신합니다.

| 항목 | 담당 | 내용 |
| --- | --- | --- |
| 배포 절차 | 🟦 하연 | SSM Run Command 기준 |
| **롤백 절차** | 🟦 하연 | **이전 ECR 태그로 되돌리기** |
| 장애 시 확인 순서 | 🟩 민지 | 헬스체크 → 로그(Loki) → 메트릭 → 컨테이너 상태 |
| 접속 정보 | 🟩 민지 | SSH, RDS 터널(§2.3), Grafana |

> 🔴 **롤백 절차가 없으면 배포 자동화는 반쪽입니다.**

### 2.8 성능 측정 — 🟩 민지 (1차)

산출물은 `docs/performance.md` — 런북·포스트모템과 **별도 파일**입니다.

#### 기존 자산 (재사용)

| 자산 | 위치 |
| --- | --- |
| 시나리오 | `infra/loadtest/jmeter/seoganpyo-smoke.jmx` — `GET /`, `GET /api/v1/courses` |
| 실행 타깃 | `Makefile`의 `jmeter-run` (`THREADS`/`RAMPUP`/`DURATION`/`BASE_HOST`) |
| 결과 저장 | InfluxDB 1.8 + Grafana 대시보드 (`docker-compose.observability.server.yml`) |

> ⚠️ JMeter·InfluxDB는 삭제 대상인 `docker-compose.observability.server.yml`에 들어 있습니다 → **`docker-compose.loadtest.yml`로 먼저 분리**한 뒤 원본을 지웁니다(§6).
> ⚠️ **부하 생성기를 t3.micro에서 돌리지 마세요.** 측정 대상과 같은 1GB를 나눠 쓰면 수치가 무의미해집니다 — **민지 PC에서 `BASE_HOST=<EC2 IP>`** 로 실행합니다.

#### 측정 규칙 — 노이즈와 개선을 구분

1. 같은 조건으로 **3회 반복** → 중앙값과 최대-최소 폭 기록
2. 그 폭이 **측정 노이즈 범위**입니다. 개선폭이 이보다 작으면 개선이라 부르지 않습니다
3. 튜닝 후 다시 3회 → 노이즈 범위를 벗어났는지로 판정
4. 매번 동일 조건: 같은 THREADS/DURATION, 같은 시간대, 같은 캐시 상태

#### 측정 항목

| # | 지표 | 측정 시점 | 기대 서술 |
| --- | --- | --- | --- |
| 1 | **RPS / p95 / 에러율** | 튜닝 전(D6) → 후(D8) | 동시 N명에서 5xx·OOM 재시작 → 튜닝 후 5xx 0건, p95 개선 |
| 2 | **OOM 임계점** | 부하를 올리며 관찰 | 동시 N명부터 컨테이너 재시작 → M명까지 안정 |
| 3 | **Docker 이미지 크기** | 최적화 전후(D3) | 3개 합계 X MB → Y MB (Z%↓) |
| 4 | **빌드 시간** | 최적화 전후(D3) | 레이어 캐싱 효과 |
| 5 | **RDS 연결 고갈점** | 1번 부하 중 `pg_stat_activity` | 동시 N에서 대기 → 풀 조정 후 해소 |
| 6 | **강의계획서 캐시 히트율** | §4.3 A 배치 전후 | 캐시 미스 최대 20초 → 히트 시 N ms, 히트율 M% |

> 💡 3·4번은 최적화 당일 `docker images` 출력을 before/after로 남기면 끝입니다.
> 💡 5번은 1번 부하 중에 `SELECT count(*) FROM pg_stat_activity;` 를 주기적으로 찍으면 됩니다.

`docs/performance.md` 구성:

```markdown
## 측정 환경
EC2 t3.micro / RDS db.t4g.micro / 부하 생성: 민지 PC
JMeter 5.5, seoganpyo-smoke.jmx, THREADS=N RAMPUP=N DURATION=N

## 측정 노이즈 범위 (3회 반복)
| 지표 | 1회 | 2회 | 3회 | 중앙값 | 폭 |

## RAM 튜닝 전후
| 지표 | 튜닝 전 | 튜닝 후 | 변화 | 노이즈 범위 초과? |

## Docker 이미지
| 이미지 | before | after | 감소율 |
```

---

## 3. 데이터 전략 (기존 데이터 복구 불가) — 🟩 민지

### 3.1 스키마 재생성

`Base.metadata.create_all()`로 테이블은 자동 생성됩니다. `scripts/migrations/`의 SQL 6개는 **기존 데이터 보정용**이라 신규 DB에는 대부분 불필요합니다.

| 파일 | 신규 DB 적용 여부 |
| --- | --- |
| `001_add_professor_department.sql` | 모델에 이미 있으면 불필요 |
| `002_resync_professors_sequence.sql` | 불필요 (빈 테이블) |
| `003_normalize_course_category.sql` | 불필요 (import 시 이미 '전공'/'교양') |
| `004_widen_professor_name.sql` | **모델 정의 확인 후, 필요하면 모델에 반영** |
| `005_move_multi_prof_to_liberal.sql` | import 로직에 반영돼 있으면 불필요 |
| `006_recompute_is_retake.sql` | 불필요 (수강이력 없음) |

→ 각 마이그레이션이 모델에 반영됐는지 검증하고, 아니면 모델을 고쳐서 **마이그레이션 없이도 올바른 스키마**가 되게 합니다.

### 3.2 데이터 재수집 — ⚠️ 블로커

| 데이터 | 복구 경로 | 상태 |
| --- | --- | --- |
| 교수 (`professors`) | `crawl_service.crawl_and_upsert()` — `cs.sogang.ac.kr` 크롤링 | ✅ 가능 |
| 교수 AI 요약 | Ollama — 민지 PC에서 배치 | ⚠️ §4.3 |
| 강의 (`courses`) | `scripts/import_courses.py` — **엑셀 파일 필요** | ❌ **레포에 없음** |
| 강의계획서 PDF | `data/syllabi/` — 비어 있음 | ❌ 원본 없음 |
| 사용자·장바구니·수강이력·게시글 | 재수집 불가 | 신규 시작 |

> 🔴 **강의 데이터가 최대 리스크입니다.** `import_courses.py`는 `<YEAR>-{1|2|동계|하계}.xls(x)`를 읽는데 레포에 없습니다. **착수 전에 하연·민지 로컬에 개설과목 엑셀이 있는지 확인**하세요. 없으면 수강신청 사이트에서 다시 받고, 그것도 안 되면 `scripts/seed_demo_data.py`(강의 200건 + 교수 30명, 실제 CSE 과목명 기반)를 새로 작성합니다(+2~3일).

### 3.3 로컬 → RDS 적재 흐름

```bash
# 0) SSH 터널 (별도 터미널) — §2.3
ssh -L 5432:<rds-endpoint>:5432 ec2-user@<ec2-ip>

# 1) 스키마 생성
DB_HOST=localhost python -c "from app.main import app"
# 2) 교수 크롤링
DB_HOST=localhost PYTHONPATH=. python -c "..."
# 3) 강의 적재
DB_HOST=localhost PYTHONPATH=. python scripts/import_courses.py
# 4) e2e 테스트 계정
DB_HOST=localhost PYTHONPATH=. python scripts/e2e_seed_user.py
```

**RDS 연결 풀**: `pool_pre_ping=True`, `db.t4g.micro`의 `max_connections`(약 80)를 확인한 뒤 `pool_size`·`max_overflow` 설정 → §2.8 5번에서 검증.

---

## 4. Ollama 경로 정비 — 🟩 민지

### 4.1 현황 — Ollama 통일은 의도된 설계

| 날짜 | 커밋 | 내용 |
| --- | --- | --- |
| 2026-04-14 | `a3d1d9c` | Groq **제거**, Claude Agent SDK로 일원화 |
| 2026-04-30 | `666939b` | Claude API → **Ollama 전환** (`exaone3.5:7.8b`) — 교수 요약과 모델 통일 |

> ⚠️ CLAUDE.md의 "Groq — 강의계획서 PDF 분석"은 **낡은 정보**입니다. Groq로 되돌리지 않고 CLAUDE.md를 정정합니다(§6).

### 4.2 남는 문제 — 사용자 경로의 동기 의존

| 호출처 | 경로 | 인증 | 성격 |
| --- | --- | --- | --- |
| `crawl_service._summarize_research_area` | `admin.py` 요약 재생성 | 관리자 | 배치 |
| `syllabus_service.summarize_with_ollama` | `admin.py` 배치 (`process_pdf_for_batch`) | 관리자 | 배치 |
| 동일 | **`POST /api/v1/syllabus/summarize`** (`syllabus.py`) | **없음** | **사용자 동기** |

현재 `httpx.Client(timeout=300)` — 5분 타임아웃입니다. 다행히 `process_syllabus`는 **`pdf_hash` 캐시를 먼저 조회**하므로, Ollama 호출은 **미등록 PDF 업로드 시에만** 발생합니다.

### 4.3 대응 — 캐시 선행 + 우아한 실패

**(A) 관리자 배치로 사전 요약** *(필수)* — 시연 전에 민지 PC에서 전체 강의계획서를 요약해 RDS에 채웁니다.
```bash
DB_HOST=localhost PYTHONPATH=. python scripts/summarize_syllabi.py   # SSH 터널 경유
```

**(B) 타임아웃 축소 + 명확한 실패** *(필수, 브랜치 `refactor/ollama-url-env`)*
```python
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434/api/generate")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))  # AWS: 20
```
- `crawl_service.py:13`, `syllabus_service.py:14` 두 곳의 하드코딩을 환경변수로
- AWS에선 `OLLAMA_TIMEOUT=20` + 실패 시 **503 "요약 준비 중입니다"** — 시연 중 500 화면 방지

**(C) Cloudflare Tunnel로 PC Ollama 연결** *(선택)* — `OLLAMA_URL`만 터널 주소로 바꾸면 되고 코드 변경은 없습니다. 단 PC 가동이 기능 가용성이 되므로, (A)+(B)가 있으면 없어도 됩니다.

**(D) 관리자 요약 엔드포인트** — AWS에서는 Ollama가 없어 실패합니다. 기본안: **503 + "로컬 실행 필요"** 반환 + 프론트 안내. (C)를 붙이면 그대로 동작.

> 모델 자체는 AWS에 올리지 않습니다 — 1GB에 7.8B 모델은 불가능합니다.

---

## 5. S3 이미지 저장소 전환 — 🟩 민지 (코드) / 🟦 하연 (IAM 검토) (2차)

### 5.1 현황 — 로컬 파일시스템 저장, EC2 재생성 시 소실

| 위치 | 경로 |
| --- | --- |
| `app/api/upload.py` | `static/uploads` (시간표 이미지) |
| `app/api/posts.py` | `static/uploads/posts` (게시글 이미지) — DB에 `/static/uploads/posts/{name}` 상대경로 저장 |
| `app/api/upload_paddle_legacy.py` | `static/uploads` (레거시 → §6에서 삭제) |
| `app/services/syllabus_service.py` | `data/syllabi/*.pdf` |

### 5.2 작업

1. `app/services/storage_service.py` 신규 — `save_upload(file_obj, key) -> str`(공개 URL), `STORAGE_BACKEND=s3|local`로 분기 (로컬 개발은 local)
2. `boto3` → `requirements.txt` 추가
3. EC2 인스턴스 역할에 해당 버킷의 `s3:PutObject`/`s3:GetObject`만 부여 — **`s3:*` 금지** (🟦 하연 검토)
4. 버킷은 **퍼블릭 차단 유지** + CloudFront OAC로 배포
5. 신규 DB라 기존 상대경로 데이터 마이그레이션 불필요

---

## 6. 코드 정리 — 학교 서버 잔재 제거 — 🟩 민지

브랜치 `chore/remove-school-server-refs` (1차 가장 먼저).

| 파일 | 내용 | 조치 |
| --- | --- | --- |
| `docker-compose.yml` | `DEFECTDOJO_URL` 기본값 `163.239.77.65` | 기본값 제거 |
| `app/api/admin_security.py` | 같은 IP 하드코딩 | 기본값 제거 + 미설정 시 기능 비활성 |
| `frontend/src/app/admin/security/page.tsx` | 안내문에 IP 노출 | 문구 수정 |
| `infra/observability/prometheus/prometheus.prod.yml` | `163.239.77.77:8080` | 파일 폐기 (Grafana Cloud 전환) |
| `infra/observability/promtail/promtail-config.prod.yml` | `163.239.77.66:3100` | Alloy 설정으로 교체 |
| `docker-compose.observability.server.yml` | 학교 모니터링 서버 전용 | **JMeter/InfluxDB를 `docker-compose.loadtest.yml`로 분리한 뒤** 삭제 |
| `docker-compose.observability.app.yml` | Promtail overlay | Alloy로 교체 |
| `Makefile` | `obs-server-*` 타깃 | 삭제 — **`jmeter-*`는 유지** |
| `.github/workflows/loki-llm-digest.yml` | 학교 Loki IP | ✅ 트리거 비활성화됨 — Grafana Cloud URL로 교체하거나 유지 |
| `docker-compose.dev.yml` 주석 | "DB: 팀 공용 서버" | 문구 갱신 |
| `Dockerfile` docker-cli 스테이지 | prod에서 docker.sock 미마운트 = 쓸모 없음 | 제거 → 이미지 축소 (단 `admin_assistant` 컨테이너 조회 기능 영향 확인) |
| `upload_paddle_legacy.py`, `image_service_paddle_legacy.py` | 레거시 | 미사용 확인 후 삭제 |
| `CLAUDE.md` AI 스택 | "Groq" 기재 | Ollama로 정정 (§4.1) |
| `crawl_service.py:13`, `syllabus_service.py:14` | `host.docker.internal:11434` 하드코딩 | `OLLAMA_URL` 환경변수화 (§4.3 B, 별도 브랜치) |

> 원본 레포가 보존되므로(§13) **과감하게 삭제해도 안전합니다.**

---

## 7. 레지스트리 · CI/CD

### 7.1 파이프라인 (2차) — 🟦 하연

```
git push (dev/main)
   ├─ ci.yml           : pytest + lint     (재활성화 검토 — §13.1)
   ├─ security-scan.yml: Trivy             (재활성화 검토)
   └─ deploy.yml       : 신규
        ① OIDC로 AWS 인증 (장기 액세스 키 없음)
        ② docker buildx build → ECR push (backend / frontend / ocr)
        ③ SSM Run Command로 EC2에서 `docker compose pull && up -d`
```

**포트폴리오 어필 지점 2개**:
- **GitHub OIDC + IAM 역할** — 레포에 AWS 키를 두지 않음. 신뢰 정책의 `sub` 조건은 `repo:kuchipachi/seoganpyo:ref:refs/heads/main` 형태로 브랜치까지 좁힘
- **SSM Run Command 배포** — SSH 키 없이 배포 → 보안그룹에서 22번 닫기

### 7.2 ECR (1차로 앞당김) — 🟦 하연 (리포지토리·IAM) / 🟩 민지 (이미지 push)

1차 첫 배포부터 이미지를 옮길 경로가 필요해서 **ECR 생성을 1차로 앞당겼습니다.** 1차는 민지 Mac에서 `buildx --platform linux/amd64` push, 2차부터 Actions가 대신합니다.

- 리포지토리 3개: `seoganpyo-api`, `seoganpyo-frontend`, `seoganpyo-ocr`
- EC2 인스턴스 역할: `AmazonEC2ContainerRegistryReadOnly` (pull만)
- 민지 IAM 사용자: 해당 3개 리포지토리 push 권한만
- 수명주기 정책 — 리포지토리당 최근 3개만 보존 (저장 $0.10/GB·월):
  ```json
  { "rules": [ { "rulePriority": 1,
      "selection": { "tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 3 },
      "action": { "type": "expire" } } ] }
  ```

> 💡 롤백(§2.7)은 "보존된 이전 태그로 되돌리기"라서, 보존 개수를 1로 줄이면 롤백이 불가능합니다.

### 7.3 프론트엔드 빌드 타임 환경변수 주의

`frontend/Dockerfile`은 `NEXT_PUBLIC_API_URL`을 **빌드 인자**로 받습니다 → 도메인이 바뀌면 **재빌드**해야 합니다.

```bash
--build-arg NEXT_PUBLIC_API_URL=https://<ec2-ip>.nip.io/backend
--build-arg NEXT_PUBLIC_GRAFANA_URL=https://<계정>.grafana.net
```

도메인은 🟦 하연이 D3에 확정 → 🟩 민지가 빌드.

---

## 8. 관측 — 1차 포함

> 목표 직무가 **"클라우드 모니터링·장애 대응"** 을 명시하므로 1차에 넣습니다. 2차로 미루면 일정이 밀릴 때 가장 먼저 잘립니다.

### 8.1 Grafana 부재 대응 — 🟩 민지 (1차, 관측 구성 전까지)

| # | 위치 | 증상 | 조치 |
| --- | --- | --- | --- |
| 1 | `admin/monitoring/page.tsx` iframe | 900px 회색 빈 박스 | `NEXT_PUBLIC_GRAFANA_URL` 미설정 시 섹션 숨김 |
| 2 | `admin_assistant.py` `query_prometheus` | 관리자 챗 LLM 도구 → **connection refused** | `PROMETHEUS_URL` 미설정 시 도구 등록 제외 |

> 🔴 2번은 **눈에 안 보이는 의존**입니다 — 관리자가 챗에서 메트릭을 물을 때만 터집니다.
> `DASHBOARDS`의 `jmeter-loadtest` 탭은 유지합니다(§2.8). Grafana Cloud로 옮기면 InfluxDB 데이터소스를 새로 연결해야 합니다.

### 8.2 Grafana Cloud 구성 — 🟩 민지 (1차)

| 항목 | 무료 한도 |
| --- | --- |
| 로그(Loki) | 50GB/월, 14일 보관 |
| 메트릭(Prometheus) | 10k 시리즈 |
| 사용자 | 3명 |

**CloudWatch 대신 Grafana Cloud인 이유**: `/metrics`가 Prometheus 형식이라 CloudWatch Agent에 scrape 설정을 따로 붙여야 하고(작업량 비슷), 기존 대시보드 JSON 2개를 버려야 합니다.

1. Grafana Cloud 계정 → **Grafana Alloy** 사용 (Promtail은 2025년 EOL, 후속이 Alloy)
2. EC2에 Alloy 컨테이너 추가(~100MB) — Docker 로그 + `backend:8000/metrics` → remote write
   - ⚠️ **RAM 튜닝(§2.2) 이후**에 붙이고 여유를 실측하세요
3. `infra/observability/grafana/provisioning/dashboards/json/*.json` 2개 임포트
   - ⚠️ datasource `uid`가 `loki`/`prometheus`로 고정 → **Cloud의 실제 uid로 교체**
4. §8.1-1에서 숨긴 iframe 복구 + `NEXT_PUBLIC_GRAFANA_URL` 주입
   - ⚠️ Grafana Cloud는 익명 iframe 임베드가 안 됨 → **Public dashboard** URL 사용
   - ⚠️ 빌드 타임 변수라 프론트 재빌드 필요(§7.3)
5. (2차) §8.1-2의 `query_prometheus`를 Cloud Prometheus + **토큰 인증**으로 전환

### 8.3 알람 — 장애 대응의 실체

공고의 "장애 대응"은 **알림이 오고 → 확인하고 → 기록하는** 사이클입니다.

| 구분 | 담당 | 내용 |
| --- | --- | --- |
| Grafana Alerting 룰 | 🟩 민지 | 5xx 급증, p95 응답시간, 컨테이너 재시작 |
| CloudWatch 알람 | 🟦 하연 | EC2 상태 검사 실패, CPU, RDS 연결 수·여유 스토리지 |
| **Discord 연동** | 🟦 하연 | 기존 `DISCORD_SIGNUP_WEBHOOK`과 **별도 채널** |

> 💡 Prometheus 라벨은 `status="2xx"/"4xx"/"5xx"`(숫자 아님) — 쿼리 시 주의.
> 💡 EC2 **메모리** 지표는 CloudWatch 기본 지표에 없습니다(Agent 필요). 메모리는 Alloy → Grafana 쪽에서 봅니다.

### 8.4 포스트모템 — 겪은 사람이 씁니다

한 사람이 몰아 쓰지 않습니다. 그래야 원인 분석이 정확하고, **둘 다 "장애 대응 경험"을 자기 것으로 말할 수 있습니다.**

- `docs/postmortems/YYYY-MM-DD-<증상>.md` — `/postmortem` 스킬 활용
- 형식: 증상 / 타임라인 / 원인 / 조치 / 재발 방지
- **각자 2건 이상, 팀 합계 4건+**

| 담당 | 예상 트러블 |
| --- | --- |
| 🟦 하연 | EC2 OOM·swap, 보안그룹 오설정으로 접속 불가, OIDC 신뢰 정책 거부, SSM 배포 실패 |
| 🟩 민지 | arm64 이미지 exec format error, 컨테이너 메모리 예약 충돌, RDS 연결 고갈, Alloy datasource uid 불일치 |
| 🟪 공통 | 부하 테스트 중 5xx 급증, 배포 후 헬스체크 실패 |

> 💡 §2.8과 짝입니다 — 부하를 걸다 터진 OOM은 수치(§2.8)와 포스트모템(§8.4) 양쪽에 남습니다.

---

## 9. 리스크

| # | 리스크 | 심각도 | 대응 | 담당 |
| --- | --- | --- | --- | --- |
| 1 | **강의 엑셀 원본 없음** | 🔴 | 착수 전 확인 → 없으면 더미 시드 (§3.2) | 🟩 민지 |
| 2 | **t3.micro 1GB OOM** | 🔴 | swap + 외부 빌드 + 메모리 제한 (§2.2) | 🟪 페어 |
| 3 | **크레딧 소진 / 6개월 후 계정 폐쇄** | 🔴 | $200 활동 채우기 + RDS 중지 + 만료 1개월 전 결정 (§2.1, §2.6) | 🟦 하연 |
| 4 | ALB/NAT/Multi-AZ 실수 생성 | 🔴 | Budgets 알람 + **보강된** Deny 정책 (§2.1) | 🟦 하연 |
| 5 | Apple Silicon에서 빌드한 arm64 이미지 | 🟡 | `buildx --platform linux/amd64` (§2.2) | 🟩 민지 |
| 6 | 사용자 경로의 Ollama 동기 의존 | 🟡 | 배치 사전 요약 + 타임아웃 20초 + 503 (§4.3) | 🟩 민지 |
| 7 | `query_prometheus` 숨은 의존 | 🟡 | 관측 구성 전까지 조건부 등록 (§8.1) | 🟩 민지 |
| 8 | 복원 훈련용 RDS 방치 | 🟡 | 검증 직후 삭제 (§2.5) | 🟩 민지 |
| 9 | Alloy 추가로 RAM 재압박 | 🟡 | RAM 튜닝 이후 실측하고 붙임 (§8.2) | 🟩 민지 |
| 10 | 부하 생성기를 EC2에서 실행 | 🟡 | 민지 PC에서 `BASE_HOST=<EC2 IP>` (§2.8) | 🟩 민지 |
| 11 | 1차 `.env`가 EC2 평문 파일 | 🟡 | `chmod 600`, 2차에 SSM 이관 (§2.4) | 🟦 하연 |
| 12 | Grafana Cloud iframe 제약 | 🟢 | Public dashboard + 재빌드 (§8.2) | 🟩 민지 |
| 13 | RDS 20GB 초과 | 🟢 | 데이터 규모 미미 | — |
| 14 | SMTP(Gmail) 차단 | 🟢 | 앱 비밀번호 + 587 포트 → 그대로 동작 | — |

> 💡 업로드 이미지 소실은 리스크가 아니라 §0 전제입니다 — 1차엔 감수하고, 2차에 S3로 옮깁니다.

---

## 10. 착수 전 체크리스트

- [ ] **강의 개설과목 엑셀이 하연·민지 로컬에 있는지 확인** ← 최우선 (§3.2) — 🟪
- [x] AWS 계정 생성 · Budgets 알람 — 🟦
- [x] 레포 분리 `kuchipachi/seoganpyo` — 🟩
- [x] 하연을 `kuchipachi` org Owner로 초대 — 🟩
- [ ] Deny 정책 Multi-AZ 조건 보강 (§2.1) — 🟦
- [ ] 도메인 결정 (기본: `nip.io`) — 🟦
- [ ] 강의계획서 배치 사전 요약 계획 확정 (§4.3 A) — 🟩
- [ ] Cloudflare Tunnel 사용 여부 (§4.3 C) — 🟪
- [ ] `upload_paddle_legacy.py` / `image_service_paddle_legacy.py` 미사용 확인 — 🟩
- [ ] `admin_assistant`의 docker 기능이 prod에 필요한지 확인 (§6 Dockerfile) — 🟩
- [ ] 1차/2차 분할과 §12 역할 분담 합의 — 🟪
- [ ] Grafana Cloud 계정 — 🟩
- [ ] Discord 알림용 **별도 채널** + 웹훅 — 🟦
- [ ] `docs/postmortems/` 디렉터리 생성 — 🟦
- [ ] 태깅 정책 합의 `Project/Env/Owner` — 🟪
- [ ] JMeter 실행 환경 확인 (민지 PC Docker) — 🟩
- [ ] `docs/performance.md` 템플릿 생성 — 🟩
- [ ] 부하 테스트 파라미터 고정값 합의 (THREADS/RAMPUP/DURATION) — 🟪

---

## 11. 브랜치 / PR 계획

모든 PR은 **`kuchipachi/seoganpyo`의 `dev`** 가 타깃입니다.

### 1차

| 브랜치 | 범위 | 담당 | 선후관계 |
| --- | --- | --- | --- |
| `chore/disable-legacy-workflows` | 워크플로 7개 자동 트리거 비활성화 | 🟩 민지 | ✅ PR #1 머지 |
| `chore/remove-school-server-refs` | §6 IP 제거·레거시 삭제·CLAUDE.md 정정 | 🟩 민지 | **가장 먼저** |
| `refactor/ollama-url-env` | §4.3 B — 환경변수화 + 503 | 🟩 민지 | 독립 |
| `fix/monitoring-page-no-grafana` | §8.1 — iframe 조건부 + `query_prometheus` | 🟩 민지 | 독립 |
| `chore/slim-docker-images` | §2.2, §6 — docker-cli 스테이지 제거·이미지 축소 | 🟩 민지 | `remove-...` 이후 |
| `chore/loadtest-compose` | §2.8 — JMeter/InfluxDB 분리 | 🟩 민지 | ✅ `remove-...` 이전에 완료 |
| `refactor/professor-summary-cli` | §4.3 D — 관리자 요약 엔드포인트 503 | 🟩 민지 | `remove-...` 이후 |
| `feat/aws-deploy` | Compose prod 설정·Caddyfile·메모리 제한 | 🟪 페어 | 위 항목 이후 |
| `feat/grafana-cloud-alloy` | §8.2 — Alloy + 대시보드 | 🟩 민지 | `feat/aws-deploy` 이후 |
| `feat/alerting-rules` | §8.3 — 알람 룰 정의 | 🟪 페어 | 위 이후 |

### 2차

| 브랜치 | 범위 | 담당 | 선후관계 |
| --- | --- | --- | --- |
| `ci/aws-oidc-deploy` | §7.1 — OIDC + SSM Run Command + `deploy.yml` | 🟦 하연 | `feat/aws-deploy` 이후 |
| `feat/storage-s3` | §5 — 스토리지 추상화 | 🟩 민지 | 독립 |
| `docs/runbook-ops` | §2.5~2.8 — 런북·비용·백업·성능 | 🟪 페어 | 2차 말 |
| `docs/cloud-migration` | 이 문서·README 갱신 + 포스트모템 + 아키텍처 결정 기록 | 🟪 페어 | **마지막** |

> 💡 AWS 콘솔 작업(VPC·RDS·EC2 생성)은 코드 변경이 없어 브랜치가 없습니다. 대신 하연의 **아키텍처 결정 기록**(§12)을 `docs/cloud-migration` PR에 함께 넣습니다.

---

## 12. 역할 분담

### 원칙

**레이어로 나눕니다** — 하연은 AWS 계정 안쪽(네트워크·IAM·배포 자동화), 민지는 컨테이너 안쪽(앱·이미지·관측). 이렇게 자르면 접점이 6개로 줄고(아래 표), AWS 콘솔을 동시에 만지는 충돌이 없습니다. 대신 **민지도 AWS를 피하지 않도록** ECR push, SSH 터널, S3 IAM 정책, RDS 복원 훈련을 민지 몫으로 넣었습니다.

> ⚠️ **일반적인 AWS 권장 구성이 여기서는 반대로 작동합니다.** Multi-AZ RDS / ALB / 프라이빗 서브넷+NAT는 보통 모범 구성이지만, 이 셋이 정확히 "크레딧 급소진" 목록입니다. 이 프로젝트는 **베스트 프랙티스를 의도적으로 위반하고 그 근거를 설명할 수 있는** 작업입니다.

### 목표 직무 대조 (Public Cloud 인프라 구축·운영)

| 공고 요구 | 담당 | 계획 |
| --- | --- | --- |
| Public Cloud 인프라·아키텍처 구축·운영 | 🟦 하연 | §2 |
| 클라우드 보안·권한 관리 | 🟦 하연 | IAM 최소권한·Deny 가드레일·OIDC·SSM·RDS 격리 |
| 운영 자동화 | 🟦 하연 (+🟩 RDS 자동 중지) | §7, §2.5 |
| 클라우드 모니터링 | 🟩 민지 | §8.2 |
| 장애 대응 | 🟦 하연 (CloudWatch·Discord) / 🟩 민지 (Grafana 알람·확인 절차) / 🟪 각자 포스트모템 | §8.3~8.4 |
| 고객 기술지원 | — | 프로젝트로 불가 — 아키텍처 결정 기록으로 일부 대체 |

### 🟦 하연 — 클라우드 인프라 · 보안 · 운영 자동화

| 차수 | 담당 | 배우는 것 |
| --- | --- | --- |
| 1차 | ✅ AWS 계정·Budgets·IAM·VPC·Deny 정책 | 네트워크 설계, 비용 방어 |
| 1차 | SG·서브넷 그룹·태깅 → RDS 생성 | 격리된 DB 접근 설계 |
| 1차 | EC2 + swap + Caddy | ALB 없이 HTTPS |
| 1차 | ECR 리포지토리 + 인스턴스 역할 | 최소 권한 pull 구조 |
| 1차 | RAM 튜닝 (인스턴스·커널 레벨) + 포스트모템 2건+ | 장애 대응·기록 |
| 1차 | CloudWatch 알람 + Discord 연동 | 알림 체계 |
| 2차 | SSM Parameter Store | Secrets Manager 대안 |
| 2차 | **GitHub OIDC + IAM 신뢰 정책** | **최난도 — 키 없는 인증** |
| 2차 | SSM Run Command 배포 | SSH 없는 배포 |
| 2차 | 비용 분석 | Cost Explorer, 만료 후 예상액 |
| 2차 | 런북 — 배포·롤백 | 운영 문서화 |

**추가 과제 — 아키텍처 결정 기록** (1차 여유 시간에 작성):

| 항목 | 일반 권장안 | 이 프로젝트 | 근거 |
| --- | --- | --- | --- |
| 로드밸런싱 | ALB | Caddy on EC2 | ALB ~$16/월, 인스턴스 1대로 충분 |
| DB 가용성 | Multi-AZ | Single-AZ | 비용 2배, 포트폴리오 서비스라 RPO/RTO 허용 |
| 네트워크 | Private subnet + NAT | Public subnet + SG 격리 | NAT ~$32/월 |
| 시크릿 | Secrets Manager | SSM Parameter Store | $0.4/시크릿 vs 무료 |
| 관측 | 자체 호스팅 | Grafana Cloud (SaaS) | 1GB RAM에 Prometheus+Loki 불가 |
| 레지스트리 | — | ECR + 수명주기 3개 | 롤백 가능 + 저장 비용 억제 |

**이력서 항목 예시**:
- 온프렘 → AWS 마이그레이션 설계 및 수행 (VPC·EC2·RDS·ECR·IAM)
- IAM 최소 권한·비용 Deny 가드레일·OIDC 키리스 인증·SSM 시크릿 기반 보안 구성
- GitHub Actions → ECR → SSM Run Command 무SSH 배포 자동화 + 태그 기반 롤백
- CloudWatch·Discord 알림 체계 구축, 장애 포스트모템 작성
- 비용 제약 하 아키텍처 트레이드오프 문서화 (월 ~$48 회피)

### 🟩 민지 — 앱 레이어 · 컨테이너 · 관측

클라우드는 처음이지만 **AWS 콘솔을 피하지 않습니다.** 백엔드 지식이 바로 쓰이는 클라우드 영역을 맡습니다.

| 차수 | 담당 | 배우는 것 |
| --- | --- | --- |
| 1차 | ✅ 레포 분리 + 워크플로 비활성화 | GitHub org·브랜치 운영 |
| 1차 | 학교 서버 잔재 제거 | — (준비 작업) |
| 1차 | Ollama 경로 정비 + Grafana 부재 대응 | 외부 의존 격리, 숨은 의존 추적 |
| 1차 | Docker 이미지 최적화 + **amd64 빌드 → ECR push** | 멀티스테이지·레이어 캐싱·멀티아키텍처 |
| 1차 | 데이터 적재 + **SSH 터널** + **RDS 연결 풀** | 네트워크 격리, 관리형 DB |
| 1차 | **베이스라인 측정 + RAM 튜닝** (컨테이너·앱 레벨) | 부하 테스트·성능 수치화 |
| 1차 | 포스트모템 2건+ | 장애 기록 |
| 1차 | **Grafana Cloud 관측** + Grafana 알람 룰 | Alloy, PromQL/LogQL, remote write |
| 2차 | **S3 전환 + 최소 권한 IAM 정책 작성** | `s3:*` 금지 — 정책 직접 작성 |
| 2차 | **RDS 백업·복구 훈련** | 백업 기본기 |
| 2차 | 관측 토큰 인증 + 런북 — 장애·접속 | 운영 문서화 |
| 2차 (선택) | RDS 자동 중지 — EventBridge + Lambda | 서버리스 운영 자동화 |

**이력서 항목 예시**:
- Grafana Cloud 기반 로그·메트릭 관측 파이프라인 구축 (Alloy, PromQL, LogQL)
- JMeter 부하 테스트로 병목 규명 — 동시 N명 OOM → 튜닝 후 5xx 0건
- Docker 이미지 최적화 — 3개 합계 X MB → Y MB, amd64 멀티아키텍처 빌드·ECR 배포
- RDS 연결 풀 설계, SSH 터널 기반 격리 DB 접근, 백업·복구 절차 검증
- S3 스토리지 추상화 + 최소 권한 IAM 정책 적용

### 🟪 페어 — RAM 튜닝 (1차, 2.5일)

가장 어렵고 가장 배울 게 많은 구간입니다. 성격이 정확히 반씩 나뉩니다:
- 🟦 **하연**: 인스턴스 레벨 — swap 동작, `vm.swappiness` 등 커널 파라미터, `dmesg` OOM Killer 추적
- 🟩 **민지**: 컨테이너 레벨 — 메모리 예약·제한, 이미지 크기, Node/Python 메모리, **JMeter 측정**
- 각자 겪은 트러블은 **각자** 포스트모템으로

> OOM은 배포 몇 시간 뒤에 터지기도 합니다. 혼자 하면 자기 절반만 보고 헤맵니다.

### 접점 — 여기서만 상대를 기다립니다

| # | 접점 | 순서 |
| --- | --- | --- |
| 1 | **RDS 엔드포인트** | 🟦 생성 → 🟩 데이터 적재 (**직렬**) |
| 2 | **EC2 접속** | 🟦 EC2·SSH 키 → 🟩 SSH 터널 (**직렬**) |
| 3 | ECR | 🟦 리포지토리·push 권한 → 🟩 이미지 push |
| 4 | 도메인 (`NEXT_PUBLIC_API_URL`) | 🟦 결정 → 🟩 프론트 빌드 |
| 5 | `.env` 스펙 | 🟩 키 목록 → 🟦 SSM 등록 |
| 6 | S3 IAM | 🟩 정책 초안 → 🟦 검토·적용 |

---

## 13. 레포 분리 — 🟩 민지 ✅ 완료 (2026-09-23)

### 왜 분리했나

마이그레이션은 4명 중 2명(하연·민지)만 진행합니다. 나머지 2명을 위해 원본 `gibunijjaejo/Opensource_Project`는 그대로 두고, **fork가 아닌 독립 복사본**에서 작업합니다(fork하면 원본에 포크 목록이 남음).

### 결과

| 항목 | 값 |
| --- | --- |
| 새 레포 | **https://github.com/kuchipachi/seoganpyo** (Public, fork 아님) |
| 복사 범위 | 원본의 `main`·`dev` + 태그 5개(v2.0.0 ~ v3.0.1), 전체 커밋 이력 — 해시 일치 확인 |
| 기본 브랜치 | `dev` |
| 원본 영향 | 없음 (원본 fork 수 작업 전후 4 → 4) |

사용한 명령:
```bash
gh repo create kuchipachi/seoganpyo --public
gh api -X PUT repos/kuchipachi/seoganpyo/actions/permissions -F enabled=false   # push 전에 Actions 차단
git clone --bare https://github.com/gibunijjaejo/Opensource_Project.git
git -C Opensource_Project.git push --mirror https://github.com/kuchipachi/seoganpyo.git
```

### 로컬 remote 교체 (하연도 동일하게)

```bash
git remote rename origin old-origin                         # 기존 fork 보존
git remote add origin https://github.com/kuchipachi/seoganpyo.git
git remote set-url --push upstream DISABLED                 # 원본에 실수로 push 방지
git fetch origin && git remote -v
```

### 13.1 워크플로 — ✅ 트리거 비활성화 (PR #1)

원본 org의 시크릿(SONAR_TOKEN, Discord 웹훅, 학교 Loki IP 등)이 없어 전부 실패하므로, 7개 워크플로의 자동 트리거를 주석 처리하고 `workflow_dispatch`(수동 실행)만 남겼습니다. 파일은 지우지 않았습니다.

| 파일 | 실패 원인 | 재활성화 시점 |
| --- | --- | --- |
| `ci.yml` | `sonar-scan` job에 SONAR_TOKEN 필요 (pytest는 동작 가능) | pytest 통과 확인 후 1차 중 — sonar job만 분리 |
| `sonarcloud.yml` | SONAR_TOKEN, `projectKey=gibunijjaejo_...` | 2차 — `sonar-project.properties` 새 org 기준 수정 |
| `security-scan.yml` | 권한·토큰 | 2차 |
| `discord-notify.yml` | 웹훅 시크릿 | 2차 (§8.3 채널과 통합 검토) |
| `issue-on-ci-failure.yml` | `ci.yml` 의존 | `ci.yml` 재활성화 후 |
| `loki-llm-digest.yml` | 학교 Loki IP | Grafana Cloud 전환 후 또는 폐기 |
| `todo-to-issue.yml` | 권한 | 필요 시 |

### 레포 세팅 — 🟩 민지

- [x] 하연(`noeyish`) org Owner 초대 + 새 remote URL 공유
- [x] Actions 다시 켜기 (트리거가 비활성화돼 있어 자동 실행 없음)
- [x] 브랜치 보호 — `main`/`dev` 직접 push 금지, PR 필수(승인 0명 — 2인 팀)
- [ ] (선택) 병합 끝난 기능 브랜치 정리 — 커밋 이력은 지우지 않음

### 13.2 이후 영향

| 섹션 | 영향 |
| --- | --- |
| §7.1 OIDC | 신뢰 정책 `sub` 조건이 `repo:kuchipachi/seoganpyo:*` 기준 |
| §11 브랜치 | 모든 PR 타깃이 새 레포의 `dev` |
| §6 코드 정리 | 원본이 보존되므로 과감하게 삭제해도 안전 |

---

## 부록 — 원안(2026-09-20) 대비 수정 사항

하연이 원안과 비교할 수 있도록 바뀐 점만 모았습니다.

| 항목 | 원안 | 수정 | 이유 |
| --- | --- | --- | --- |
| 1차 이미지 전달 | 없음 (ECR은 2차) | **ECR을 1차로 앞당김**, 🟦 하연 담당 + 민지 Mac에서 amd64 push | 첫 배포 때 이미지를 옮길 방법이 없었음 |
| 공수 | 하연·민지 합계가 표마다 다름(5.25/6.75/7.25/7.75) | 단계표 합산 기준으로 통일: 하연 10.75 / 민지 11.0 | 계산 불일치 + 누락 작업(Grafana 부재 대응, loadtest 분리) 반영 |
| 월 비용 | ~$28 | **~$34** (퍼블릭 IPv4 $3.6 추가, 합계 재계산) | 표 합계가 $30.6이었고 IPv4 요금 누락 |
| 크레딧 수명 | "RDS 중지로 7개월" | $120 기준 3.5~4.1개월, **$200 확보 시 6개월 기한 충족** | RDS만 멈춰도 EC2 등은 계속 과금 |
| Deny 정책 | "RDS 클러스터 차단" | `rds:MultiAz` 조건 + 인스턴스 클래스·타입 제한 | 클러스터 차단으로는 Multi-AZ가 막히지 않음 |
| 1차 `.env` | 언급 없음 | EC2 평문 + `chmod 600`, 2차 SSM | 1차 배포에 필요 |
| 첫 배포 | 메모리 예약 조정(D7) 전에 배포 | 조정 후 배포, 또는 OOM을 포스트모템 1호로 | 기존 예약 합계 1GB |
| 레포 | "워크플로 7개", `noeyish` origin, 브랜치 106개 | 실제: 원본 브랜치 2개·태그 5개, `kuchipachi/seoganpyo` | 실측 |
| 단계 번호 | 절마다 "7단계"/"8단계"가 어긋남 | 본문에서 단계 번호 대신 D·절 번호로 참조 | 상호 참조 오류 |
| 역할 원칙 | "레이어로 갈랐다" vs "난이도로 가른다" 모순 | **레이어로 나누고, 민지 몫에 AWS 작업을 명시** | 문구 모순 |
| 구 무료 티어 표현 | "무료 티어 대상 아님", "ECR 500MB 한도" 등 | 크레딧 모델 기준 표현으로 교체 | 이 계정에는 해당 없음 |
