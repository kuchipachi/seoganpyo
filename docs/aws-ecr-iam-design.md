# AWS ECR · IAM 설계 — 이미지 레지스트리와 권한 분리

> 컨테이너 이미지를 어떻게 옮기고, 누구에게 어떤 권한을 주는지에 대한 설계.
> 인프라(네트워크·EC2·RDS)는 [aws-infra-design.md](./aws-infra-design.md).
> 계획은 [cloud-migration-plan.md](./cloud-migration-plan.md).
> 작성: 2026-09-23 · 🟦 하연

---

## 0. 실제 구성값

| 항목 | 값 |
| --- | --- |
| 리전 | `ap-northeast-2` (서울) |
| 리포지토리 | `seoganpyo-api` · `seoganpyo-frontend` · `seoganpyo-ocr` |
| 레지스트리 URI | `<계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com` |
| EC2 역할 | `SeoganpyoEC2Role` (프로파일 `SeoganpyoEC2Profile`) |
| EC2 정책 | `AmazonEC2ContainerRegistryReadOnly` + `AmazonSSMManagedInstanceCore` |
| 민지 정책 | `SeoganpyoECRPush` (커스텀, 리포 3개 한정) |
| 비용 방어 | `SeoganpyoDenyCostly` (관리자 그룹) |

```
맥북(민지) ──push──> ECR ──pull──> EC2
  amd64 빌드          3 repos       SeoganpyoEC2Role
  SeoganpyoECRPush    수명주기 3개   (키 없음)
```

---

## 1. 왜 ECR이 필요한가

### 문제

```
맥북 (빌드)  ───?───>  EC2 (실행)
```

이미지를 옮길 방법이 없습니다.

| 방법 | 판단 |
| --- | --- |
| EC2에서 직접 빌드 | ❌ 1GiB RAM — `pnpm build`가 OOM ([infra §4](./aws-infra-design.md)) |
| `docker save` → `scp` | ❌ 이미지 3개 수백 MB, 매번 수동 |
| Docker Hub (public) | ❌ 코드·환경변수가 공개 |
| Docker Hub (private) | △ 무료 1개 리포만 |
| **ECR** | ✅ 같은 VPC·리전, IAM으로 권한 제어 |

### 원래 2차였는데 1차로 앞당긴 이유

계획서 원안은 ECR을 2차(CI/CD와 함께)에 뒀습니다. 그런데 **첫 배포 시점에 이미지를 옮길
수단이 없다**는 게 드러나 1차로 당겼습니다 (민지 지적, 계획서 부록).

```
1차: 맥북에서 수동 빌드 → push → EC2에서 pull
2차: GitHub Actions가 빌드 → push → SSM Run Command 로 배포  (§7)
```

1차의 수동 단계를 2차에 자동화하는 구조라, **같은 ECR을 그대로 씁니다.**

---

## 2. 리포지토리 설계

### 왜 3개로 나누나

`docker-compose.yml`의 빌드 대상이 3개입니다.

| 리포지토리 | 소스 | 베이스 |
| --- | --- | --- |
| `seoganpyo-api` | `Dockerfile` | `python:3.11-slim-bookworm` |
| `seoganpyo-frontend` | `frontend/Dockerfile` | `node:20-alpine` |
| `seoganpyo-ocr` | `ocr-service/Dockerfile` | — |

Git 레포와 달리 ECR은 **이미지 한 종류당 리포지토리 하나**가 원칙입니다. 하나에 몰아넣고
태그로 구분하면 수명주기 정책을 서비스별로 걸 수 없습니다.

> `redis`·`caddy`는 공식 이미지를 그대로 쓰므로 ECR에 올리지 않습니다.

### 수명주기 정책 — 최근 3개만

```json
{
  "rules": [{
    "rulePriority": 1,
    "description": "Keep only the 3 most recent images",
    "selection": { "tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 3 },
    "action": { "type": "expire" }
  }]
}
```

**이유** — 크레딧 모델에서 ECR은 **스토리지 GB당 과금**입니다. 배포할 때마다 태그가 쌓이면
조용히 새어 나갑니다. 이미지 3개 × 태그 누적이라 방치하면 수 GB가 됩니다.

3개를 남기는 건 **롤백 여지**를 위해서입니다 ([runbook 롤백 절차](./runbook.md)):
현재 + 직전 + 그 전. 그 이상은 실질적으로 안 씁니다.

### 스캔 — `scanOnPush`

```bash
--image-scanning-configuration scanOnPush=true
```

push할 때마다 **이미지 취약점을 자동 스캔**합니다. 기본 스캔은 무료입니다.

기존 CI에 Trivy(`security-scan.yml`)가 있었지만 §13.1에서 비활성화한 상태라, 그 공백을
일부 메웁니다. 2차에 CI를 되살리면 두 겹이 됩니다.

---

## 3. 권한 설계 — 읽기와 쓰기를 나눈다

이 절이 이 문서의 핵심입니다. **누가 무엇을 할 수 있는가**를 최소 권한으로 나눴습니다.

