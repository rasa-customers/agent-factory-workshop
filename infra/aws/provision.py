"""Provision the workshop on AWS (idempotent). Run steps individually or `all`:

    uv run python -m infra.aws.provision network   # security groups + SSH key
    uv run python -m infra.aws.provision cert      # wildcard TLS cert via DNS-01 (Docker + certbot)
    uv run python -m infra.aws.provision bake      # build the cloud-machine image + launch template
    uv run python -m infra.aws.provision portal    # portal host + Elastic IP + wildcard DNS + IAM role
    uv run python -m infra.aws.provision deploy    # copy the stack to the portal host and start it

Everything is tagged project=factory-workshop and lives under factory-workshop.playground-cse.rasa-dev.io.
IAM role creation may need `AWS_PROFILE=cse-playground-admin`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from botocore.exceptions import ClientError

from infra.aws.common import (DOMAIN, PORTAL_TYPE, PROFILE, TAG, VM_PORTS, VM_TYPE, assert_safe_record,
                              parent_zone_id, session, tags)

REPO = Path(__file__).resolve().parents[2]
KEY_PATH = Path.home() / ".ssh" / "factory-workshop.pem"
CERT_DIR = REPO / "infra" / "portal" / "certs"
UBUNTU_SSM = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
ROLE = "factory-workshop-portal"

s = session()
ec2 = s.client("ec2")


def log(msg: str) -> None:
    print(f"==> {msg}", flush=True)


def my_ip() -> str:
    return urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10).read().decode().strip()


def default_vpc() -> str:
    return ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"][0]["VpcId"]


def sg(name: str) -> str | None:
    r = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [name]}])["SecurityGroups"]
    return r[0]["GroupId"] if r else None


def ensure_sg(name: str, desc: str) -> str:
    gid = sg(name)
    if gid:
        return gid
    gid = ec2.create_security_group(GroupName=name, Description=desc, VpcId=default_vpc(),
                                    TagSpecifications=[{"ResourceType": "security-group", "Tags": tags(name)}])["GroupId"]
    log(f"created security group {name} ({gid})")
    return gid


def allow(gid: str, perms: list[dict]) -> None:
    try:
        ec2.authorize_security_group_ingress(GroupId=gid, IpPermissions=perms)
    except ClientError as e:
        if "InvalidPermission.Duplicate" not in str(e):
            raise


def network() -> tuple[str, str]:
    me = f"{my_ip()}/32"
    portal = ensure_sg("factory-workshop-portal", "Agent Factory workshop portal host")
    vm = ensure_sg("factory-workshop-vm", "Agent Factory workshop cloud machines")
    allow(portal, [{"IpProtocol": "tcp", "FromPort": p, "ToPort": p, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]} for p in (80, 443)]
          + [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": me}]}])
    allow(vm, [{"IpProtocol": "tcp", "FromPort": p, "ToPort": p, "UserIdGroupPairs": [{"GroupId": portal}]} for p in VM_PORTS]
          + [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": me}]}])
    if not KEY_PATH.exists():
        try:
            key = ec2.create_key_pair(KeyName="factory-workshop", TagSpecifications=[{"ResourceType": "key-pair", "Tags": [TAG]}])
            KEY_PATH.parent.mkdir(exist_ok=True)
            KEY_PATH.write_text(key["KeyMaterial"])
            KEY_PATH.chmod(0o600)
            log(f"SSH key saved to {KEY_PATH}")
        except ClientError as e:
            if "Duplicate" in str(e):
                raise SystemExit("Key pair factory-workshop exists in AWS but not locally; delete it in AWS and re-run.")
            raise
    log("network ready")
    return portal, vm


def cert() -> None:
    """Wildcard cert for *.DOMAIN using certbot's Route 53 plugin, with the current AWS credentials."""
    creds = subprocess.run(["aws", "configure", "export-credentials", "--profile", PROFILE, "--format", "env-no-export"],
                           capture_output=True, text=True, check=True).stdout
    env = dict(line.split("=", 1) for line in creds.strip().splitlines())
    le = REPO / "infra" / "portal" / "letsencrypt"
    le.mkdir(exist_ok=True)
    cmd = ["docker", "run", "--rm", "-v", f"{le}:/etc/letsencrypt"]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd += ["certbot/dns-route53", "certonly", "--dns-route53", "--non-interactive", "--agree-tos",
            "--register-unsafely-without-email", "-d", f"*.{DOMAIN}", "--cert-name", DOMAIN]
    subprocess.run(cmd, check=True)
    CERT_DIR.mkdir(exist_ok=True)
    live = le / "live" / DOMAIN
    for f in ("fullchain.pem", "privkey.pem"):
        (CERT_DIR / f).write_bytes((live / f).resolve().read_bytes() if (live / f).exists()
                                   else (le / "archive" / DOMAIN / f.replace(".pem", "1.pem")).read_bytes())
    log(f"certificate written to {CERT_DIR}")


