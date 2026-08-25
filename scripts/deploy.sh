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

# Upload browser assets explicitly with deterministic MIME and no-cache headers.
aws s3 cp dashboard/index.html "s3://$DASHBOARD_BUCKET/index.html" \
  --content-type text/html \
  --cache-control 'no-store,no-cache,must-revalidate,max-age=0' \
  --region "$REGION"
aws s3 cp dashboard/app.js "s3://$DASHBOARD_BUCKET/app.js" \
  --content-type application/javascript \
  --cache-control 'no-store,no-cache,must-revalidate,max-age=0' \
  --region "$REGION"
aws s3 cp dashboard/style.css "s3://$DASHBOARD_BUCKET/style.css" \
  --content-type text/css \
  --cache-control 'no-store,no-cache,must-revalidate,max-age=0' \
  --region "$REGION"

TMP_CONFIG="$(mktemp)"
printf 'window.APP_CONFIG = { apiBase: %s };\n' "$(printf '%s' "$API_URL" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" > "$TMP_CONFIG"
aws s3 cp "$TMP_CONFIG" "s3://$DASHBOARD_BUCKET/config.js" \
  --content-type application/javascript \
  --cache-control 'no-store,no-cache,must-revalidate,max-age=0' \
  --region "$REGION"
rm -f "$TMP_CONFIG"

INVALIDATION_ID="$(aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths '/*' \
  --query 'Invalidation.Id' \
  --output text)"
echo "Waiting for CloudFront invalidation $INVALIDATION_ID to complete..."
aws cloudfront wait invalidation-completed --distribution-id "$DIST_ID" --id "$INVALIDATION_ID"

cat <<EOF
Deployment complete.
Dashboard: $DASHBOARD_URL
API:       $API_URL

Open the dashboard and enter the ADMIN_TOKEN you supplied at deploy time.
The dashboard should immediately show that its JavaScript loaded.
IMPORTANT: EC2 instances are created in running state. Stop both from the dashboard when not benchmarking.
EOF
