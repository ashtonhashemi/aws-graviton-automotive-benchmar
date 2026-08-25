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
  --no-fail-on-empty-changeset \
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
ZCU_IP="$(output X86ZcuPrivateIp)"
HPC_IP="$(output GravitonHpcPrivateIp)"
P2_TESTER_IP="$(output P2TesterPrivateIp)"
P2_HPC_IP="$(output P2HpcPrivateIp)"
P2_ZONE_IP="$(output P2ZonePrivateIp)"
P2_TARGET_IP="$(output P2TargetPrivateIp)"

# Runtime assets fetched by SSM onto EC2 nodes.
aws s3 cp network/zcu_esc.py "s3://$RESULTS_BUCKET/assets/zcu_esc.py" --region "$REGION"
aws s3 cp network/hpc_vehicle.py "s3://$RESULTS_BUCKET/assets/hpc_vehicle.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_target_ecu.py "s3://$RESULTS_BUCKET/assets/p2_target_ecu.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_relay.py "s3://$RESULTS_BUCKET/assets/p2_relay.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_tester.py "s3://$RESULTS_BUCKET/assets/p2_tester.py" --region "$REGION"
# Keep the standalone single-process model available for local/reference testing.
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
Dashboard:       $DASHBOARD_URL
API:             $API_URL
ESC Graviton HPC: $HPC_IP
ESC x86 ZCU:      $ZCU_IP
P2 Tester:        $P2_TESTER_IP
P2 HPC:           $P2_HPC_IP
P2 Zone:          $P2_ZONE_IP
P2 Target ECU:    $P2_TARGET_IP
ESC transport:    UDP/5005 over private VPC networking
P2 transport:     TCP/13400 over private VPC networking

Open the dashboard and enter the ADMIN_TOKEN you supplied at deploy time.
IMPORTANT: all EC2 lab nodes are intended to remain stopped when experiments are not running.
EOF
