import base64
import json
import os
from decimal import Decimal
import time
import uuid

import boto3

EC2 = boto3.client("ec2")
SSM = boto3.client("ssm")
S3 = boto3.client("s3")
DDB = boto3.resource("dynamodb").Table(os.environ["RESULTS_TABLE"])
BUCKET = os.environ["RESULTS_BUCKET"]
X86_ID = os.environ["X86_INSTANCE_ID"]
ARM_ID = os.environ["ARM_INSTANCE_ID"]
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def response(code, body):
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def authorized(event):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return headers.get("x-admin-token") == ADMIN_TOKEN


def state(instance_id):
    r = EC2.describe_instances(InstanceIds=[instance_id])
    i = r["Reservations"][0]["Instances"][0]
    return {
        "instance_id": instance_id,
        "state": i["State"]["Name"],
        "instance_type": i["InstanceType"],
        "architecture": i["Architecture"],
    }


def start_stop(instance_id, action):
    if action == "start":
        EC2.start_instances(InstanceIds=[instance_id])
    elif action == "stop":
        EC2.stop_instances(InstanceIds=[instance_id])
    else:
        raise ValueError("action must be start or stop")


def command_for(run_id, arch, records, iterations, mode, auto_stop):
    out = f"/tmp/{run_id}-{arch}.json"
    commands = [
        "set -euo pipefail",
        f"aws s3 cp s3://{BUCKET}/assets/benchmark.py /tmp/benchmark.py",
        f"python3 /tmp/benchmark.py --records {records} --iterations {iterations} --mode {mode} --output {out}",
        f"aws s3 cp {out} s3://{BUCKET}/results/{run_id}/{arch}.json",
    ]
    if auto_stop:
        commands.append("sudo shutdown -h now")
    return commands


def run_benchmark(body):
    records = int(body.get("records", 500000))
    iterations = int(body.get("iterations", 5))
    mode = body.get("mode", "baseline")
    auto_stop = bool(body.get("auto_stop", True))
    if not (1 <= records <= 5_000_000 and 1 <= iterations <= 20 and mode in ("baseline", "optimized")):
        raise ValueError("invalid benchmark parameters")

    states = {"x86_64": state(X86_ID), "arm64": state(ARM_ID)}
    if any(v["state"] != "running" for v in states.values()):
        return response(409, {"error": "Both instances must be running", "instances": states})

    run_id = str(uuid.uuid4())
    commands = {}
    for arch, iid in (("x86_64", X86_ID), ("arm64", ARM_ID)):
        r = SSM.send_command(
            InstanceIds=[iid],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": command_for(run_id, arch, records, iterations, mode, auto_stop)},
            TimeoutSeconds=3600,
        )
        commands[arch] = r["Command"]["CommandId"]

    DDB.put_item(Item={
        "run_id": run_id,
        "created_at": int(time.time()),
        "records": records,
        "iterations": iterations,
        "mode": mode,
        "auto_stop": auto_stop,
        "x86_command_id": commands["x86_64"],
        "arm_command_id": commands["arm64"],
    })
    return response(202, {"run_id": run_id, "commands": commands})


def get_json(key):
    try:
        obj = S3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    except S3.exceptions.NoSuchKey:
        return None
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise


def get_result(run_id):
    item = DDB.get_item(Key={"run_id": run_id}).get("Item")
    if not item:
        return response(404, {"error": "run not found"})
    x86 = get_json(f"results/{run_id}/x86_64.json")
    arm = get_json(f"results/{run_id}/arm64.json")
    body = {"run": item, "x86_64": x86, "arm64": arm, "complete": bool(x86 and arm)}
    if x86 and arm:
        xt = float(x86["throughput_records_per_sec"])
        at = float(arm["throughput_records_per_sec"])
        body["comparison"] = {
            "arm_vs_x86_throughput_ratio": round(at / xt, 3) if xt else None,
            "faster_architecture": "arm64" if at > xt else "x86_64",
        }
    return response(200, body)


def handler(event, context):
    if not authorized(event):
        return response(401, {"error": "unauthorized"})

    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    try:
        if method == "GET" and path == "/status":
            return response(200, {"x86_64": state(X86_ID), "arm64": state(ARM_ID)})

        if method == "POST" and path.startswith("/instances/"):
            parts = path.strip("/").split("/")
            if len(parts) != 3:
                return response(404, {"error": "not found"})
            _, arch, action = parts
            iid = X86_ID if arch == "x86_64" else ARM_ID if arch == "arm64" else None
            if not iid:
                return response(400, {"error": "arch must be x86_64 or arm64"})
            start_stop(iid, action)
            return response(202, {"arch": arch, "action": action})

        if method == "POST" and path == "/benchmark/run":
            raw_body = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            return run_benchmark(json.loads(raw_body))

        if method == "GET" and path.startswith("/benchmark/results/"):
            return get_result(path.rsplit("/", 1)[-1])

        return response(404, {"error": "not found"})
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except Exception as exc:
        print(repr(exc))
        return response(500, {"error": "internal error"})
