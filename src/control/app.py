import base64
import json
import os
from decimal import Decimal
import time
import uuid

import boto3
from botocore.exceptions import ClientError
from p2_sim import run_study

EC2 = boto3.client("ec2")
SSM = boto3.client("ssm")
S3 = boto3.client("s3")
DDB = boto3.resource("dynamodb").Table(os.environ["RESULTS_TABLE"])
BUCKET = os.environ["RESULTS_BUCKET"]
X86_ID = os.environ["X86_INSTANCE_ID"]
ARM_ID = os.environ["ARM_INSTANCE_ID"]
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
UDP_PORT = 5005
P2_PORT = 13400

P2_IDS = {
    "tester": os.environ["P2_TESTER_INSTANCE_ID"],
    "legacy_gateway": os.environ["P2_LEGACY_GATEWAY_INSTANCE_ID"],
    "legacy_ecu1": os.environ["P2_LEGACY_ECU1_INSTANCE_ID"],
    "legacy_ecu2": os.environ["P2_LEGACY_ECU2_INSTANCE_ID"],
    "legacy_ecu3": os.environ["P2_LEGACY_ECU3_INSTANCE_ID"],
    "legacy_ecu4": os.environ["P2_LEGACY_ECU4_INSTANCE_ID"],
    "hpc": os.environ["P2_HPC_INSTANCE_ID"],
    "zcu1": os.environ["P2_ZCU1_INSTANCE_ID"],
    "zcu2": os.environ["P2_ZCU2_INSTANCE_ID"],
    "zcu3": os.environ["P2_ZCU3_INSTANCE_ID"],
    "zcu4": os.environ["P2_ZCU4_INSTANCE_ID"],
}
LEGACY_ECU_KEYS = tuple(f"legacy_ecu{i}" for i in range(1, 5))
ZCU_KEYS = tuple(f"zcu{i}" for i in range(1, 5))
ALL_INSTANCE_IDS = {X86_ID, ARM_ID, *P2_IDS.values()}
P2_ROLES = {
    "tester": "External OBDonUDS tester",
    "legacy_gateway": "Legacy central diagnostic gateway",
    "legacy_ecu1": "Distributed ECU 1 diagnostic server",
    "legacy_ecu2": "Distributed ECU 2 diagnostic server",
    "legacy_ecu3": "Distributed ECU 3 diagnostic server",
    "legacy_ecu4": "Distributed ECU 4 diagnostic server",
    "hpc": "Graviton zonal HPC router / application proxy",
    "zcu1": "ZCU 1 diagnostic server",
    "zcu2": "ZCU 2 diagnostic server",
    "zcu3": "ZCU 3 diagnostic server",
    "zcu4": "ZCU 4 diagnostic server",
}
P2_PROFILES = {
    "nominal": {"mean_ms": 20.0, "sigma_ms": 7.0, "minimum_ms": 3.0, "maximum_ms": 45.0},
    "near_limit": {"mean_ms": 38.0, "sigma_ms": 5.0, "minimum_ms": 20.0, "maximum_ms": 49.0},
}


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