def ubuntu_ami() -> str:
    return s.client("ssm").get_parameter(Name=UBUNTU_SSM)["Parameter"]["Value"]


def wait_console(instance_id: str, marker: str, timeout_s: int = 1800) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = ec2.get_console_output(InstanceId=instance_id, Latest=True).get("Output", "") or ""
        if marker in out:
            return
        time.sleep(20)
    raise SystemExit(f"Timed out waiting for {marker!r} on {instance_id}")


def bake() -> str:
    """Build the VM image from a fresh Ubuntu box running bootstrap.sh, then (re)point the launch template at it."""
    _, vm_sg = network()
    repo_url = os.environ.get("REPO_URL") or sys.exit("Set REPO_URL to the public workshop repo.")
    user_data = ("#!/bin/bash\nset -x\n" + f"export REPO_URL={repo_url}\n" +
                 (REPO / "infra" / "vm" / "bootstrap.sh").read_text() +
                 "\necho FACTORY_BAKE_DONE > /dev/console\n")
    inst = ec2.run_instances(ImageId=ubuntu_ami(), InstanceType=VM_TYPE, MinCount=1, MaxCount=1, KeyName="factory-workshop",
                             SecurityGroupIds=[vm_sg], UserData=user_data,
                             BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 30, "VolumeType": "gp3"}}],
                             TagSpecifications=[{"ResourceType": "instance", "Tags": tags("factory-workshop-bake")}])["Instances"][0]
    iid = inst["InstanceId"]
    log(f"baking on {iid} (≈10–15 min)…")
    wait_console(iid, "bootstrap complete")
    ec2.stop_instances(InstanceIds=[iid])
    ec2.get_waiter("instance_stopped").wait(InstanceIds=[iid])
    name = f"factory-workshop-vm-{time.strftime('%Y%m%d-%H%M')}"
    ami = ec2.create_image(InstanceId=iid, Name=name, TagSpecifications=[{"ResourceType": "image", "Tags": tags(name)}])["ImageId"]
    ec2.get_waiter("image_available").wait(ImageIds=[ami], WaiterConfig={"Delay": 20, "MaxAttempts": 90})
    ec2.terminate_instances(InstanceIds=[iid])
    data = {"ImageId": ami, "InstanceType": VM_TYPE, "KeyName": "factory-workshop", "SecurityGroupIds": [vm_sg],
            "BlockDeviceMappings": [{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 30, "VolumeType": "gp3"}}],
            "TagSpecifications": [{"ResourceType": "instance", "Tags": [TAG]}]}
    try:
        ec2.create_launch_template(LaunchTemplateName="factory-workshop-vm", LaunchTemplateData=data,
                                   TagSpecifications=[{"ResourceType": "launch-template", "Tags": [TAG]}])
    except ClientError as e:
        if "AlreadyExists" not in str(e):
            raise
        v = ec2.create_launch_template_version(LaunchTemplateName="factory-workshop-vm", LaunchTemplateData=data)
        ec2.modify_launch_template(LaunchTemplateName="factory-workshop-vm",
                                   DefaultVersion=str(v["LaunchTemplateVersion"]["VersionNumber"]))
    log(f"image {ami} ready; launch template factory-workshop-vm updated")
    return ami


