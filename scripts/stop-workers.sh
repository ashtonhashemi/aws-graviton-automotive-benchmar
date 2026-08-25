#!/usr/bin/env bash
set -euo pipefail
STACK_NAME="${STACK_NAME:-aws-graviton-automotive-benchmark}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-west-2}}"
ids=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='X86InstanceId'||OutputKey=='ArmInstanceId'||OutputKey=='P2TesterInstanceId'||OutputKey=='P2HpcInstanceId'||OutputKey=='P2ZoneInstanceId'||OutputKey=='P2TargetInstanceId'].OutputValue" \
  --output text)
if [[ -z "$ids" || "$ids" == "None" ]]; then
  echo "No worker instance IDs found in stack $STACK_NAME"
  exit 0
fi
aws ec2 stop-instances --instance-ids $ids --region "$REGION" >/dev/null
echo "Stop requested for all automotive lab workers: $ids"
