#!/usr/bin/env bash
set -euo pipefail
STACK_NAME="${STACK_NAME:-aws-graviton-automotive-benchmark}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
output() { aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text; }
RESULTS_BUCKET="$(output ResultsBucket)"
DASHBOARD_BUCKET="$(output DashboardBucket)"
aws s3 rm "s3://$RESULTS_BUCKET" --recursive --region "$REGION" || true
aws s3 rm "s3://$DASHBOARD_BUCKET" --recursive --region "$REGION" || true
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"
echo "Delete requested for stack $STACK_NAME"
