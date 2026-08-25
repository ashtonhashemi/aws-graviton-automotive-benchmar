#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="${STACK_NAME:-aws-graviton-automotive-benchmark}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

DASHBOARD_BUCKET="$(output DashboardBucket)"
API_URL="$(output ApiUrl)"
DIST_ID="$(output DashboardDistributionId)"
DASHBOARD_URL="$(output DashboardUrl)"

if [[ -z "$DASHBOARD_BUCKET" || "$DASHBOARD_BUCKET" == "None" ]]; then
  echo "Could not find dashboard outputs for stack $STACK_NAME in $REGION" >&2
  exit 1
fi

# Upload browser assets explicitly so MIME types and cache behavior cannot drift.
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
aws cloudfront wait invalidation-completed \
  --distribution-id "$DIST_ID" \
  --id "$INVALIDATION_ID"

cat <<EOF
Dashboard update is live.
Dashboard: $DASHBOARD_URL
API:       $API_URL

Open the Dashboard URL in a new browser tab. You should immediately see:
  Dashboard JavaScript loaded. Enter/confirm the admin token and click Use configuration.
EOF
