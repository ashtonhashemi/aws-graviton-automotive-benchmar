#!/usr/bin/env bash
set -euo pipefail

export AWS_REGION="${AWS_REGION:-us-west-2}"

if ! aws sts get-caller-identity --region "$AWS_REGION" >/dev/null 2>&1; then
  cat <<'EOF'
AWS is not authenticated in this Codespace yet.

Authenticate first, then rerun this script. Common options:
  aws configure
or, if your AWS account uses IAM Identity Center:
  aws configure sso
  aws sso login

Verify with:
  aws sts get-caller-identity
EOF
  exit 1
fi

if [[ -z "${VPC_ID:-}" ]]; then
  VPC_ID="$(aws ec2 describe-vpcs \
    --region "$AWS_REGION" \
    --filters Name=is-default,Values=true \
    --query 'Vpcs[0].VpcId' \
    --output text)"
fi

if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
  echo "No default VPC was found in $AWS_REGION."
  echo "Set VPC_ID and SUBNET_ID manually, then rerun:"
  echo '  export VPC_ID=vpc-xxxxxxxx'
  echo '  export SUBNET_ID=subnet-xxxxxxxx'
  exit 1
fi
export VPC_ID

if [[ -z "${SUBNET_ID:-}" ]]; then
  SUBNET_ID="$(aws ec2 describe-subnets \
    --region "$AWS_REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" Name=map-public-ip-on-launch,Values=true \
    --query 'Subnets[0].SubnetId' \
    --output text)"
fi

if [[ -z "$SUBNET_ID" || "$SUBNET_ID" == "None" ]]; then
  echo "No public-IP-enabled subnet was found in VPC $VPC_ID."
  echo "Set SUBNET_ID to a subnet with outbound internet access, then rerun."
  exit 1
fi
export SUBNET_ID

if [[ -z "${ADMIN_TOKEN:-}" ]]; then
  ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  export ADMIN_TOKEN
fi

TOKEN_FILE="$HOME/.aws-graviton-admin-token"
printf '%s\n' "$ADMIN_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

cat <<EOF
Ready to deploy AWS Graviton Automotive Benchmark
  AWS account: $ACCOUNT_ID
  Region:      $AWS_REGION
  VPC:         $VPC_ID
  Subnet:      $SUBNET_ID

Dashboard admin token saved to:
  $TOKEN_FILE

Admin token:
  $ADMIN_TOKEN
EOF

bash scripts/deploy.sh

cat <<EOF

Deployment command completed.
If you need the dashboard token again:
  cat $TOKEN_FILE

When finished benchmarking, stop compute with:
  bash scripts/stop-workers.sh

To delete the whole lab:
  bash scripts/destroy.sh
EOF
