#!/usr/bin/env bash
# CloudWatch 알람 → Discord 파이프라인 배포
#
#   CloudWatch 알람 → SNS 토픽 → Lambda → Discord 웹훅
#
# 사용법:
#   DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...' ./deploy.sh
#
# 멱등하게 동작한다 — 이미 있으면 갱신만 한다. 여러 번 실행해도 안전.

set -euo pipefail

REGION=${REGION:-ap-northeast-2}
TOPIC=${TOPIC:-seoganpyo-alarms}
FUNC=${FUNC:-seoganpyo-alarm-to-discord}
ROLE=${ROLE:-SeoganpyoAlarmLambdaRole}
INSTANCE_ID=${INSTANCE_ID:-i-0cf5fbf562ec4017b}
DB_INSTANCE=${DB_INSTANCE:-seoganpyo-db}

if [ -z "${DISCORD_WEBHOOK_URL:-}" ]; then
    echo "ERROR: DISCORD_WEBHOOK_URL 환경변수가 필요합니다" >&2
    exit 1
fi

ACCT=$(aws sts get-caller-identity --query Account --output text)
cd "$(dirname "$0")"

echo "[1/6] SNS 토픽"
TOPIC_ARN=$(aws sns create-topic --name "$TOPIC" --region "$REGION" \
    --tags Key=Project,Value=seoganpyo Key=Env,Value=prod \
    --query TopicArn --output text)
echo "      $TOPIC_ARN"

echo "[2/6] Lambda 실행 역할"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    aws iam create-role --role-name "$ROLE" \
        --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
        --tags Key=Project,Value=seoganpyo >/dev/null
    # 로그만 쓸 수 있으면 된다 — Discord 호출은 아웃바운드라 IAM 권한 불필요
    aws iam attach-role-policy --role-name "$ROLE" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    echo "      생성 — IAM 전파 대기 10초"
    sleep 10
else
    echo "      이미 있음"
fi
ROLE_ARN="arn:aws:iam::${ACCT}:role/${ROLE}"

echo "[3/6] 함수 패키징"
rm -f function.zip
zip -q function.zip lambda_function.py

echo "[4/6] Lambda 배포"
if aws lambda get-function --function-name "$FUNC" --region "$REGION" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$FUNC" \
        --zip-file fileb://function.zip --region "$REGION" >/dev/null
    aws lambda wait function-updated --function-name "$FUNC" --region "$REGION"
    aws lambda update-function-configuration --function-name "$FUNC" \
        --environment "Variables={DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL}" \
        --region "$REGION" >/dev/null
    echo "      갱신"
else
    aws lambda create-function --function-name "$FUNC" \
        --runtime python3.12 --handler lambda_function.lambda_handler \
        --role "$ROLE_ARN" --zip-file fileb://function.zip \
        --timeout 15 --memory-size 128 \
        --environment "Variables={DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK_URL}" \
        --tags Project=seoganpyo,Env=prod --region "$REGION" >/dev/null
    echo "      생성"
fi
FUNC_ARN=$(aws lambda get-function --function-name "$FUNC" --region "$REGION" \
    --query 'Configuration.FunctionArn' --output text)

echo "[5/6] SNS → Lambda 연결"
aws lambda add-permission --function-name "$FUNC" \
    --statement-id sns-invoke --action lambda:InvokeFunction \
    --principal sns.amazonaws.com --source-arn "$TOPIC_ARN" \
    --region "$REGION" >/dev/null 2>&1 || true   # 이미 있으면 무시
aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol lambda \
    --notification-endpoint "$FUNC_ARN" --region "$REGION" >/dev/null

echo "[6/6] CloudWatch 알람"

mk_alarm() {  # 이름 설명 네임스페이스 지표 통계 비교 임계 기간 횟수 차원...
    local name=$1 desc=$2 ns=$3 metric=$4 stat=$5 op=$6 threshold=$7 period=$8 evals=$9
    shift 9
    aws cloudwatch put-metric-alarm \
        --alarm-name "$name" --alarm-description "$desc" \
        --namespace "$ns" --metric-name "$metric" --statistic "$stat" \
        --comparison-operator "$op" --threshold "$threshold" \
        --period "$period" --evaluation-periods "$evals" \
        --treat-missing-data notBreaching \
        --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN" \
        --dimensions "$@" --region "$REGION"
    echo "      $name"
}

# EC2 — 인스턴스 자체가 죽은 경우. 컨테이너 헬스체크로는 못 잡는다
mk_alarm seoganpyo-ec2-status-check "EC2 상태 검사 실패" \
    AWS/EC2 StatusCheckFailed Maximum GreaterThanThreshold 0 300 1 \
    Name=InstanceId,Value="$INSTANCE_ID"

# CPU 크레딧 — t3.micro 는 버스터블. 소진되면 baseline 으로 강제 제한돼
# 성능이 급락하는데 CPU 사용률만 보면 원인을 알 수 없다 (docs/performance.md §3.4)
mk_alarm seoganpyo-ec2-cpu-credit-low "CPU 크레딧 부족 — 스로틀링 임박" \
    AWS/EC2 CPUCreditBalance Average LessThanThreshold 50 300 2 \
    Name=InstanceId,Value="$INSTANCE_ID"

# RDS 연결 수 — 2026-09-27 교착 때 풀이 전부 점유됐다
mk_alarm seoganpyo-rds-connections-high "RDS 연결 수 과다" \
    AWS/RDS DatabaseConnections Average GreaterThanThreshold 40 300 2 \
    Name=DBInstanceIdentifier,Value="$DB_INSTANCE"

# RDS 여유 메모리 — db.t4g.micro 는 1GB
mk_alarm seoganpyo-rds-memory-low "RDS 여유 메모리 부족" \
    AWS/RDS FreeableMemory Average LessThanThreshold 100000000 300 2 \
    Name=DBInstanceIdentifier,Value="$DB_INSTANCE"

rm -f function.zip
echo
echo "완료. 테스트 발송:"
echo "  aws sns publish --topic-arn $TOPIC_ARN --region $REGION \\"
echo "    --message '{\"AlarmName\":\"테스트\",\"NewStateValue\":\"ALARM\",\"NewStateReason\":\"수동 테스트\",\"Region\":\"Seoul\"}'"