def request_json(event):
    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")
    return json.loads(raw_body)


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
            if iid in ALL_INSTANCE_IDS:
                statuses[iid] = info.get("PingStatus", "Unknown")
        token = page.get("NextToken")
        if not token or len(statuses) == len(ALL_INSTANCE_IDS):
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
            InstanceIds=[X86_ID], DocumentName="AWS-RunShellScript",
            Parameters={"commands": zcu_commands(run_id, esc, auto_stop)}, TimeoutSeconds=600,
        )["Command"]["CommandId"]
        hpc_cmd = SSM.send_command(
            InstanceIds=[ARM_ID], DocumentName="AWS-RunShellScript",
            Parameters={"commands": hpc_commands(run_id, zcu["private_ip"], esc, auto_stop)}, TimeoutSeconds=600,
        )["Command"]["CommandId"]
    except ClientError as exc:
        err = exc.response.get("Error", {})
        return response(409, {"error": f"SSM command failed [{err.get('Code', 'AWSClientError')}]: {err.get('Message', 'unknown error')}", "instances": states})

    DDB.put_item(Item={
        "run_id": run_id, "created_at": int(time.time()), "experiment": "esc_sil",
        "esc": esc, "auto_stop": auto_stop, "transport": "UDP/IPv4 over AWS VPC", "udp_port": UDP_PORT,
        "zcu_instance_id": X86_ID, "zcu_private_ip": zcu["private_ip"], "hpc_instance_id": ARM_ID,
        "zcu_command_id": zcu_cmd, "hpc_command_id": hpc_cmd,
    })
    return response(202, {
        "run_id": run_id, "transport": "real UDP/IPv4 over AWS VPC Ethernet",
        "zcu_private_ip": zcu["private_ip"], "udp_port": UDP_PORT,
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
            "transport": hpc.get("transport"), "packets_sent": hpc.get("packets_sent"),
            "packets_received": hpc.get("packets_received"), "packets_lost": hpc.get("packets_lost"),
            "packet_loss_pct": hpc.get("packet_loss_pct"), "rtt_ms_mean": hpc.get("network_rtt_ms_mean"),
            "rtt_ms_p95": hpc.get("network_rtt_ms_p95"), "rtt_ms_max": hpc.get("network_rtt_ms_max"),
            "deadline_misses": hpc.get("control_deadline_misses"),
        }
    return response(200, body)


def p2_states():
    ssm_map = ssm_statuses()
    return {name: state(instance_id, P2_ROLES[name], ssm_map) for name, instance_id in P2_IDS.items()}


def p2_profile(body):
    profile = body.get("profile", "nominal")
    if profile in P2_PROFILES:
        return profile, dict(P2_PROFILES[profile])
    if profile != "custom":
        raise ValueError("profile must be nominal, near_limit, or custom")
    custom = body.get("custom_server") or {}
    params = {
        "mean_ms": float(custom.get("mean_ms", 38.0)),
        "sigma_ms": float(custom.get("sigma_ms", 5.0)),
        "minimum_ms": float(custom.get("minimum_ms", 20.0)),
        "maximum_ms": float(custom.get("maximum_ms", 49.0)),
    }
    if params["minimum_ms"] < 0 or params["maximum_ms"] < params["minimum_ms"] or params["sigma_ms"] < 0:
        raise ValueError("invalid custom diagnostic-server timing profile")
    return profile, params


def p2_process_commands(asset, command, auto_stop):
    commands = [
        "set -uo pipefail",
        f"aws s3 cp s3://{BUCKET}/assets/doip_codec.py /tmp/doip_codec.py",
        f"aws s3 cp s3://{BUCKET}/assets/{asset} /tmp/{asset}",
        "code=0",
        f"timeout 1200 {command} || code=$?",
    ]
    if auto_stop:
        commands.append("sudo shutdown -h now || true")
    commands.append("exit $code")
    return commands


def p2_tester_commands(run_id, architecture, legacy_gateway_ip, hpc_ip, samples, budget_ms, auto_stop):
    out = f"/tmp/{run_id}-p2-measured.json"
    commands = [
        "set -euo pipefail",
        f"aws s3 cp s3://{BUCKET}/assets/doip_codec.py /tmp/doip_codec.py",
        f"aws s3 cp s3://{BUCKET}/assets/p2_tester.py /tmp/p2_tester.py",
        "sleep 5",
        (
            f"python3 /tmp/p2_tester.py --architecture {architecture} "
            f"--legacy-gateway-ip {legacy_gateway_ip} --hpc-ip {hpc_ip} --port {P2_PORT} "
            f"--samples {samples} --budget-ms {budget_ms} --output {out}"
        ),
        f"aws s3 cp {out} s3://{BUCKET}/results/{run_id}/p2-measured.json",
    ]
    if auto_stop:
        commands.append("sudo shutdown -h now || true")
    return commands


def send_ssm(instance_id, commands):
    return SSM.send_command(
        InstanceIds=[instance_id], DocumentName="AWS-RunShellScript",
        Parameters={"commands": commands}, TimeoutSeconds=1500,
    )["Command"]["CommandId"]


def run_p2_measured(body):
    architecture = body.get("architecture", "all")
    if architecture not in ("all", "distributed_canfd", "zonal_transparent", "zonal_hpc_proxy"):
        raise ValueError("invalid measured architecture")
    samples = int(body.get("samples", 500))
    if samples < 12 or samples > 5000:
        raise ValueError("measured samples must be between 12 and 5000")
    budget_ms = float(body.get("budget_ms", 50.0))
    if budget_ms <= 0 or budget_ms > 5000:
        raise ValueError("budget_ms must be > 0 and <= 5000")
    proxy_work_ms = float(body.get("proxy_work_ms", 0.0))
    if proxy_work_ms < 0 or proxy_work_ms > 50:
        raise ValueError("proxy_work_ms must be between 0 and 50")
    can_load = float(body.get("can_load", 0.30))
    if can_load < 0 or can_load >= 0.95:
        raise ValueError("can_load must be >= 0 and < 0.95")
    can_arb_bps = float(body.get("can_arb_bps", 500000.0))
    can_data_bps = float(body.get("can_data_bps", 2000000.0))
    if can_arb_bps <= 0 or can_data_bps <= 0:
        raise ValueError("CAN-FD bit rates must be positive")
    auto_stop = bool(body.get("auto_stop", True))
    profile_name, profile = p2_profile(body)

    states = p2_states()
    if any(node["state"] != "running" for node in states.values()):
        return response(409, {"error": "All 11 measured benchmark nodes must be running", "instances": states})
    if any(node["ssm_ping_status"] != "Online" for node in states.values()):
        return response(409, {
            "error": "Benchmark EC2 nodes are running but not all are SSM Online yet. Refresh P2 node status and retry.",
            "instances": states,
        })
    if any(not node.get("private_ip") for node in states.values()):
        return response(409, {"error": "One or more benchmark private IPs are unavailable", "instances": states})

    run_id = str(uuid.uuid4())
    legacy_routes = []
    hpc_routes = []
    proxy_routes = []
    for i in range(1, 5):
        legacy_routes.append(f"--route 0x{0x1000+i:04X}={states[f'legacy_ecu{i}']['private_ip']}:{P2_PORT}")
        hpc_routes.append(f"--route 0x{0x2000+i:04X}={states[f'zcu{i}']['private_ip']}:{P2_PORT}")
        proxy_routes.append(
            f"--proxy-route 0x{0x3000+i:04X}=0x{0x2000+i:04X}@{states[f'zcu{i}']['private_ip']}:{P2_PORT}"
        )

    command_ids = {}
    try:
        for i, key in enumerate(LEGACY_ECU_KEYS, 1):
            cmd = (
                f"python3 /tmp/p2_diag_server.py --role legacy_ecu --zone-id {i} "
                f"--logical-address 0x{0x1000+i:04X} --port {P2_PORT} "
                f"--mean-ms {profile['mean_ms']} --sigma-ms {profile['sigma_ms']} "
                f"--min-ms {profile['minimum_ms']} --max-ms {profile['maximum_ms']} --idle-timeout-s 120"
            )
            command_ids[key] = send_ssm(P2_IDS[key], p2_process_commands("p2_diag_server.py", cmd, auto_stop))

        for i, key in enumerate(ZCU_KEYS, 1):
            cmd = (
                f"python3 /tmp/p2_diag_server.py --role zcu --zone-id {i} "
                f"--logical-address 0x{0x2000+i:04X} --port {P2_PORT} "
                f"--mean-ms {profile['mean_ms']} --sigma-ms {profile['sigma_ms']} "
                f"--min-ms {profile['minimum_ms']} --max-ms {profile['maximum_ms']} --idle-timeout-s 120"
            )
            command_ids[key] = send_ssm(P2_IDS[key], p2_process_commands("p2_diag_server.py", cmd, auto_stop))

        legacy_gateway_cmd = (
            f"python3 /tmp/p2_router.py --role legacy_gateway --entity-address 0x0D00 --port {P2_PORT} "
            + " ".join(legacy_routes)
            + f" --can-arb-bps {can_arb_bps} --can-data-bps {can_data_bps} --can-load {can_load} --idle-timeout-s 120"
        )
        command_ids["legacy_gateway"] = send_ssm(
            P2_IDS["legacy_gateway"], p2_process_commands("p2_router.py", legacy_gateway_cmd, auto_stop)
        )

        hpc_cmd = (
            f"python3 /tmp/p2_router.py --role hpc --entity-address 0x0A00 --port {P2_PORT} "
            + " ".join(hpc_routes + proxy_routes)
            + f" --proxy-work-ms {proxy_work_ms} --idle-timeout-s 120"
        )
        command_ids["hpc"] = send_ssm(P2_IDS["hpc"], p2_process_commands("p2_router.py", hpc_cmd, auto_stop))

        command_ids["tester"] = send_ssm(
            P2_IDS["tester"],
            p2_tester_commands(
                run_id, architecture, states["legacy_gateway"]["private_ip"], states["hpc"]["private_ip"],
                samples, budget_ms, auto_stop,
            ),
        )
    except ClientError as exc:
        err = exc.response.get("Error", {})
        return response(409, {
            "error": f"Measured P2 SSM launch failed [{err.get('Code', 'AWSClientError')}]: {err.get('Message', 'unknown error')}",
            "instances": states,
            "commands_started": command_ids,
        })

    DDB.put_item(Item={
        "run_id": run_id,
        "created_at": int(time.time()),
        "experiment": "p2_measured_v2",
        "architecture": architecture,
        "profile": profile_name,
        "samples": samples,
        "budget_ms": str(budget_ms),
        "proxy_work_ms": str(proxy_work_ms),
        "can_load": str(can_load),
        "can_arb_bps": str(can_arb_bps),
        "can_data_bps": str(can_data_bps),
        "auto_stop": auto_stop,
        "transport": "DoIP framing over TCP/IPv4 on private AWS VPC; CAN-FD timing emulated on legacy gateway",
        "p2_port": P2_PORT,
        "p2_config_json": json.dumps(profile),
        "command_ids_json": json.dumps(command_ids),
        "instance_ids_json": json.dumps(P2_IDS),
    })
    return response(202, {
        "run_id": run_id,
        "mode": "measured_aws_vehicle_architecture",
        "transport": "DoIP diagnostic messages over private AWS VPC TCP/13400",
        "port": P2_PORT,
        "architecture": architecture,
        "profile": profile_name,
        "instances": states,
        "commands": command_ids,
    })


def command_snapshot(command_id, instance_id):
    try:
        item = SSM.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        return {
            "status": item.get("Status"),
            "status_details": item.get("StatusDetails"),
            "stderr": (item.get("StandardErrorContent") or "")[-1500:],
        }
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "InvocationDoesNotExist":
            return {"status": "Pending", "status_details": "Invocation pending", "stderr": ""}
        raise


def get_p2_measured_result(run_id):
    item = DDB.get_item(Key={"run_id": run_id}).get("Item")
    if not item or item.get("experiment") != "p2_measured_v2":
        return response(404, {"error": "measured P2 run not found"})
    measured = get_json(f"results/{run_id}/p2-measured.json")
    command_ids = json.loads(item.get("command_ids_json", "{}"))
    instance_ids = json.loads(item.get("instance_ids_json", "{}"))
    commands = {
        role: command_snapshot(command_id, instance_ids[role])
        for role, command_id in command_ids.items()
    }
    failed = {
        role: snap for role, snap in commands.items()
        if snap.get("status") in ("Failed", "TimedOut", "Cancelled", "Cancelling")
    }
    body = {"run": item, "complete": measured is not None, "result": measured, "commands": commands}
    if failed and measured is None:
        body["error"] = "One or more benchmark node commands failed before a result was produced."
        body["failed_commands"] = failed
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
            return run_benchmark(request_json(event))
        if method == "GET" and path.startswith("/benchmark/results/"):
            return get_result(path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/p2/simulate":
            return response(200, run_study(request_json(event)))
        if method == "GET" and path == "/p2/measured/status":
            return response(200, p2_states())

        if method == "POST" and path.startswith("/p2/measured/nodes/"):
            action = path.rsplit("/", 1)[-1]
            if action not in ("start", "stop"):
                raise ValueError("P2 node action must be start or stop")
            for instance_id in P2_IDS.values():
                start_stop(instance_id, action)
            return response(202, {"action": action, "nodes": list(P2_IDS)})

        if method == "POST" and path == "/p2/measured/run":
            return run_p2_measured(request_json(event))
        if method == "GET" and path.startswith("/p2/measured/results/"):
            return get_p2_measured_result(path.rsplit("/", 1)[-1])
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
