#!/usr/bin/env bash
# SSM Parameter Store → .env 생성 (EC2 에서 실행)
#
#   ~/seoganpyo/scripts/ssm-fetch-env.sh
#
# deploy.sh 가 기동 전에 호출한다. 배포할 때마다 최신 값을 받아오므로
# 값을 바꿀 때 EC2 에 들어가 파일을 고칠 필요가 없다 — SSM 만 갱신하면 된다.
#
# 액세스 키는 쓰지 않는다. EC2 인스턴스 역할로 조회한다.
#
# ⚠️ .env 는 여전히 디스크에 쓰인다. docker compose 가 env_file 을 읽어야 하기 때문.
#    SSM 이 주는 이점은 "저장소가 암호화되고, 값 배포가 중앙화된다" 는 것이지
#    EC2 에서 평문이 사라지는 게 아니다. 그래서 chmod 600 은 그대로 유지한다.

set -euo pipefail

REGION=${REGION:-ap-northeast-2}
PREFIX=${PREFIX:-/seoganpyo/prod}
OUT=${OUT:-$HOME/seoganpyo/.env}

echo "SSM 에서 환경변수 조회: ${PREFIX}"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
chmod 600 "$TMP"

# --with-decryption: SecureString 을 평문으로 받는다 (인스턴스 역할에 kms:Decrypt 필요)
# 파라미터가 10개를 넘으면 페이지가 나뉘므로 --page-size 로 한 번에 받는다
aws ssm get-parameters-by-path \
    --path "$PREFIX" \
    --with-decryption \
    --recursive \
    --page-size 10 \
    --region "$REGION" \
    --query 'Parameters[].[Name,Value]' \
    --output text \
    | while IFS=$'\t' read -r name value; do
        [ -n "$name" ] || continue
        printf '%s=%s\n' "${name##*/}" "$value"
      done > "$TMP"

COUNT=$(wc -l < "$TMP" | tr -d ' ')
if [ "$COUNT" -eq 0 ]; then
    echo "ERROR: SSM 에서 아무것도 받지 못했습니다 (경로·권한 확인)" >&2
    exit 1
fi

# 기존 파일 백업 — 롤백 수단
[ -f "$OUT" ] && cp -p "$OUT" "${OUT}.bak"

mv "$TMP" "$OUT"
trap - EXIT
chmod 600 "$OUT"

# root 로 실행돼도(SSM Run Command 기본값·sudo) .env 주인은 폴더 주인(ec2-user)으로 맞춘다.
# 2026-10-08: root 소유 .env(600) 를 ec2-user 로 도는 deploy.sh 가 못 읽어 배포가 실패했음.
if [ "$(id -u)" -eq 0 ]; then
    chown "$(stat -c '%u:%g' "$(dirname "$OUT")")" "$OUT" "${OUT}.bak" 2>/dev/null || true
fi

echo "  ${COUNT}개 → ${OUT}"
