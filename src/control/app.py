import base64
import json
import os
from decimal import Decimal
import time
import uuid

import boto3
from botocore.exceptions import ClientError

EC2 = boto3.client("ec2")
SSM = boto3.client("ssm")
S3 = boto3.client("s3")
DDB = boto3.resource("dynamodb").Table(os.environ["RESULTS_TABLE"])
BUCKET = os.environ["RESULTS_BUCKET"]
X86_ID = os.environ["X86_INSTANCE_ID"]
ARM_ID = os.environ["ARM_INSTANCE_ID"]
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
UDP_PORT = 5005


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


def ssm_statuses():
    statuses = {}
    token = None
    while True:
        kwargs = {"MaxResults": 50}
        if token:
            kwargs["NextToken"] = token
        page = SSM.describe_instance_information(**kwargs)
        for info in page.get("InstanceInformationList", []):
            iid = info.get("InstanceId")
            if iid in (X86_ID, ARM_ID):
                statuses[iid] = info.get("PingStatus", "Unknown")
        token = page.get("NextToken")
        if not token or len(statuses) == 2:
            break
    return statuses


def state(instance_id, role, ssm_map=None):
    r = EC2.describe_instances(InstanceIds=[instance_id])
    i = r["Reservations"][0]["Instances"][0]
    return {
        "instance_id": instance_id,
        "state": i["State"]["Name"],
        "instance_type": i["InstanceType"],
        "architecture": i["Architecture"],
        "private_ip": i.get("PrivateIpAddress"),
        "role": role,
        "ssm_ping_status": (ssm_map or {}).get(instance_id, "NotRegistered"),
    }


def start_stop(instance_id, action):
    if action == "start":
        EC2.start_instances(InstanceIds=[instance_id])
    elif action == "stop":
        EC2.stop_instances(InstanceIds=[instance_id])
    else:
        raise ValueError("action must be start or stop")


def zcu_commands(run_id, esc, auto_stop):
    out = f"/tmp/{run_id}-zcu.json"
    commands = [
        "set -euo pipefail",
        f"aws s3 cp s3://{BUCKET}/assets/zcu_esc.py /tmp/zcu_esc.py",
        f"python3 /tmp/zcu_esc.py --port {UDP_PORT} --esc {esc} --output {out}",
        f"aws s3 cp {out} s3://{BUCKET}/results/{run_id}/zcu.json",
    ]
    if auto_stop:
        commands.append("sudo shutdown -h now")
    return commands


def hpc_commands(run_id, zcu_ip, esc, auto_stop):
    out = f"/tmp/{run_id}-hpc.json"
    commands = [
        "set -euo pipefail",
        f"aws s3 cp s3://{BUCKET}/assets/hpc_vehicle.py /tmp/hpc_vehicle.py",
        "sleep 2",
        f"python3 /tmp/hpc_vehicle.py --zcu-ip {zcu_ip} --port {UDP_PORT} --esc {esc} --realtime --output {out}",
        f"aws s3 cp {out} s3://{BUCKET}/results/{run_id}/hpc.json",
    ]
    if auto_stop:
        commands.append("sudo shutdown -h now")
    return commands


