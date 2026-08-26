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

# Runtime assets fetched by SSM onto EC2 nodes.
aws s3 cp network/zcu_esc.py "s3://$RESULTS_BUCKET/assets/zcu_esc.py" --region "$REGION"
aws s3 cp network/hpc_vehicle.py "s3://$RESULTS_BUCKET/assets/hpc_vehicle.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/doip_codec.py "s3://$RESULTS_BUCKET/assets/doip_codec.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_diag_server.py "s3://$RESULTS_BUCKET/assets/p2_diag_server.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_router.py "s3://$RESULTS_BUCKET/assets/p2_router.py" --region "$REGION"
aws s3 cp diagnostic_timing/aws_measured/p2_tester.py "s3://$RESULTS_BUCKET/assets/p2_tester.py" --region "$REGION"
aws s3 cp benchmark/benchmark.py "s3://$RESULTS_BUCKET/assets/benchmark.py" --region "$REGION"

# Upload browser assets explicitly with deterministic MIME and no-cache headers.
aws s3 cp dashboard/index.html "s3://$DASHBOARD_BUCKET/index.html" \
  --content-type text/html --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"
aws s3 cp dashboard/app.js "s3://$DASHBOARD_BUCKET/app.js" \
  --content-type application/javascript --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"
aws s3 cp dashboard/benchmark_v3.js "s3://$DASHBOARD_BUCKET/benchmark_v3.js" \
  --content-type application/javascript --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"
aws s3 cp dashboard/benchmark-architecture.svg "s3://$DASHBOARD_BUCKET/benchmark-architecture.svg" \
  --content-type image/svg+xml --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"
aws s3 cp dashboard/style.css "s3://$DASHBOARD_BUCKET/style.css" \
  --content-type text/css --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"

TMP_CONFIG="$(mktemp)"
python3 - "$API_URL" > "$TMP_CONFIG" <<'PY'
import json, sys
api_url = sys.argv[1]
print(f"window.APP_CONFIG = {{ apiBase: {json.dumps(api_url)} }};")
print("try { if (!sessionStorage.getItem('p2ModeMeasuredDefaultV3')) { sessionStorage.setItem('p2Mode', 'measured'); sessionStorage.setItem('p2ModeMeasuredDefaultV3', '1'); } } catch (_) {}")
print("window.addEventListener('DOMContentLoaded', () => { const s=document.createElement('script'); s.src='benchmark_v3.js'; document.body.appendChild(s); });")
PY
aws s3 cp "$TMP_CONFIG" "s3://$DASHBOARD_BUCKET/config.js" \
  --content-type application/javascript --cache-control 'no-store,no-cache,must-revalidate,max-age=0' --region "$REGION"
rm -f "$TMP_CONFIG"

INVALIDATION_ID="$(aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" --paths '/*' --query 'Invalidation.Id' --output text)"
echo "Waiting for CloudFront invalidation $INVALIDATION_ID to complete..."
aws cloudfront wait invalidation-completed --distribution-id "$DIST_ID" --id "$INVALIDATION_ID"

cat <<EOF
Deployment complete.
Dashboard: $DASHBOARD_URL
API:       $API_URL

ESC SIL:
  Graviton HPC: $(output GravitonHpcPrivateIp)
  x86 ZCU:      $(output X86ZcuPrivateIp)

Measured SAE J1979-2 / OBDonUDS architecture benchmark:
  Tester:         $(output P2TesterPrivateIp)
  Legacy Gateway: $(output P2LegacyGatewayPrivateIp)
  Legacy ECU 1:   $(output P2LegacyEcu1PrivateIp)  [CAN-FD Bus A]
  Legacy ECU 2:   $(output P2LegacyEcu2PrivateIp)  [CAN-FD Bus A]
  Legacy ECU 3:   $(output P2LegacyEcu3PrivateIp)  [CAN-FD Bus B]
  Legacy ECU 4:   $(output P2LegacyEcu4PrivateIp)  [CAN-FD Bus C]
  Graviton HPC:   $(output P2HpcPrivateIp)
  ZCU 1:          $(output P2Zcu1PrivateIp)
  ZCU 2:          $(output P2Zcu2PrivateIp)
  ZCU 3:          $(output P2Zcu3PrivateIp)
  ZCU 4:          $(output P2Zcu4PrivateIp)

Measured diagnostic transport: DoIP framing over private VPC TCP/13400.
Benchmark comparison: legacy gateway + CAN-FD versus Graviton HPC application proxy + automotive Ethernet.
Dashboard controls: J1979-2 service, sequential/4-way traffic, three CAN-FD bus loads,
CAN-FD bit rates, automotive-Ethernet rate/load, CPU pressure, server processing, proxy workload, and P2 budget.
The J1979-2 service harness uses synthetic lab data and is not a conformance test.
All EC2 lab nodes are intended to remain stopped when experiments are not running.
EOF