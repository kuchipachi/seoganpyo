#!/usr/bin/env bash
# EC2 의 .env → SSM Parameter Store 로 이관 (1회성, 맥북/CloudShell 에서 실행)
#
#   ./scripts/ssm-put-params.sh <.env 파일 경로>
#   ./scripts/ssm-put-params.sh ~/Downloads/env-from-ec2
#
# 왜:
#   지금 EC2 의 .env 는 평문이고 chmod 600 이 유일한 보호다.
#   DB 비밀번호·API 키가 파일에 그대로 있어, 인스턴스에 들어간 사람은 전부 읽을 수 있다.
#   SSM SecureString 은 KMS 로 암호화되고, EC2 는 인스턴스 역할로 조회한다.
#
# 분류 근거는 docs/env-reference.md 의 SSM 열:
#   🔒 SecureString (비밀)  /  📄 String (비밀 아님)
#
# ⚠️ 이 스크립트는 값을 읽어 SSM 에 쓴다. 로그·히스토리에 값이 남지 않게 주의할 것.

set -euo pipefail

REGION=${REGION:-ap-northeast-2}
PREFIX=${PREFIX:-/seoganpyo/prod}
ENV_FILE=${1:-}

[ -n "$ENV_FILE" ] || { echo "사용법: $0 <.env 파일 경로>" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE 이 없습니다" >&2; exit 1; }

# 비밀로 다룰 키 — 나머지는 String.
# 애매하면 SecureString 쪽에 넣는다 (String 은 콘솔에서 그대로 보인다).
SECURE_KEYS="DB_USER DB_PASSWORD SECRET_KEY ADMIN_SECRET_KEY SENDER_EMAIL SENDER_PASSWORD MISTRAL_API_KEY GEMINI_API_KEY DISCORD_ALERT_WEBHOOK DEFECTDOJO_TOKEN GRAFANA_CLOUD_TOKEN"

is_secure() {
    case " $SECURE_KEYS " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

put=0 skipped=0
while IFS= read -r line || [ -n "$line" ]; do
    # 주석·빈 줄 건너뜀
    case "$line" in ''|'#'*) continue ;; esac
    key=${line%%=*}
    val=${line#*=}
    # key 형식이 아니면 건너뜀 (= 가 없는 줄 등)
    case "$key" in *[!A-Za-z0-9_]*|'') continue ;; esac
    # 빈 값은 등록하지 않는다 — 미설정과 빈 문자열은 앱에서 의미가 다를 수 있다
    [ -n "$val" ] || { printf '  ⏭  %-28s (빈 값)\n' "$key"; skipped=$((skipped+1)); continue; }

    if is_secure "$key"; then
        type=SecureString; mark="🔒"
    else
        type=String;       mark="📄"
    fi

    aws ssm put-parameter \
        --name "${PREFIX}/${key}" \
        --value "$val" \
        --type "$type" \
        --overwrite \
        --region "$REGION" >/dev/null

    printf '  %s %-28s %s\n' "$mark" "$key" "$type"
    put=$((put+1))
done < "$ENV_FILE"

echo
echo "등록 ${put}건 / 건너뜀 ${skipped}건  →  ${PREFIX}/"
echo
echo "확인:"
echo "  aws ssm get-parameters-by-path --path ${PREFIX} --region ${REGION} \\"
echo "    --query 'Parameters[].[Name,Type]' --output table"
