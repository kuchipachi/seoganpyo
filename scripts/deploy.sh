#!/usr/bin/env bash
# EC2 배포 — ECR 재인증 → pull → 기동 → Caddy 갱신 → 검증
#
#   ~/seoganpyo/deploy.sh            전체
#   ~/seoganpyo/deploy.sh backend    특정 서비스만
#
# 맥북에서 scripts/build-push.sh 로 이미지를 올린 뒤 실행한다.
#
# 이 스크립트는 EC2 의 ~/seoganpyo/ 에 두고 쓴다 (레포에도 두는 이유는
# EC2 를 재생성하면 사라지기 때문 — 복구 가능해야 한다).

set -euo pipefail
cd "$HOME/seoganpyo"

[ -f .env ] || { echo "ERROR: ~/seoganpyo/.env 가 없습니다" >&2; exit 1; }
source .env

DC="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
SVC=("$@")

echo "[1/5] ECR 로그인"
# 토큰은 12시간마다 만료된다 — 배포할 때마다 새로 받는다
aws ecr get-login-password --region ap-northeast-2 \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null
echo "      OK"

echo "[2/5] 이미지 pull"
$DC pull "${SVC[@]}"

echo "[3/5] 컨테이너 기동"
$DC up -d "${SVC[@]}"

# backend 를 재생성하면 컨테이너 IP 가 바뀌는데 Caddy 가 옛 IP 를 캐시해 502 가 난다.
# 실제로 겪은 문제라 스크립트에 넣어 잊지 않게 한다.
echo "[4/5] Caddy 재시작"
$DC restart caddy
sleep 5

echo "[5/5] 스모크 테스트"
if [ -x ./scripts/smoke-test.sh ]; then
    ./scripts/smoke-test.sh
else
    echo "      ⚠️ scripts/smoke-test.sh 가 없습니다 — 수동 확인 필요"
    $DC ps
fi
