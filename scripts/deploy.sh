#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-aws-graviton-automotive-benchmark}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
: "${VPC_ID:?Set VPC_ID}"
: "${SUBNET_ID:?Set SUBNET_ID to a subnet with outbound internet access}"
: "${ADMIN_TOKEN:?Set ADMIN_TOKEN to a random value of at least 16 characters}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

sam build --template-file infra/template.yaml
sam deploy \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --parameter-overrides \
    VpcId="$VPC_ID" \
    SubnetId="$SUBNET_ID" \
    AdminToken="$ADMIN_TOKEN"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

RESULTS_BUCKET="$(output ResultsBucket)"
DASHBOARD_BUCKET="$(output DashboardBucket)"
API_URL="$(output ApiUrl)"
DIST_ID="$(output DashboardDistributionId)"
DASHBOARD_URL="$(output DashboardUrl)"

aws s3 cp benchmark/benchmark.py "s3://$RESULTS_BUCKET/assets/benchmark.py" --region "$REGION"
aws s3 sync dashboard/ "s3://$DASHBOARD_BUCKET/" --delete --exclude config.js --region "$REGION"
TMP_CONFIG="$(mktemp)"
printf 'window.APP_CONFIG = { apiBase: %s };\n' "$(printf '%s' "$API_URL" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" > "$TMP_CONFIG"
aws s3 cp "$TMP_CONFIG" "s3://$DASHBOARD_BUCKET/config.js" --content-type application/javascript --cache-control no-store --region "$REGION"
rm -f "$TMP_CONFIG"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' >/dev/null

cat <<EOF
Deployment complete.
Dashboard: $DASHBOARD_URL
API:       $API_URL

Open the dashboard and enter the ADMIN_TOKEN you supplied at deploy time.
IMPORTANT: EC2 instances are created in running state. Stop both from the dashboard when not benchmarking.
EOF