| 주체 | 권한 | 수단 | 왜 |
| --- | --- | --- | --- |
| **EC2** | `pull` 만 | 인스턴스 역할 | 서버는 받기만 하면 됨 |
| **민지** | `push`/`pull`, 리포 3개만 | IAM 사용자 정책 | 빌드·배포 담당 |
| **하연** | 관리자 | `AdministratorAccess` | 인프라 구성 |

### EC2 — 인스턴스 역할 (키 없는 인증)

```
SeoganpyoEC2Role
 ├─ AmazonEC2ContainerRegistryReadOnly   ← ECR pull
 └─ AmazonSSMManagedInstanceCore          ← 2차 SSM 배포 대비
        ↑
 SeoganpyoEC2Profile  (인스턴스 프로파일)
        ↑
 i-0cf5fbf562ec4017b
```

**EC2에 액세스 키를 두지 않습니다.** 인스턴스 메타데이터에서 임시 자격증명을 자동으로
발급받는 구조라, 키 파일 유출 위험이 없고 만료·갱신도 자동입니다.

확인:
```bash
aws sts get-caller-identity
# Arn: arn:aws:sts::<계정>:assumed-role/SeoganpyoEC2Role/i-0cf5fbf562ec4017b
```

> 💡 2차 GitHub OIDC(§7)도 **같은 원리**입니다 — 리포지토리에 AWS 키를 두지 않고
> 신뢰 관계로 임시 자격증명을 받습니다. 인스턴스 역할이 그 예습인 셈입니다.

**인스턴스 프로파일이 왜 따로 필요한가** — IAM 역할은 EC2에 직접 못 붙입니다.
프로파일이라는 껍데기에 역할을 담아 인스턴스에 연결하는 구조입니다. 콘솔에서는 자동으로
처리해 주지만 CLI에서는 두 단계로 나뉩니다.

| 제약 | 내용 |
| --- | --- |
| 프로파일당 역할 | **1개** (`LimitExceeded` 오류의 원인) |
| 전파 지연 | 생성 직후 `associate` 하면 실패 — 수십 초 대기 필요 |
| 메타데이터 반영 | 연결 후 EC2에서 인식까지 1~2분 |

### 민지 — 리포지토리 3개로 한정한 push 권한

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*" },
    { "Effect": "Allow",
      "Action": ["ecr:BatchCheckLayerAvailability","ecr:CompleteLayerUpload",
                 "ecr:InitiateLayerUpload","ecr:PutImage","ecr:UploadLayerPart",
                 "ecr:BatchGetImage","ecr:GetDownloadUrlForLayer"],
      "Resource": [
        "arn:aws:ecr:ap-northeast-2:<계정>:repository/seoganpyo-api",
        "arn:aws:ecr:ap-northeast-2:<계정>:repository/seoganpyo-frontend",
        "arn:aws:ecr:ap-northeast-2:<계정>:repository/seoganpyo-ocr"
      ]
    }
  ]
}
```

**`ecr:*` / `Resource: "*"` 를 쓰지 않은 이유**

| 방식 | 문제 |
| --- | --- |
| `AmazonEC2ContainerRegistryFullAccess` | 리포지토리 **삭제**까지 가능 |
| `Resource: "*"` | 앞으로 생길 모든 리포지토리에 적용 |
| **리포 3개 명시** | 필요한 범위만 ✅ |

`ecr:GetAuthorizationToken`만 `Resource: "*"`인데, 이건 **레지스트리 단위 API**라
리포지토리를 지정할 수 없습니다. 로그인 토큰 발급 권한이라 위험도가 낮습니다.

### 비용 방어 — `SeoganpyoDenyCostly`

관리자 그룹에 붙인 Deny 정책입니다. `AdministratorAccess`가 있어도 **Deny가 우선**합니다.

```json
{
  "Statement": [
    { "Sid": "DenyALBandNAT", "Effect": "Deny",
      "Action": ["elasticloadbalancing:CreateLoadBalancer", "ec2:CreateNatGateway"],
      "Resource": "*" }
  ]
}
```

> ⚠️ 민지 지적대로 **Multi-AZ는 클러스터가 아니라 `CreateDBInstance` 옵션**이라
> 초기 정책(`rds:CreateDBCluster` 차단)으로는 막히지 않았습니다.
> 다만 무료 플랜이 RDS 템플릿을 프리 티어로 고정해 Multi-AZ 선택 자체가 불가능하므로
> 실질적 위험은 없습니다. 조건부 Deny(`rds:MultiAz`) 보강은 선택 사항.

---

## 4. 이미지 빌드 · 배포 흐름

### 🔴 아키텍처 불일치 — 가장 흔한 실수

Apple Silicon 맥북은 기본이 **ARM64**, EC2 `t3.micro`는 **x86_64**입니다.
그냥 빌드해서 올리면 EC2에서 `exec format error`가 납니다.

```bash
docker buildx build --platform linux/amd64 ...
```

**반드시 `--platform linux/amd64`** 를 붙여야 합니다.

### 민지 — 빌드 & push

```bash
ACCT=<계정ID>
REG=${ACCT}.dkr.ecr.ap-northeast-2.amazonaws.com

aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin $REG

docker buildx build --platform linux/amd64 -t $REG/seoganpyo-api:latest . --push
docker buildx build --platform linux/amd64 -t $REG/seoganpyo-frontend:latest ./frontend --push
docker buildx build --platform linux/amd64 -t $REG/seoganpyo-ocr:latest ./ocr-service --push
```

> ⚠️ 프론트엔드는 `NEXT_PUBLIC_API_URL`이 **빌드 타임 변수**입니다 (계획서 §7.3).
> `--build-arg NEXT_PUBLIC_API_URL=https://54.180.181.46.nip.io/backend` 를 넘겨야 합니다.
> 도메인이 바뀌면 재빌드가 필요한 이유입니다.

### EC2 — pull & 실행

```bash
ACCT=$(aws sts get-caller-identity --query Account --output text)
REG=${ACCT}.dkr.ecr.ap-northeast-2.amazonaws.com

aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin $REG

docker compose pull && docker compose up -d
```

`docker-compose.yml`의 `build:` 를 `image: $REG/seoganpyo-api:latest` 형태로 바꿔야 합니다.
1차 배포 시 별도 compose 파일(`docker-compose.prod.yml`)로 분리하는 편이 낫습니다.

### 태그 전략

1차는 `latest` 단일 태그로 갑니다. 2차에 CI가 붙으면 커밋 SHA 태그를 병행합니다.

```
1차:  seoganpyo-api:latest
2차:  seoganpyo-api:latest + seoganpyo-api:<git-sha>   ← 롤백 지점
```

수명주기 정책이 3개만 남기므로, SHA 태그를 쓰면 롤백 가능한 버전이 3개 유지됩니다.

---

## 5. 겪은 문제

### EC2에서 `Unable to locate credentials`

**증상**
```
Unable to locate credentials. You can configure credentials by running "aws login".
Error: Cannot perform an interactive login from a non TTY device
```

**원인** — 인스턴스 역할을 연결하기 전에 `ecr get-login-password`를 실행. EC2에는
액세스 키가 없고 역할로만 권한을 받는데, 그게 없으니 자격증명을 못 찾음.

**조치** — `SeoganpyoEC2Role` + 프로파일 생성 → 인스턴스에 연결 → 1~2분 후 재시도.

### `InvalidParameterValue ... Invalid IAM Instance Profile name`

**원인** — 프로파일 생성 직후 바로 `associate`. **IAM 전파 지연**.

**조치** — 수십 초 대기 후 재시도. 또는 이름 대신 ARN 지정:
```bash
PROF_ARN=$(aws iam get-instance-profile --instance-profile-name SeoganpyoEC2Profile \
  --query 'InstanceProfile.Arn' --output text)
aws ec2 associate-iam-instance-profile --instance-id <id> --iam-instance-profile Arn=$PROF_ARN
```

### `LimitExceeded ... InstanceSessionsPerInstanceProfile: 1`

**원인** — 역할이 **이미 붙어 있는데** 다시 붙이려 함. 인스턴스 프로파일에는 역할을
1개만 담을 수 있음.

**판단** — 오류가 아니라 **이미 완료됨**을 뜻함. `EntityAlreadyExists`도 마찬가지.
상태 확인 후 다음 단계로 진행.

```bash
aws iam get-instance-profile --instance-profile-name SeoganpyoEC2Profile \
  --query 'InstanceProfile.Roles[].RoleName'
```

---

## 6. 2차에 바뀌는 것

| 항목 | 1차 (현재) | 2차 |
| --- | --- | --- |
| 빌드 | 맥북에서 수동 `buildx` | GitHub Actions |
| 인증 | 민지 IAM 사용자 키 | **GitHub OIDC** — 키 없음 (§7) |
| push | 수동 | Actions가 자동 |
| 배포 | EC2에서 수동 `pull` | **SSM Run Command** (§7) |
| 태그 | `latest` | `latest` + git SHA |
| 스캔 | ECR `scanOnPush` | + Trivy CI 복구 (§13.1) |

**민지 IAM 사용자 정책은 2차에 제거 대상**입니다. OIDC로 옮기면 사람 계정에 push 권한을
둘 이유가 없어집니다 — 그게 키리스 인증의 목적입니다.

---

## 부록 — 용어

| 용어 | 뜻 |
| --- | --- |
| **ECR** | Elastic Container Registry. AWS의 Docker 이미지 저장소 |
| **레지스트리 / 리포지토리** | 레지스트리 = 계정별 저장소 전체, 리포지토리 = 이미지 한 종류 |
| **인스턴스 역할** | EC2에 부여하는 IAM 역할. 액세스 키 없이 임시 자격증명 발급 |
| **인스턴스 프로파일** | 역할을 EC2에 연결하기 위한 컨테이너. 역할 1개만 담김 |
| **수명주기 정책** | 오래된 이미지를 자동 삭제하는 규칙 |
| **`buildx`** | 크로스 플랫폼 빌드를 지원하는 Docker 빌더 |
| **최소 권한** | 필요한 작업·리소스만 허용하는 원칙 |