def ensure_role() -> str:
    iam = s.client("iam")
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["ec2:RunInstances", "ec2:CreateTags"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["ec2:Describe*"], "Resource": "*"},
        {"Effect": "Allow", "Action": ["ec2:TerminateInstances"], "Resource": "*",
         "Condition": {"StringEquals": {"aws:ResourceTag/project": "factory-workshop"}}}]}
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                                                     "Action": "sts:AssumeRole"}]}
    try:
        iam.get_role(RoleName=ROLE)
    except ClientError:
        try:
            iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust), Tags=[TAG])
        except ClientError as e:
            raise SystemExit(f"Cannot create IAM role ({e}). Re-run this step with AWS_PROFILE=cse-playground-admin.")
    iam.put_role_policy(RoleName=ROLE, PolicyName="launch-workshop-vms", PolicyDocument=json.dumps(policy))
    try:
        iam.get_instance_profile(InstanceProfileName=ROLE)
    except ClientError:
        iam.create_instance_profile(InstanceProfileName=ROLE)
        iam.add_role_to_instance_profile(InstanceProfileName=ROLE, RoleName=ROLE)
        time.sleep(10)
    return ROLE


def portal_instance() -> dict | None:
    r = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": ["factory-workshop-portal"]},
                                        {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]}])
    found = [i for res in r["Reservations"] for i in res["Instances"]]
    return found[0] if found else None


def portal() -> str:
    portal_sg, _ = network()
    profile = ensure_role()
    inst = portal_instance()
    if inst is None:
        user_data = "#!/bin/bash\ncurl -fsSL https://get.docker.com | sh\nusermod -aG docker ubuntu\n"
        inst = ec2.run_instances(ImageId=ubuntu_ami(), InstanceType=PORTAL_TYPE, MinCount=1, MaxCount=1,
                                 KeyName="factory-workshop", SecurityGroupIds=[portal_sg], UserData=user_data,
                                 IamInstanceProfile={"Name": profile},
                                 BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 40, "VolumeType": "gp3"}}],
                                 TagSpecifications=[{"ResourceType": "instance", "Tags": tags("factory-workshop-portal")}])["Instances"][0]
        log(f"portal host {inst['InstanceId']} launching")
    iid = inst["InstanceId"]
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    addrs = ec2.describe_addresses(Filters=[{"Name": "tag:Name", "Values": ["factory-workshop-portal"]}])["Addresses"]
    if addrs:
        alloc = addrs[0]
    else:
        alloc = ec2.allocate_address(Domain="vpc", TagSpecifications=[{"ResourceType": "elastic-ip", "Tags": tags("factory-workshop-portal")}])
    ec2.associate_address(InstanceId=iid, AllocationId=alloc["AllocationId"])
    ip = alloc["PublicIp"]
    r53 = s.client("route53")
    name = f"*.{DOMAIN}"
    assert_safe_record(name)
    r53.change_resource_record_sets(HostedZoneId=parent_zone_id(r53), ChangeBatch={"Changes": [{
        "Action": "UPSERT", "ResourceRecordSet": {"Name": name, "Type": "A", "TTL": 60, "ResourceRecords": [{"Value": ip}]}}]})
    log(f"portal host {iid} at {ip}; {name} → {ip}")
    return ip


def deploy() -> None:
    inst = portal_instance() or sys.exit("No portal host yet — run the `portal` step.")
    host = inst.get("PublicIpAddress") or sys.exit("Portal host has no public IP yet.")
    env_file = REPO / "infra" / "portal" / ".env"
    if not env_file.exists() or not (CERT_DIR / "fullchain.pem").exists():
        sys.exit("Need infra/portal/.env (see .env.example) and infra/portal/certs/ (run `cert`).")
    ssh = ["-i", str(KEY_PATH), "-o", "StrictHostKeyChecking=accept-new"]
    files = ["infra", "pyproject.toml"]
    subprocess.run(["rsync", "-az", "--delete", "--exclude", "letsencrypt", "--exclude", "__pycache__", "-e",
                    "ssh " + " ".join(ssh), *files, f"ubuntu@{host}:~/workshop/"], cwd=REPO, check=True)
    subprocess.run(["ssh", *ssh, f"ubuntu@{host}",
                    "cd ~/workshop && sudo docker compose -f infra/portal/docker-compose.yml --env-file infra/portal/.env up -d --build"],
                   check=True)
    log(f"deployed — https://portal.{DOMAIN}")


STEPS = {"network": network, "cert": cert, "bake": bake, "portal": portal, "deploy": deploy}

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "all":
        for name in ("network", "cert", "portal", "bake", "deploy"):
            STEPS[name]()
    elif step in STEPS:
        STEPS[step]()
    else:
        sys.exit(__doc__)
