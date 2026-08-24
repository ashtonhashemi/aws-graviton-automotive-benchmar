#!/usr/bin/env bash
set -euo pipefail
STACK_NAME="${STACK_NAME:-aws-graviton-automotive-benchmark}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
ids=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='X86InstanceId'||OutputKey=='ArmInstanceId'].OutputValue" --output text)
aws ec2 stop-instances --instance-ids $ids --region "$REGION" >/dev/null
echo "Stop requested for: $ids"
