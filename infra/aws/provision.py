"""Provision the workshop on AWS (idempotent). Run steps individually or `all`:

    uv run python -m infra.aws.provision network   # security groups + SSH key
    uv run python -m infra.aws.provision cert      # ACM wildcard cert, validated by DNS
    uv run python -m infra.aws.provision bake      # build the cloud-machine image + launch template
    uv run python -m infra.aws.provision portal    # portal host + load balancer (TLS) + wildcard DNS + IAM role
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


VPC_CIDR = "10.77.0.0/16"
SUBNETS = {"us-east-1a": "10.77.0.0/20", "us-east-1b": "10.77.16.0/20"}


def _tagged(resource: str, name: str) -> list[dict]:
    return [{"ResourceType": resource, "Tags": tags(name)}]


def workshop_vpc() -> tuple[str, list[str]]:
    """The workshop's own VPC (public subnets + internet gateway). Never uses or changes anyone else's network."""
    found = ec2.describe_vpcs(Filters=[{"Name": "tag:project", "Values": ["factory-workshop"]}])["Vpcs"]
    if found:
        vpc = found[0]["VpcId"]
    else:
        vpc = ec2.create_vpc(CidrBlock=VPC_CIDR, TagSpecifications=_tagged("vpc", "factory-workshop"))["Vpc"]["VpcId"]
        ec2.get_waiter("vpc_available").wait(VpcIds=[vpc])
        ec2.modify_vpc_attribute(VpcId=vpc, EnableDnsHostnames={"Value": True})
        log(f"created VPC {vpc}")
    igws = ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc]}])["InternetGateways"]
    if igws:
        igw = igws[0]["InternetGatewayId"]
    else:
        igw = ec2.create_internet_gateway(TagSpecifications=_tagged("internet-gateway", "factory-workshop"))["InternetGateway"]["InternetGatewayId"]
        ec2.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc)
    rts = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc]}, {"Name": "tag:project", "Values": ["factory-workshop"]}])["RouteTables"]
    if rts:
        rt = rts[0]["RouteTableId"]
    else:
        rt = ec2.create_route_table(VpcId=vpc, TagSpecifications=_tagged("route-table", "factory-workshop-public"))["RouteTable"]["RouteTableId"]
        ec2.create_route(RouteTableId=rt, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw)
    subnets = []
    existing = {sn["AvailabilityZone"]: sn["SubnetId"] for sn in
                ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]}])["Subnets"]}
    for az, cidr in SUBNETS.items():
        sid = existing.get(az)
        if not sid:
            sid = ec2.create_subnet(VpcId=vpc, CidrBlock=cidr, AvailabilityZone=az,
                                    TagSpecifications=_tagged("subnet", f"factory-workshop-{az}"))["Subnet"]["SubnetId"]
            ec2.modify_subnet_attribute(SubnetId=sid, MapPublicIpOnLaunch={"Value": True})
            ec2.associate_route_table(RouteTableId=rt, SubnetId=sid)
        subnets.append(sid)
    return vpc, subnets


def default_vpc() -> str:
    return workshop_vpc()[0]


def sg(name: str) -> str | None:
    r = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [name]},
                                             {"Name": "vpc-id", "Values": [default_vpc()]}])["SecurityGroups"]
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


def cert() -> str:
    """ACM wildcard cert for *.DOMAIN, validated by DNS inside our own subdomain. (The parent zone's CAA policy
    allows wildcard certificates only from Amazon, so this is the one way to get one.) Returns the cert ARN."""
    acm = s.client("acm")
    for c in acm.list_certificates(CertificateStatuses=["PENDING_VALIDATION", "ISSUED"])["CertificateSummaryList"]:
        if c["DomainName"] == f"*.{DOMAIN}":
            arn = c["CertificateArn"]
            break
    else:
        arn = acm.request_certificate(DomainName=f"*.{DOMAIN}", ValidationMethod="DNS",
                                      Tags=[TAG, {"Key": "Name", "Value": "factory-workshop"}])["CertificateArn"]
        log(f"requested certificate {arn}")
    for _ in range(30):
        opts = acm.describe_certificate(CertificateArn=arn)["Certificate"].get("DomainValidationOptions", [])
        if opts and "ResourceRecord" in opts[0]:
            break
        time.sleep(2)
    rr = opts[0]["ResourceRecord"]
    assert_safe_record(rr["Name"])
    r53 = s.client("route53")
    r53.change_resource_record_sets(HostedZoneId=parent_zone_id(r53), ChangeBatch={"Changes": [{
        "Action": "UPSERT", "ResourceRecordSet": {"Name": rr["Name"], "Type": rr["Type"], "TTL": 300,
                                                  "ResourceRecords": [{"Value": rr["Value"]}]}}]})
    log("validation record in place; waiting for the certificate (usually 1–5 min)…")
    acm.get_waiter("certificate_validated").wait(CertificateArn=arn, WaiterConfig={"Delay": 15, "MaxAttempts": 60})
    log(f"certificate issued: {arn}")
    return arn


def ubuntu_ami() -> str:
    return s.client("ssm").get_parameter(Name=UBUNTU_SSM)["Parameter"]["Value"]


def wait_console(instance_id: str, marker: str, timeout_s: int = 1800) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = ec2.get_console_output(InstanceId=instance_id, Latest=True).get("Output", "") or ""
        if marker in out:
            return
        if "Failed to run module scripts_user" in out:
            tail = "\n".join(out.strip().splitlines()[-25:])
            raise SystemExit(f"Bootstrap failed on {instance_id} (left running so you can SSH in):\n{tail}")
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
                             SecurityGroupIds=[vm_sg], SubnetId=workshop_vpc()[1][0], UserData=user_data,
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
    data = {"ImageId": ami, "InstanceType": VM_TYPE, "KeyName": "factory-workshop",
            "NetworkInterfaces": [{"DeviceIndex": 0, "SubnetId": workshop_vpc()[1][0], "Groups": [vm_sg],
                                   "AssociatePublicIpAddress": True}],
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


def load_balancer(portal_iid: str, portal_sg: str, cert_arn: str) -> dict:
    """Internet-facing ALB in the workshop VPC: TLS with the ACM wildcard, forwarding HTTP to Caddy on the portal host."""
    elb = s.client("elbv2")
    vpc, subnets = workshop_vpc()
    alb_sg = ensure_sg("factory-workshop-alb", "Agent Factory workshop load balancer")
    allow(alb_sg, [{"IpProtocol": "tcp", "FromPort": p, "ToPort": p, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]} for p in (80, 443)])
    allow(portal_sg, [{"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "UserIdGroupPairs": [{"GroupId": alb_sg}]}])
    try:
        lb = elb.describe_load_balancers(Names=["factory-workshop"])["LoadBalancers"][0]
    except ClientError:
        lb = elb.create_load_balancer(Name="factory-workshop", Subnets=subnets, SecurityGroups=[alb_sg],
                                      Scheme="internet-facing", Type="application", Tags=tags("factory-workshop"))["LoadBalancers"][0]
        log(f"created load balancer {lb['DNSName']}")
    arn = lb["LoadBalancerArn"]
    # long-lived SSE streams and the Inspector's websocket
    elb.modify_load_balancer_attributes(LoadBalancerArn=arn, Attributes=[{"Key": "idle_timeout.timeout_seconds", "Value": "3600"}])
    try:
        tg = elb.describe_target_groups(Names=["factory-workshop-portal"])["TargetGroups"][0]["TargetGroupArn"]
    except ClientError:
        tg = elb.create_target_group(Name="factory-workshop-portal", Protocol="HTTP", Port=80, VpcId=vpc, TargetType="instance",
                                     HealthCheckPath="/healthz", Matcher={"HttpCode": "200"},
                                     Tags=tags("factory-workshop-portal"))["TargetGroups"][0]["TargetGroupArn"]
    elb.register_targets(TargetGroupArn=tg, Targets=[{"Id": portal_iid, "Port": 80}])
    listeners = {l["Port"] for l in elb.describe_listeners(LoadBalancerArn=arn)["Listeners"]}
    if 443 not in listeners:
        elb.create_listener(LoadBalancerArn=arn, Protocol="HTTPS", Port=443, Certificates=[{"CertificateArn": cert_arn}],
                            SslPolicy="ELBSecurityPolicy-TLS13-1-2-2021-06",
                            DefaultActions=[{"Type": "forward", "TargetGroupArn": tg}], Tags=[TAG])
    if 80 not in listeners:
        elb.create_listener(LoadBalancerArn=arn, Protocol="HTTP", Port=80, Tags=[TAG], DefaultActions=[{
            "Type": "redirect", "RedirectConfig": {"Protocol": "HTTPS", "Port": "443", "StatusCode": "HTTP_301"}}])
    return lb


def portal() -> str:
    portal_sg, _ = network()
    cert_arn = cert()
    profile = ensure_role()
    inst = portal_instance()
    if inst is None:
        user_data = "#!/bin/bash\ncurl -fsSL https://get.docker.com | sh\nusermod -aG docker ubuntu\n"
        inst = ec2.run_instances(ImageId=ubuntu_ami(), InstanceType=PORTAL_TYPE, MinCount=1, MaxCount=1,
                                 KeyName="factory-workshop", SecurityGroupIds=[portal_sg], SubnetId=workshop_vpc()[1][0],
                                 UserData=user_data, IamInstanceProfile={"Name": profile},
                                 # the portal runs in Docker: containers need one extra hop to reach instance credentials
                                 MetadataOptions={"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
                                 BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 40, "VolumeType": "gp3"}}],
                                 TagSpecifications=[{"ResourceType": "instance", "Tags": tags("factory-workshop-portal")}])["Instances"][0]
        log(f"portal host {inst['InstanceId']} launching")
    iid = inst["InstanceId"]
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    lb = load_balancer(iid, portal_sg, cert_arn)
    r53 = s.client("route53")
    name = f"*.{DOMAIN}"
    assert_safe_record(name)
    r53.change_resource_record_sets(HostedZoneId=parent_zone_id(r53), ChangeBatch={"Changes": [{
        "Action": "UPSERT", "ResourceRecordSet": {"Name": name, "Type": "A", "AliasTarget": {
            "HostedZoneId": lb["CanonicalHostedZoneId"], "DNSName": lb["DNSName"], "EvaluateTargetHealth": False}}}]})
    log(f"portal host {iid}; {name} → load balancer {lb['DNSName']}")
    return lb["DNSName"]


def deploy() -> None:
    inst = portal_instance() or sys.exit("No portal host yet — run the `portal` step.")
    host = inst.get("PublicIpAddress") or sys.exit("Portal host has no public IP yet.")  # SSH only; web traffic goes via the ALB
    env_file = REPO / "infra" / "portal" / ".env"
    if not env_file.exists():
        sys.exit("Need infra/portal/.env (see .env.example).")
    ssh = ["-i", str(KEY_PATH), "-o", "StrictHostKeyChecking=accept-new"]
    files = ["infra", "pyproject.toml"]
    subprocess.run(["rsync", "-az", "--delete", "--exclude", "letsencrypt", "--exclude", "__pycache__", "-e",
                    "ssh " + " ".join(ssh), *files, f"ubuntu@{host}:~/workshop/"], cwd=REPO, check=True)
    subprocess.run(["ssh", *ssh, f"ubuntu@{host}",
                    "cd ~/workshop && sudo docker compose -f infra/portal/docker-compose.yml --env-file infra/portal/.env up -d --build"],
                   check=True)
    log(f"deployed — https://portal.{DOMAIN}")



STUDIO_TYPE = os.environ.get("STUDIO_TYPE", "t3.xlarge")


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def _set_env(path: Path, updates: dict[str, str]) -> None:
    """Set KEY=value lines in an env file, keeping every other line as it is."""
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            lines[i] = f"{key}={updates[key]}"
            seen.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def studio_instance() -> dict | None:
    r = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": ["factory-workshop-studio"]},
                                        {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]}])
    found = [i for res in r["Reservations"] for i in res["Instances"]]
    return found[0] if found else None


def studio() -> None:
    """Rasa Studio 2.0 on its own host: Review shows every foreman and travel-agent conversation.
    Then points the portal at it (STUDIO_KAFKA_URL, STUDIO_UPSTREAM); run `deploy` afterwards."""
    import secrets as _secrets
    portal_sg, vm_sg = network()
    me = f"{my_ip()}/32"
    gid = ensure_sg("factory-workshop-studio", "Agent Factory workshop Rasa Studio")
    allow(gid, [{"IpProtocol": "tcp", "FromPort": 4000, "ToPort": 4000, "UserIdGroupPairs": [{"GroupId": portal_sg}]},
                {"IpProtocol": "tcp", "FromPort": 29092, "ToPort": 29092, "UserIdGroupPairs": [{"GroupId": vm_sg}]},
                {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": me}]}])
    inst = studio_instance()
    if inst is None:
        user_data = "#!/bin/bash\ncurl -fsSL https://get.docker.com | sh\nusermod -aG docker ubuntu\n"
        inst = ec2.run_instances(ImageId=ubuntu_ami(), InstanceType=STUDIO_TYPE, MinCount=1, MaxCount=1,
                                 KeyName="factory-workshop", SecurityGroupIds=[gid], SubnetId=workshop_vpc()[1][0],
                                 UserData=user_data,
                                 BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"VolumeSize": 60, "VolumeType": "gp3"}}],
                                 TagSpecifications=[{"ResourceType": "instance", "Tags": tags("factory-workshop-studio")}])["Instances"][0]
        log(f"studio host {inst['InstanceId']} launching")
    iid = inst["InstanceId"]
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    private, public = inst["PrivateIpAddress"], inst.get("PublicIpAddress")
    if not public:
        sys.exit("Studio host has no public IP for SSH.")

    local = _env_file(REPO / ".env.local") | _env_file(REPO / ".env")
    env_path = REPO / "infra" / "studio" / ".env"
    current = _env_file(env_path)
    _set_env(env_path, {
        "DOMAIN": DOMAIN, "PRIVATE_IP": private, "STUDIO_IMAGE_TAG": current.get("STUDIO_IMAGE_TAG", "2.0.0.dev5"),
        "DB_PASS": current.get("DB_PASS") or _secrets.token_hex(16),
        "AUTH_SECRET": current.get("AUTH_SECRET") or _secrets.token_hex(32),
        "STUDIO_ENCRYPTION_KEY": current.get("STUDIO_ENCRYPTION_KEY") or _secrets.token_urlsafe(32)[:43],
        "INITIAL_ADMIN_EMAIL": current.get("INITIAL_ADMIN_EMAIL", "admin@factory-workshop.example"),
        "INITIAL_ADMIN_PASSWORD": current.get("INITIAL_ADMIN_PASSWORD") or _secrets.token_urlsafe(18),
        "RASA_PRO_LICENSE": local.get("RASA_LICENSE", ""), "OPENAI_API_KEY": local.get("OPENAI_API_KEY", ""),
    })
    ssh = ["-i", str(KEY_PATH), "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
    for _ in range(60):  # wait for SSH and Docker from user data
        if subprocess.run(["ssh", *ssh, f"ubuntu@{public}", "sudo docker info >/dev/null 2>&1"]).returncode == 0:
            break
        time.sleep(10)
    else:
        sys.exit("Docker never came up on the studio host.")
    template = (REPO / "infra" / "studio" / "config.template.js").read_text()
    (REPO / "infra" / "studio" / "config.js").write_text(template.replace("__STUDIO_URL__", f"https://studio.{DOMAIN}"))
    subprocess.run(["rsync", "-az", "-e", "ssh " + " ".join(ssh), "infra/studio/docker-compose.yml",
                    "infra/studio/.env", "infra/studio/config.js", f"ubuntu@{public}:~/studio/"], cwd=REPO, check=True)
    subprocess.run(["ssh", *ssh, f"ubuntu@{public}",
                    "cd ~/studio && mkdir -p rasa-pro/models rasa-pro/logs rasa-pro/builder && sudo docker compose up -d"],
                   check=True)
    _set_env(REPO / "infra" / "portal" / ".env",
             {"STUDIO_KAFKA_URL": f"{private}:29092", "STUDIO_UPSTREAM": f"{private}:4000"})
    log(f"studio host {iid} ({private}); https://studio.{DOMAIN} once the portal is redeployed. "
        f"Admin: see infra/studio/.env")


STEPS = {"network": network, "cert": cert, "bake": bake, "portal": portal, "deploy": deploy, "studio": studio}

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "all":
        for name in ("network", "cert", "portal", "bake", "deploy"):
            STEPS[name]()
    elif step in STEPS:
        STEPS[step]()
    else:
        sys.exit(__doc__)
