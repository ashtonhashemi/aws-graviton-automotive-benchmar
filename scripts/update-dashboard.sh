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

aws s3 sync dashboard/ "s3://$DASHBOARD_BUCKET/" --delete --exclude config.js --region "$REGION"
TMP_CONFIG="$(mktemp)"
printf 'window.APP_CONFIG = { apiBase: %s };\n' "$(printf '%s' "$API_URL" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" > "$TMP_CONFIG"
aws s3 cp "$TMP_CONFIG" "s3://$DASHBOARD_BUCKET/config.js" --content-type application/javascript --cache-control no-store --region "$REGION"
rm -f "$TMP_CONFIG"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths '/*' >/dev/null

cat <<EOF
Dashboard files updated and CloudFront invalidation requested.
Dashboard: $DASHBOARD_URL
API:       $API_URL

Hard-refresh the browser after the invalidation completes.
EOF