def run_benchmark(body):
    esc = body.get("esc", "on")
    auto_stop = bool(body.get("auto_stop", True))
    if esc not in ("on", "off"):
        raise ValueError("esc must be on or off")

    ssm_map = ssm_statuses()
    zcu = state(X86_ID, "x86 EC2 ZCU / ESC controller", ssm_map)
    hpc = state(ARM_ID, "Graviton HPC / vehicle and FMVSS maneuver simulator", ssm_map)
    states = {"zcu": zcu, "hpc": hpc}

    if zcu["state"] != "running" or hpc["state"] != "running":
        return response(409, {"error": "Both the Graviton HPC and x86 ZCU must be running", "instances": states})
    if zcu["ssm_ping_status"] != "Online" or hpc["ssm_ping_status"] != "Online":
        return response(409, {
            "error": "EC2 is running, but Systems Manager is not ready on both nodes yet. Refresh Status until both show SSM Online, then run the test.",
            "instances": states,
        })
    if not zcu.get("private_ip"):
        return response(409, {"error": "ZCU private VPC IP is unavailable", "instances": states})

    run_id = str(uuid.uuid4())
    try:
        zcu_cmd = SSM.send_command(
            InstanceIds=[X86_ID],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": zcu_commands(run_id, esc, auto_stop)},
            TimeoutSeconds=600,
        )["Command"]["CommandId"]

        hpc_cmd = SSM.send_command(
            InstanceIds=[ARM_ID],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": hpc_commands(run_id, zcu["private_ip"], esc, auto_stop)},
            TimeoutSeconds=600,
        )["Command"]["CommandId"]
    except ClientError as exc:
        err = exc.response.get("Error", {})
        code = err.get("Code", "AWSClientError")
        message = err.get("Message", "AWS Systems Manager command failed")
        return response(409, {"error": f"SSM command failed [{code}]: {message}", "instances": states})

    DDB.put_item(Item={
        "run_id": run_id,
        "created_at": int(time.time()),
        "esc": esc,
        "auto_stop": auto_stop,
        "transport": "UDP/IPv4 over AWS VPC",
        "udp_port": UDP_PORT,
        "zcu_instance_id": X86_ID,
        "zcu_private_ip": zcu["private_ip"],
        "hpc_instance_id": ARM_ID,
        "zcu_command_id": zcu_cmd,
        "hpc_command_id": hpc_cmd,
    })
    return response(202, {
        "run_id": run_id,
        "transport": "real UDP/IPv4 over AWS VPC Ethernet",
        "zcu_private_ip": zcu["private_ip"],
        "udp_port": UDP_PORT,
        "commands": {"zcu": zcu_cmd, "hpc": hpc_cmd},
    })


def get_json(key):
    try:
        obj = S3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise


def get_result(run_id):
    item = DDB.get_item(Key={"run_id": run_id}).get("Item")
    if not item:
        return response(404, {"error": "run not found"})
    hpc = get_json(f"results/{run_id}/hpc.json")
    zcu = get_json(f"results/{run_id}/zcu.json")
    body = {"run": item, "hpc": hpc, "zcu": zcu, "complete": bool(hpc and zcu)}
    if hpc and zcu:
        body["network"] = {
            "transport": hpc.get("transport"),
            "packets_sent": hpc.get("packets_sent"),
            "packets_received": hpc.get("packets_received"),
            "packets_lost": hpc.get("packets_lost"),
            "packet_loss_pct": hpc.get("packet_loss_pct"),
            "rtt_ms_mean": hpc.get("network_rtt_ms_mean"),
            "rtt_ms_p95": hpc.get("network_rtt_ms_p95"),
            "rtt_ms_max": hpc.get("network_rtt_ms_max"),
            "deadline_misses": hpc.get("control_deadline_misses"),
        }
    return response(200, body)


def handler(event, context):
    if not authorized(event):
        return response(401, {"error": "unauthorized"})

    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("rawPath", "")
    try:
        if method == "GET" and path == "/status":
            ssm_map = ssm_statuses()
            return response(200, {
                "x86_64": state(X86_ID, "ZCU / ESC controller", ssm_map),
                "arm64": state(ARM_ID, "HPC / vehicle simulator", ssm_map),
            })

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
    except ClientError as exc:
        err = exc.response.get("Error", {})
        code = err.get("Code", "AWSClientError")
        message = err.get("Message", "AWS request failed")
        print(repr(exc))
        return response(502, {"error": f"AWS error [{code}]: {message}"})
    except Exception as exc:
        print(repr(exc))
        return response(500, {"error": f"control-plane error: {type(exc).__name__}"})
