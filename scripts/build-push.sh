#!/usr/bin/env bash
# 이미지 빌드 → ECR push (맥북에서 실행)
#
#   ./scripts/build-push.sh              api 만 (가장 흔한 경우)
#   ./scripts/build-push.sh api frontend 여러 개
#   ./scripts/build-push.sh all          셋 다
#
# EC2(1GiB)에서는 빌드가 OOM 나므로 맥북에서 만들어 ECR 로 올린다.
# 그다음 EC2 에서 ~/seoganpyo/deploy.sh 로 pull·기동.
#
# ⚠️ Apple Silicon 주의: --platform linux/amd64 필수.
#    안 붙이면 arm64 이미지가 올라가 EC2 에서 exec format error 가 난다.

set -euo pipefail
cd "$(dirname "$0")/.."

REGION=${REGION:-ap-northeast-2}
TAG=${TAG:-latest}

# 운영 주소 — 공개 레포라 IP 를 코드에 두지 않는다 (smoke-test.sh 와 같은 방식).
# EIP 재할당 시 고칠 곳을 줄이려는 목적도 있다.
# frontend 를 빌드할 때만 필요하므로 여기서 죽이지 않고 아래에서 확인한다.
if [ -z "${DOMAIN:-}" ]; then
    DOMAIN=$(grep -s '^DOMAIN=' .env | cut -d= -f2-)
fi

# ── AWS 인증 확인 ─────────────────────────────────────
# 토큰 만료·키 미설정으로 막히는 일이 잦아 먼저 확인하고 안내한다
if ! ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
    cat >&2 <<'MSG'
ERROR: AWS 인증이 안 됩니다.

  export AWS_ACCESS_KEY_ID=...
  export AWS_SECRET_ACCESS_KEY=...
  export AWS_DEFAULT_REGION=ap-northeast-2

키가 없으면 IAM 콘솔 → 사용자 → 보안 자격 증명에서 발급하세요.
MSG
    exit 1
fi
REG="${ACCT}.dkr.ecr.${REGION}.amazonaws.com"

# ── 대상 결정 ─────────────────────────────────────────
TARGETS=(${@+"$@"})
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(api)
[ "${TARGETS[0]}" = "all" ] && TARGETS=(api frontend ocr)

echo "레지스트리 : $REG"
echo "태그       : $TAG"
echo "대상       : ${TARGETS[*]}"
echo

# ── 커밋되지 않은 변경 경고 ───────────────────────────
# 로컬 수정분이 섞인 이미지를 운영에 올리는 사고를 막는다
if ! git diff --quiet HEAD 2>/dev/null; then
    echo "⚠️  커밋되지 않은 변경이 있습니다:"
    git status --short | sed 's/^/     /'
    read -rp "   이대로 빌드할까요? [y/N] " ans
    [ "$ans" = "y" ] || exit 1
    echo
fi

echo "브랜치: $(git branch --show-current)  커밋: $(git rev-parse --short HEAD)"
echo

echo "[1/2] ECR 로그인"
aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$REG" >/dev/null
echo "      OK"

echo "[2/2] 빌드 & push"
for t in "${TARGETS[@]}"; do
    case "$t" in
        api)
            ctx="." ; args=()
            ;;
        frontend)
            ctx="./frontend"
            # NEXT_PUBLIC_* 는 빌드 타임에 이미지에 박힌다 — 도메인이 바뀌면 재빌드 필요.
            # 비어 있으면 https:///backend 로 박혀 배포는 되는데 화면만 안 뜬다.
            : "${DOMAIN:?DOMAIN 필요 — 예) DOMAIN=<EIP>.nip.io ./scripts/build-push.sh frontend  (또는 .env 에 DOMAIN=)}"
            # /backend 는 Caddy 가 백엔드로 보내는 prefix (infra/caddy/Caddyfile)
            args=(--build-arg "NEXT_PUBLIC_API_URL=https://${DOMAIN}/backend"
                  --build-arg "NEXT_PUBLIC_GRAFANA_URL=${GRAFANA_URL:-}")
            ;;
        ocr)
            ctx="./ocr-service" ; args=()
            ;;
        *)
            echo "      알 수 없는 대상: $t (api|frontend|ocr|all)" >&2; exit 1
            ;;
    esac

    echo "      → seoganpyo-$t"
    # bash 3.2(macOS 기본)에서는 set -u 와 빈 배열 참조가 충돌한다 → ${a[@]+"${a[@]}"}
    docker buildx build --platform linux/amd64 \
        ${args[@]+"${args[@]}"} \
        -t "${REG}/seoganpyo-${t}:${TAG}" \
        "$ctx" --push
done

echo
echo "완료. 배포하세요:"
echo "  GitHub Actions 의 Deploy 워크플로 실행 (권장)"
echo "  또는 Session Manager 접속 후:  ~/seoganpyo/deploy.sh"
echo "    aws ssm start-session --target <INSTANCE_ID> --region ${REGION}"
